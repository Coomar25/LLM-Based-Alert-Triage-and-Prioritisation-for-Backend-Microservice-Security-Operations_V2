"""
Groq API client.

Groq provides extremely fast hosted inference for open models (Llama 3.1 8B,
Llama 3.3 70B, and others) through an OpenAI-compatible API, with a free tier.
On Groq's hardware, inference runs at hundreds of tokens/second, so each alert
is triaged in ~1-2 seconds instead of ~60+ seconds on local CPU.

This client is a DROP-IN REPLACEMENT for ollama_client: it exposes the same
`generate()` function returning the same `LlmResponse` dataclass, and a
`check_groq()` health check mirroring `check_ollama()`. The rest of the
pipeline (sampler, alert_repr, prompts, retrieval, runners, evaluation) is
model-agnostic and needs no changes.

Setup
-----
1. Create a free API key at https://console.groq.com
2. Export it (do NOT hard-code it):
       export GROQ_API_KEY="your_key_here"
3. Select a Groq model string, e.g. "llama-3.1-8b-instant" or
   "llama-3.3-70b-versatile".

Model name mapping
------------------
Groq uses different model identifiers than Ollama:
    Ollama            ->  Groq
    llama3.1:8b       ->  llama-3.1-8b-instant
    llama3.3:70b      ->  llama-3.3-70b-versatile
The pipeline passes whatever --model string you give it straight through, so
pass the Groq identifier when using --provider groq.

Rate limits
-----------
The free tier enforces requests-per-minute and tokens-per-minute limits. The
client handles HTTP 429 (rate limited) with exponential backoff and honours
the Retry-After header when present. If you hit limits with high concurrency,
reduce --workers.

Determinism
-----------
temperature=0 for reproducible triage, matching the local pipeline. Note that
hosted APIs do not guarantee bit-identical outputs across time the way local
greedy decoding does, but temperature 0 makes them as deterministic as the
service allows. Record the model and date of the run for reproducibility.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


@dataclass
class LlmResponse:
    """Result of one generation call. Identical shape to ollama_client,
    plus infra_error to distinguish an infrastructure failure (rate-limit,
    timeout, empty response after retries) from a genuine parse failure
    (the model returned text that wasn't valid JSON).

    infra_error=True means "we never got a usable answer from the service"
    — such alerts should be EXCLUDED from evaluation, not counted as a
    (benign) prediction. parse_ok=False with infra_error=False means the
    model DID answer but the JSON was malformed — a real model failure.
    """
    raw_text: str
    latency_ms: float
    parsed_json: Optional[dict]
    parse_ok: bool
    error: Optional[str] = None
    infra_error: bool = False


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from model output.

    Identical logic to ollama_client._extract_json:
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
    return os.environ.get("GROQ_API_KEY")


def generate(
    prompt: str,
    model: str = DEFAULT_GROQ_MODEL,
    url: str = GROQ_URL,
    temperature: float = 0.0,
    timeout: int = 60,
    max_retries: int = 8,
    expect_json: bool = True,
    min_interval_s: float = 0.0,
) -> LlmResponse:
    """Call Groq's chat completions endpoint once (with retries).

    Mirrors ollama_client.generate: same signature shape, same LlmResponse
    return. temperature=0 for reproducible triage. Handles rate limiting
    (HTTP 429) with backoff, retrying up to max_retries times (default 8,
    high because the free tier throttles aggressively). If all retries are
    exhausted the response is flagged infra_error=True so the caller can
    exclude it rather than count it as a benign prediction.

    min_interval_s: if >0, sleep this long before the request. Used for
    proactive pacing to stay under the free-tier rate limit.
    """
    api_key = _get_api_key()
    if not api_key:
        return LlmResponse(
            raw_text="", latency_ms=0.0, parsed_json=None, parse_ok=False,
            error="GROQ_API_KEY environment variable is not set. "
                  "Get a free key at https://console.groq.com and export it.",
            infra_error=True,
        )

    # Proactive pacing to avoid hammering the rate limit.
    if min_interval_s > 0:
        time.sleep(min_interval_s)

    # Groq uses the OpenAI chat format: a list of messages.
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 512,
    }
    # Ask for JSON output when supported (OpenAI-compatible response_format).
    if expect_json:
        payload["response_format"] = {"type": "json_object"}

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        # Cloudflare (in front of Groq) blocks requests with a bare urllib
        # User-Agent (error 1010). Send a standard UA so the request is
        # allowed through to the API.
        "User-Agent": "Mozilla/5.0 (compatible; ait-parser-research/1.0)",
        "Accept": "application/json",
    }

    last_err = None
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read())
            latency_ms = (time.perf_counter() - t0) * 1000.0

            # OpenAI-compatible response shape
            raw_text = (body.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", ""))
            parsed = _extract_json(raw_text) if expect_json else None
            # An empty body counts as an infrastructure failure, not a
            # legitimate (parseable) benign answer.
            if not raw_text.strip():
                last_err = "Empty response body from API"
                if attempt < max_retries:
                    time.sleep(2.0)
                    continue
                return LlmResponse(
                    raw_text="", latency_ms=latency_ms, parsed_json=None,
                    parse_ok=False, error=last_err, infra_error=True,
                )
            return LlmResponse(
                raw_text=raw_text,
                latency_ms=latency_ms,
                parsed_json=parsed,
                parse_ok=parsed is not None,
                # parse_ok False here means the model answered but the JSON
                # was bad — a genuine model failure, NOT infra.
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
                    wait = min(2.0 * (2 ** attempt), 30.0)  # capped backoff
                time.sleep(wait)
                continue
            # Other server errors — brief backoff and retry
            if 500 <= e.code < 600 and attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
                continue
            # Non-retryable (e.g. 401 bad key, 400 bad request)
            try:
                err_body = e.read().decode("utf-8")[:200]
                last_err += f" — {err_body}"
            except Exception:
                pass
            break

        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = str(e)
            if attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
                continue

    # All retries exhausted — this is an infrastructure failure, flagged so
    # the caller excludes it from evaluation instead of scoring it as benign.
    return LlmResponse(
        raw_text="", latency_ms=0.0, parsed_json=None, parse_ok=False,
        error=f"All {max_retries + 1} attempts failed. Last error: {last_err}",
        infra_error=True,
    )


def check_groq(model: str = DEFAULT_GROQ_MODEL,
               url: str = GROQ_URL) -> tuple[bool, str]:
    """Health check mirroring check_ollama.

    Returns (ok, message). Fails fast if the key is missing or the model
    isn't responding.
    """
    if not _get_api_key():
        return False, ("GROQ_API_KEY is not set. Get a free key at "
                       "https://console.groq.com and `export GROQ_API_KEY=...`")
    resp = generate(
        prompt='Reply with this exact JSON: {"status": "ok"}',
        model=model, url=url, timeout=30, max_retries=2, expect_json=True,
    )
    if resp.error:
        return False, resp.error
    if resp.parse_ok:
        return True, (f"Groq responsive; model '{model}' returned valid JSON "
                      f"in {resp.latency_ms:.0f}ms")
    return True, (f"Groq responsive but model output wasn't clean JSON "
                  f"(raw: {resp.raw_text[:80]!r})")