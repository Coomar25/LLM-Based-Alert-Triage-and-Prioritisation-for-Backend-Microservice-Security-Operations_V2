"""
Google Gemini API client.

Google's Gemini API (via AI Studio, aistudio.google.com) provides hosted
inference with a free tier that has substantially higher throughput than
Groq's free tier — the reason we switched. It runs on Google's own
infrastructure, so it avoids the Cloudflare-fronting that blocked Groq
requests (HTTP 403 error 1010).

This client is a DROP-IN REPLACEMENT for ollama_client / groq_client: it
exposes the same `generate()` returning the same `LlmResponse` dataclass
(including the infra_error flag), and a `check_gemini()` health check. The
rest of the pipeline is model-agnostic and needs no changes.

Setup
-----
1. Create a free API key at https://aistudio.google.com (Get API key).
2. Export it (do NOT hard-code it):
       export GEMINI_API_KEY="your_key_here"
3. Select a model, e.g. "gemini-2.0-flash" (fast, free-tier friendly) or
   "gemini-2.5-flash".

API format (REST generateContent)
---------------------------------
    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    header: x-goog-api-key: <key>
    body: {
        "contents": [{"parts": [{"text": "<prompt>"}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 512,
            "response_mime_type": "application/json"   # forces JSON output
        }
    }
    response: candidates[0].content.parts[0].text

Rate limits
-----------
The free tier enforces requests-per-minute and requests-per-day limits
(more generous than Groq's). The client handles HTTP 429 with exponential
backoff. Exhausted retries are flagged infra_error=True so the caller
excludes them from scoring rather than counting them as benign predictions.

Determinism
-----------
temperature=0 for reproducible triage, matching the local pipeline. As with
any hosted API, outputs are as deterministic as the service allows rather
than bit-identical across time. Record the model and run date for
reproducibility.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


@dataclass
class LlmResponse:
    """Result of one generation call. Identical shape to the other clients,
    including infra_error to distinguish an infrastructure failure (rate
    limit, timeout, empty response after retries) from a genuine parse
    failure (the model answered but the JSON was malformed).

    infra_error=True  -> we never got a usable answer; EXCLUDE from scoring.
    parse_ok=False, infra_error=False -> model answered but JSON was bad
                                         (a real model failure worth counting).
    """
    raw_text: str
    latency_ms: float
    parsed_json: Optional[dict]
    parse_ok: bool
    error: Optional[str] = None
    infra_error: bool = False


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from model output.

    Identical logic to the other clients:
        1. Direct json.loads
        2. Strip markdown ```json fences
        3. Regex-extract the first {...} block
    """
    text = text.strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text,
                    flags=re.MULTILINE).strip()
    try:
        return json.loads(fenced)
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _get_api_key() -> Optional[str]:
    # Accept either GEMINI_API_KEY or GOOGLE_API_KEY (both are common).
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def generate(
    prompt: str,
    model: str = DEFAULT_GEMINI_MODEL,
    url: str = None,
    temperature: float = 0.0,
    timeout: int = 60,
    max_retries: int = 8,
    expect_json: bool = True,
    min_interval_s: float = 0.0,
) -> LlmResponse:
    """Call Gemini's generateContent endpoint once (with retries).

    Same signature shape and LlmResponse return as ollama_client /
    groq_client. temperature=0 for reproducible triage. Handles rate
    limiting (HTTP 429) with backoff; exhausted retries are flagged
    infra_error=True.

    min_interval_s: if >0, sleep this long before the request (proactive
    pacing to stay under the free-tier rate limit).
    """
    api_key = _get_api_key()
    if not api_key:
        return LlmResponse(
            raw_text="", latency_ms=0.0, parsed_json=None, parse_ok=False,
            error="GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable is "
                  "not set. Get a free key at https://aistudio.google.com and "
                  "export it.",
            infra_error=True,
        )

    # Gemini takes the model in the URL path, not the body.
    endpoint = (url or GEMINI_URL_TEMPLATE).format(model=model)

    # Proactive pacing to avoid hammering the rate limit.
    if min_interval_s > 0:
        time.sleep(min_interval_s)

    gen_config = {
        "temperature": temperature,
        "maxOutputTokens": 512,
    }
    if expect_json:
        # Forces the model to emit valid JSON.
        gen_config["response_mime_type"] = "application/json"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
        "User-Agent": "ait-parser-research/1.0",
        "Accept": "application/json",
    }

    last_err = None
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(endpoint, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read())
            latency_ms = (time.perf_counter() - t0) * 1000.0

            # Gemini response shape: candidates[0].content.parts[0].text
            raw_text = ""
            candidates = body.get("candidates", [])
            if candidates:
                parts = (candidates[0].get("content", {}) or {}).get("parts", [])
                # Concatenate any text parts (usually one).
                raw_text = "".join(p.get("text", "") for p in parts)

            # A blocked prompt returns no candidates but a promptFeedback block.
            # An empty body is an infrastructure/response failure, not a benign
            # answer.
            if not raw_text.strip():
                # Check for an explicit safety block to report clearly.
                feedback = body.get("promptFeedback", {})
                block_reason = feedback.get("blockReason")
                if block_reason:
                    # A safety block IS a real (if unhelpful) response — the
                    # model refused. Treat as a parseable "no decision":
                    # return malformed (not infra) so it's counted, not hidden.
                    return LlmResponse(
                        raw_text=f"[blocked: {block_reason}]",
                        latency_ms=latency_ms, parsed_json=None,
                        parse_ok=False, error=f"Safety block: {block_reason}",
                        infra_error=False,
                    )
                last_err = "Empty response body from API"
                if attempt < max_retries:
                    time.sleep(2.0)
                    continue
                return LlmResponse(
                    raw_text="", latency_ms=latency_ms, parsed_json=None,
                    parse_ok=False, error=last_err, infra_error=True,
                )

            parsed = _extract_json(raw_text) if expect_json else None
            return LlmResponse(
                raw_text=raw_text,
                latency_ms=latency_ms,
                parsed_json=parsed,
                parse_ok=parsed is not None,
                infra_error=False,
            )

        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.reason}"
            # Rate limited — honour Retry-After, else exponential backoff
            if e.code == 429 and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = min(2.0 * (2 ** attempt), 30.0)
                else:
                    wait = min(2.0 * (2 ** attempt), 30.0)
                time.sleep(wait)
                continue
            # Server errors — brief backoff and retry
            if 500 <= e.code < 600 and attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
                continue
            # Non-retryable (400 bad request, 401/403 bad key)
            try:
                err_body = e.read().decode("utf-8")[:300]
                last_err += f" — {err_body}"
            except Exception:
                pass
            # A bad key / permission problem is infra (no usable answer).
            infra = e.code in (401, 403)
            return LlmResponse(
                raw_text="", latency_ms=0.0, parsed_json=None, parse_ok=False,
                error=last_err, infra_error=infra,
            )

        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = str(e)
            if attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
                continue

    # All retries exhausted — infrastructure failure, excluded from scoring.
    return LlmResponse(
        raw_text="", latency_ms=0.0, parsed_json=None, parse_ok=False,
        error=f"All {max_retries + 1} attempts failed. Last error: {last_err}",
        infra_error=True,
    )


def check_gemini(model: str = DEFAULT_GEMINI_MODEL,
                 url: str = None) -> tuple[bool, str]:
    """Health check mirroring check_ollama / check_groq."""
    if not _get_api_key():
        return False, ("GEMINI_API_KEY is not set. Get a free key at "
                       "https://aistudio.google.com and "
                       "`export GEMINI_API_KEY=...`")
    resp = generate(
        prompt='Reply with this exact JSON: {"status": "ok"}',
        model=model, url=url, timeout=30, max_retries=2, expect_json=True,
    )
    if resp.error and resp.infra_error:
        return False, resp.error
    if resp.parse_ok:
        return True, (f"Gemini responsive; model '{model}' returned valid JSON "
                      f"in {resp.latency_ms:.0f}ms")
    return True, (f"Gemini responsive but model output wasn't clean JSON "
                  f"(raw: {resp.raw_text[:80]!r})")
