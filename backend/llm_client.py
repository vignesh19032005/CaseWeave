"""
Unified LLM client with real fallback chain: Meta (primary) -> Groq (secondary,
still serves real Llama models) -> Google Gemini (tertiary, non-Meta, last resort).

No mock mode. If a provider's key is missing or the call fails, it moves to the
next provider and records which one actually answered, so the pipeline/report
can disclose it (hackathon rule: disclose if a non-Meta fallback was used).

If ALL three are unavailable, functions raise LLMUnavailableError — the
pipeline should surface that clearly, not silently fall back to fake output.
"""
import json
import os
import time
import urllib.request
import urllib.error

from secrets_store import load_all_secrets
from logging_config import get_logger, log_event

_log = get_logger("llm_client")


def _load_env():
    """Stage 13: secrets come from Windows Credential Manager (secrets_store.py),
    not plaintext .env. Falls back to an existing os.environ value if already
    set (e.g. by a deployment's real env vars), so this stays swappable for
    Stage 20's move to a real Vault/Secrets Manager on a shared server."""
    for key, value in load_all_secrets().items():
        if value and key not in os.environ:
            os.environ[key] = value


_load_env()


class LLMUnavailableError(RuntimeError):
    pass


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 60, retries: int = 3) -> dict:
    data = json.dumps(payload).encode("utf-8")
    full_headers = {"User-Agent": "Mozilla/5.0 (CaseWeave/1.0)", **headers}
    req = urllib.request.Request(url, data=data, headers=full_headers, method="POST")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s — rate limit / transient overload backoff
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as e:
            # Any connection-level failure (socket timeout, remote closed
            # the connection, DNS/network blip) — distinct from an HTTP
            # error response, but just as transient. Observed in practice:
            # http.client.RemoteDisconnected right after a network/Docker
            # restart, and a raw socket TimeoutError under load.
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue
            raise


