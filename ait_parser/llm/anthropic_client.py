"""


Anthropic Claude API client.

Uses the Anthropic Messages API to run Claude models — chiefly the fast,
inexpensive Haiku tier (claude-haiku-4-5-20251001) — for high-volume alert
triage. Claude models follow instructions reliably and produce clean
structured output, which directly addresses the malformed-JSON problem seen
with rate-limited free-tier providers. The Anthropic API is a straightforward
authenticated endpoint (no Cloudflare-style blocking).

This client is a DROP-IN REPLACEMENT for the other clients: same `generate()`
returning the same `LlmResponse` dataclass (including infra_error), and a
`check_anthropic()` health check. The rest of the pipeline is model-agnostic.

NOTE: the Anthropic API is PAID (pay-per-token). Haiku is inexpensive and the
prompts/outputs here are small, so a full experiment is typically low-cost,
but it is not free like Groq/Gemini. Ensure the account has API credit.

Setup
-----
1. Create an API key at https://console.anthropic.com and add credit.
2. Export it (do NOT hard-code it):
       export ANTHROPIC_API_KEY="sk-ant-..."
3. Model: "claude-haiku-4-5-20251001" (fast/cheap) or another Claude model.

API format (Messages API)
-------------------------
    POST https://api.anthropic.com/v1/messages
    headers:
        x-api-key: <key>
        anthropic-version: 2023-06-01
        content-type: application/json
    body: {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 512,
        "temperature": 0.0,
        "system": "<optional system prompt>",
        "messages": [
            {"role": "user", "content": "<prompt>"},
            {"role": "assistant", "content": "{"}   # JSON prefill (see below)
        ]
    }
    response: content[0].text  (text blocks), plus stop_reason, usage

Reliable JSON via assistant prefill
-----------------------------------
Unlike OpenAI/Gemini, the Anthropic API has no response_format=json flag.
The standard technique is to prefill the assistant turn with an opening
brace "{". The model then continues the JSON object, so the returned text is
the remainder — we prepend the "{" back before parsing. This makes Claude
emit clean JSON without markdown fences or preamble.

Rate limits
-----------
Paid tiers have generous rate limits, but 429s are still possible under
burst. The client backs off on 429; exhausted retries are flagged
infra_error=True so they are excluded from scoring, not counted as benign.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# The brace we prefill the assistant turn with, prepended back before parsing.
_JSON_PREFILL = "{"


@dataclass
class LlmResponse:
    """Result of one generation call. Identical shape to the other clients,
    including infra_error to distinguish an infrastructure failure (rate
    limit, timeout, empty response after retries) from a genuine parse
    failure (the model answered but the JSON was malformed).

    infra_error=True  -> we never got a usable answer; EXCLUDE from scoring.
    parse_ok=False, infra_error=False -> model answered but JSON was bad.
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
    return os.environ.get("ANTHROPIC_API_KEY")


def generate(
    prompt: str,
    model: str = DEFAULT_ANTHROPIC_MODEL,
    url: str = ANTHROPIC_URL,
    temperature: float = 0.0,
    timeout: int = 60,
    max_retries: int = 8,
    expect_json: bool = True,
    min_interval_s: float = 0.0,
) -> LlmResponse:
    """Call the Anthropic Messages API once (with retries).

    Same signature shape and LlmResponse return as the other clients.
    temperature=0 for reproducible triage. When expect_json, the assistant
    turn is prefilled with "{" to force clean JSON output. Handles rate
    limiting (HTTP 429) with backoff; exhausted retries flag infra_error=True.

    min_interval_s: if >0, sleep before the request (proactive pacing).
    """
    api_key = _get_api_key()
    if not api_key:
        return LlmResponse(
            raw_text="", latency_ms=0.0, parsed_json=None, parse_ok=False,
            error="ANTHROPIC_API_KEY environment variable is not set. Get a "
                  "key at https://console.anthropic.com and export it.",
            infra_error=True,
        )

    if min_interval_s > 0:
        time.sleep(min_interval_s)

    messages = [{"role": "user", "content": prompt}]
    if expect_json:
        # Prefill the assistant turn to force JSON output.
        messages.append({"role": "assistant", "content": _JSON_PREFILL})

    payload = {
        "model": model,
        "max_tokens": 512,
        "temperature": temperature,
        "messages": messages,
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }

    last_err = None
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read())
            latency_ms = (time.perf_counter() - t0) * 1000.0

            # Messages API response: content is a list of blocks; concatenate
            # the text blocks.
            raw_text = ""
            for block in body.get("content", []):
                if block.get("type") == "text":
                    raw_text += block.get("text", "")

            # If we prefilled "{", the model's continuation omits it — add back
            # so the text is a complete JSON object.
            if expect_json and raw_text and not raw_text.lstrip().startswith("{"):
                raw_text = _JSON_PREFILL + raw_text

            if not raw_text.strip():
                last_err = "Empty response content from API"
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
            # Rate limited / overloaded — honour Retry-After, else backoff
            if e.code in (429, 529) and attempt < max_retries:
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
            # Non-retryable (400 bad request, 401 bad key, 403 forbidden)
            try:
                err_body = e.read().decode("utf-8")[:300]
                last_err += f" — {err_body}"
            except Exception:
                pass
            # Auth/permission problems are infra (no usable answer).
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


def check_anthropic(model: str = DEFAULT_ANTHROPIC_MODEL,
                    url: str = ANTHROPIC_URL) -> tuple[bool, str]:
    """Health check mirroring the other clients' checks."""
    if not _get_api_key():
        return False, ("ANTHROPIC_API_KEY is not set. Get a key at "
                       "https://console.anthropic.com and "
                       "`export ANTHROPIC_API_KEY=...`")
    resp = generate(
        prompt='Reply with this exact JSON and nothing else: '
               '{"status": "ok"}',
        model=model, url=url, timeout=30, max_retries=2, expect_json=True,
    )
    if resp.error and resp.infra_error:
        return False, resp.error
    if resp.parse_ok:
        return True, (f"Anthropic responsive; model '{model}' returned valid "
                      f"JSON in {resp.latency_ms:.0f}ms")
    return True, (f"Anthropic responsive but output wasn't clean JSON "
                  f"(raw: {resp.raw_text[:80]!r})")