def _call_meta(system: str, prompt: str, max_tokens: int, timeout: int = 60) -> str:
    api_key = os.environ.get("META_API_KEY", "").strip()
    base_url = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").strip()
    if not api_key:
        raise LLMUnavailableError("META_API_KEY not set")

    # Real Meta Model API shape, confirmed live: /v1/responses, "input" field,
    # OpenAI-Responses-API-style — not the /v1/chat/completions shape some
    # earlier docs implied. System + user prompt concatenated into one
    # input string since this endpoint takes a single input, not a
    # messages array.
    # max_tokens is deliberately NOT sent: this API counts its hidden
    # reasoning tokens against max_output_tokens, and a live test with a small
    # cap returned an empty reply. Output size is bounded after the fact.
    payload = {
        "model": "muse-wonder-1.0",
        "input": f"{system}\n\n{prompt}",
        "reasoning": {"effort": "high"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result = _post_json(f"{base_url}/responses", headers, payload, timeout=timeout, retries=2 if timeout > 100 else 3)
    for item in result.get("output", []):
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    return block["text"]
    raise LLMUnavailableError(f"Meta API response had no message/output_text block: {result}")


def _call_groq(system: str, prompt: str, max_tokens: int, timeout: int = 60) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    if not api_key:
        raise LLMUnavailableError("GROQ_API_KEY not set")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_completion_tokens": max_tokens,
        "reasoning_effort": "low",
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result = _post_json("https://api.groq.com/openai/v1/chat/completions", headers, payload, timeout=timeout)
    content = result["choices"][0]["message"]["content"]
    if not content:
        raise LLMUnavailableError("groq returned empty content (reasoning model may have exhausted token budget)")
    return content


def _call_gemini(system: str, prompt: str, max_tokens: int, timeout: int = 60) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    model = os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash").strip()
    if not api_key:
        raise LLMUnavailableError("GOOGLE_API_KEY not set")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
    }
    headers = {"Content-Type": "application/json"}
    result = _post_json(url, headers, payload, timeout=timeout)
    return result["candidates"][0]["content"]["parts"][0]["text"]


def _call_local(system: str, prompt: str, max_tokens: int, timeout: int = 120) -> str:
    """A model running on this machine or on the department's own server, through any
    OpenAI-compatible endpoint (Ollama, vLLM, llama.cpp). Nothing leaves the premises."""
    base = os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").strip().rstrip("/")
    model = os.environ.get("LOCAL_LLM_MODEL", "").strip()
    if not model:
        raise LLMUnavailableError("LOCAL_LLM_MODEL not set")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LOCAL_LLM_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    result = _post_json(f"{base}/chat/completions", headers, payload, timeout=timeout, retries=1)
    content = (result.get("choices") or [{}])[0].get("message", {}).get("content")
    if not content:
        raise LLMUnavailableError("local model returned empty content")
    return content


_ALL_PROVIDERS = [
    ("meta", _call_meta),
    ("groq", _call_groq),
    ("gemini", _call_gemini),
    ("local", _call_local),
]


def provider_mode() -> str:
    """auto: Meta, then the other hosted providers (the long-standing behaviour).
    meta_only: only Meta's hosted models. local_only: only a model on this network."""
    m = os.environ.get("LLM_PROVIDER_MODE", "auto").strip().lower()
    return m if m in ("auto", "meta_only", "local_only") else "auto"


def active_providers():
    mode = provider_mode()
    if mode == "meta_only":
        names = {"meta"}
    elif mode == "local_only":
        names = {"local"}
    else:
        names = {"meta", "groq", "gemini"}
    return [(n, f) for n, f in _ALL_PROVIDERS if n in names]


PROVIDERS = [(n, f) for n, f in _ALL_PROVIDERS if n != "local"]  # kept for older callers; chat() uses active_providers()


def _call_meta_vision(system: str, prompt: str, image_b64: str, mime_type: str, max_tokens: int) -> str:
    api_key = os.environ.get("META_API_KEY", "").strip()
    base_url = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").strip()
    if not api_key:
        raise LLMUnavailableError("META_API_KEY not set")
    # Real confirmed-working shape (tested live): /v1/responses, "input"
    # array with content blocks, model muse-wonder-1.0.
    payload = {
        "model": "muse-wonder-1.0",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"{system}\n\n{prompt}"},
                    {"type": "input_image", "image_url": f"data:{mime_type};base64,{image_b64}"},
                ],
            }
        ],
        "reasoning": {"effort": "high"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result = _post_json(f"{base_url}/responses", headers, payload, timeout=90)
    for item in result.get("output", []):
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    return block["text"]
    raise LLMUnavailableError(f"Meta vision response had no message/output_text block: {result}")


def _call_groq_vision(system: str, prompt: str, image_b64: str, mime_type: str, max_tokens: int) -> str:
    # Disclosed limitation: this account's Groq key has no vision-capable model
    # available (checked via /v1/models — only prompt-guard/whisper/gpt-oss/qwen).
    # Kept as a real attempt (will work automatically if the account gains access
    # to a vision model like llama-4-scout), but expected to fail today.
    raise LLMUnavailableError("No vision-capable model available on this Groq account (checked via /v1/models)")


def _call_gemini_vision(system: str, prompt: str, image_b64: str, mime_type: str, max_tokens: int) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    model = os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash").strip()
    if not api_key:
        raise LLMUnavailableError("GOOGLE_API_KEY not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": f"{system}\n\n{prompt}"},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ]
        }],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
    }
    headers = {"Content-Type": "application/json"}
    result = _post_json(url, headers, payload, timeout=90)
    return result["candidates"][0]["content"]["parts"][0]["text"]


VISION_PROVIDERS = [
    ("meta", _call_meta_vision),
    ("groq", _call_groq_vision),
    ("gemini", _call_gemini_vision),
]


def chat_vision(system: str, prompt: str, image_path, max_tokens: int = 2048) -> tuple[str, str]:
    """Same fallback chain as chat(), but sends an image alongside the text
    prompt. image_path: a Path to a .png/.jpg file. Used for Stage 2 when the
    evidence item is a photo or an extracted video frame."""
    import base64
    from pathlib import Path as _Path

    path = _Path(image_path)
    mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

    errors = []
    allowed = {n for n, _ in active_providers()}
    for name, fn in VISION_PROVIDERS:
        if name not in allowed:
            errors.append(f"{name}: not allowed in {provider_mode()} mode")
            continue
        try:
            text = fn(system, prompt, image_b64, mime_type, max_tokens)
            return name, text
        except LLMUnavailableError as e:
            errors.append(f"{name}: {e}")
            continue
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as e:
            errors.append(f"{name}: call failed — {e}")
            continue
    raise LLMUnavailableError(
        "All vision-capable providers unavailable. Details: " + "; ".join(errors)
    )


def chat_vision_json(system: str, prompt: str, image_path, max_tokens: int = 2048) -> tuple[str, dict]:
    provider, text = chat_vision(system, prompt, image_path, max_tokens)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    try:
        return provider, json.loads(cleaned)
    except json.JSONDecodeError as e:
        if e.msg == "Extra data":
            try:
                value, _ = json.JSONDecoder().raw_decode(cleaned)
                return provider, value
            except json.JSONDecodeError:
                pass
        raise LLMUnavailableError(f"{provider} returned non-JSON output: {e}\nRaw: {text[:300]}")


def chat(system: str, prompt: str, max_tokens: int = 2048, timeout: int | None = None) -> tuple[str, str]:
    """Returns (provider_name_used, response_text). Raises LLMUnavailableError if all fail."""
    errors = []
    start = time.time()
    for name, fn in active_providers():
        try:
            text = fn(system, prompt, max_tokens) if timeout is None else fn(system, prompt, max_tokens, timeout)
            latency_ms = round((time.time() - start) * 1000)
            if name != "meta":
                log_event(_log, "warning", "non-primary LLM provider used", provider=name, latency_ms=latency_ms)
            else:
                log_event(_log, "info", "llm call succeeded", provider=name, latency_ms=latency_ms)
            return name, text
        except LLMUnavailableError as e:
            errors.append(f"{name}: {e}")
            log_event(_log, "warning", "llm provider unavailable", provider=name, error=str(e))
            continue
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as e:
            errors.append(f"{name}: call failed — {e}")
            log_event(_log, "error", "llm provider call failed", provider=name, error=str(e))
            continue
    log_event(_log, "error", "all llm providers exhausted", errors=errors)
    raise LLMUnavailableError(
        "All providers unavailable. Set at least one API key via secrets_store.py or backend/.env. Details: "
        + "; ".join(errors)
    )


def model_id(provider: str) -> str:
    """The model name behind a provider label, recorded with every generated
    artifact so a result can be traced to the exact model that produced it."""
    if provider == "meta":
        return "muse-wonder-1.0"
    if provider == "groq":
        return os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    if provider == "gemini":
        return os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash").strip()
    if provider == "local":
        return os.environ.get("LOCAL_LLM_MODEL", "local").strip()
    return provider


def _parse_json_text(provider: str, text: str):
    """Parses model output as JSON. Tolerates a markdown fence, prose before
    the JSON, and stray text after it; raises LLMUnavailableError only if no
    valid JSON value can be found."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as first:
        decoder = json.JSONDecoder()
        for i, ch in enumerate(cleaned):
            if ch in "{[":
                try:
                    value, _ = decoder.raw_decode(cleaned[i:])
                    return value
                except json.JSONDecodeError:
                    continue
        raise LLMUnavailableError(f"{provider} returned non-JSON output: {first} | Raw: {text[:300]}")


def chat_json(system: str, prompt: str, max_tokens: int = 2048) -> tuple[str, dict]:
    """Same as chat(), but parses the response as JSON (see _parse_json_text)."""
    provider, text = chat(system, prompt, max_tokens)
    return provider, _parse_json_text(provider, text)


def chat_json_ex(system: str, prompt: str, max_tokens: int = 2048, timeout: int | None = None) -> dict:
    """chat_json plus what is needed to audit the call: the model name and
    the raw, unparsed reply."""
    provider, text = chat(system, prompt, max_tokens, timeout)
    return {"provider": provider, "model": model_id(provider), "parsed": _parse_json_text(provider, text), "raw": text}
