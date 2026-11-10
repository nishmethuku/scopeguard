"""Model providers over plain HTTPS (no SDK dependency). Keys come from environment variables.

    anthropic:<model>            ANTHROPIC_API_KEY
    openai:<model>               OPENAI_API_KEY (optionally OPENAI_BASE_URL)
    compat:<base_url>|<model>    any OpenAI-compatible server (vLLM, Ollama, Together, ...), key from COMPAT_API_KEY
    gemini:<model>               GEMINI_API_KEY

Only the harness process talks to these APIs. Sandbox services never touch the network.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class ProviderError(RuntimeError):
    pass


class Provider:
    spec = ""

    rpm = 0.0  # max requests per minute (0 = unlimited)
    max_calls = 0  # hard cap on requests (0 = unlimited)

    def __init__(self):
        self._lock = threading.Lock()
        self._next_ok = 0.0
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.resolved_model = ""
        self.first_call_utc = ""

    def _gate(self):
        """Enforce the request cap and spacing so a free quota is never exceeded by accident."""
        with self._lock:
            if self.max_calls and self.calls >= self.max_calls:
                raise ProviderError(f"call cap of {self.max_calls} reached for {self.spec}; rerun later (runs resume) or raise --max-calls")
            if self.rpm:
                now = time.monotonic()
                wait = self._next_ok - now
                self._next_ok = max(now, self._next_ok) + 60.0 / self.rpm
                if wait > 0:
                    time.sleep(wait)

    def _post(self, url: str, headers: dict, body: dict, retries: int = 8) -> dict:
        self._gate()
        data = json.dumps(body).encode()
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < retries:
                    time.sleep(min(5 * 2 ** attempt, 90))
                    continue
                raise ProviderError(f"HTTP {e.code} from {url.split('?')[0]}: {e.read()[:300]!r}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < retries:
                    time.sleep(min(5 * 2 ** attempt, 90))
                    continue
                raise ProviderError(f"network error: {e}")
        raise ProviderError("unreachable")

    def _note(self, tin: int, tout: int, model: str):
        self.calls += 1
        self.tokens_in += tin
        self.tokens_out += tout
        self.resolved_model = model or self.resolved_model
        if not self.first_call_utc:
            self.first_call_utc = datetime.now(timezone.utc).isoformat()

    def complete(self, system: str, messages: list[dict], max_tokens: int = 700, temperature: float = 0.0):
        raise NotImplementedError

    def info(self) -> dict:
        return {"spec": self.spec, "resolved_model": self.resolved_model, "first_call_utc": self.first_call_utc,
                "calls": self.calls, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}


class AnthropicProvider(Provider):
    def __init__(self, model: str):
        super().__init__()
        self.model, self.spec = model, f"anthropic:{model}"
        self.key = os.environ.get("ANTHROPIC_API_KEY", "")

    def complete(self, system, messages, max_tokens=700, temperature=0.0):
        if not self.key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        r = self._post("https://api.anthropic.com/v1/messages", {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                       {"model": self.model, "max_tokens": max_tokens, "temperature": temperature, "system": system, "messages": messages})
        text = "".join(b.get("text", "") for b in r.get("content", []))
        u = r.get("usage", {})
        self._note(u.get("input_tokens", 0), u.get("output_tokens", 0), r.get("model", self.model))
        return text, u


class OpenAICompatProvider(Provider):
    def __init__(self, model: str, base_url: str = "https://api.openai.com/v1", key_env: str = "OPENAI_API_KEY", label: str = "openai"):
        super().__init__()
        self.model, self.base = model, base_url.rstrip("/")
        self.spec = f"{label}:{model}" if label in ("openai", "groq", "openrouter") else f"compat:{base_url}|{model}"
        self.key = os.environ.get(key_env, "")
        self.key_env, self.needs_key = key_env, label in ("groq", "openrouter")

    def complete(self, system, messages, max_tokens=700, temperature=0.0):
        if self.needs_key and not self.key:
            raise ProviderError(f"{self.key_env} is not set")
        headers = {"authorization": f"Bearer {self.key}"} if self.key else {}
        r = self._post(f"{self.base}/chat/completions", headers,
                       {"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                        "messages": [{"role": "system", "content": system}] + messages})
        text = r["choices"][0]["message"]["content"] or ""
        u = r.get("usage", {})
        self._note(u.get("prompt_tokens", 0), u.get("completion_tokens", 0), r.get("model", self.model))
        return text, u


class GeminiProvider(Provider):
    def __init__(self, model: str):
        super().__init__()
        self.model, self.spec = model, f"gemini:{model}"
        self.key = os.environ.get("GEMINI_API_KEY", "")

    def complete(self, system, messages, max_tokens=700, temperature=0.0):
        if not self.key:
            raise ProviderError("GEMINI_API_KEY is not set")
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages]
        r = self._post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent", {"x-goog-api-key": self.key},
                       {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                        "generationConfig": {"temperature": temperature, "maxOutputTokens": max(max_tokens, 4096)}})
        cand = (r.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        if not text:
            raise ProviderError(f"empty reply from {self.model} (finishReason={cand.get('finishReason')})")
        u = r.get("usageMetadata", {})
        self._note(u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), r.get("modelVersion", self.model))
        return text, u


# Free-tier OpenAI-compatible endpoints: spec "groq:<model>" reads GROQ_API_KEY, "openrouter:<model>" reads OPENROUTER_API_KEY.
FREE_PRESETS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}


def make_provider(spec: str, rpm: float = 0.0, max_calls: int = 0) -> Provider:
    p = _make(spec)
    p.rpm, p.max_calls = rpm, max_calls
    return p


def _make(spec: str) -> Provider:
    kind, _, rest = spec.partition(":")
    if kind == "anthropic":
        return AnthropicProvider(rest)
    if kind == "openai":
        return OpenAICompatProvider(rest, os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    if kind == "compat":
        base, _, model = rest.partition("|")
        return OpenAICompatProvider(model, base, "COMPAT_API_KEY", "compat")
    if kind == "gemini":
        return GeminiProvider(rest)
    if kind in FREE_PRESETS:
        base, env = FREE_PRESETS[kind]
        return OpenAICompatProvider(rest, base, env, kind)
    raise ValueError(f"unknown provider spec '{spec}'")


def list_gemini_models() -> list[str]:
    """Model ids your key can call for text generation (run this to pick a --agent value)."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ProviderError("GEMINI_API_KEY is not set")
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ProviderError(f"HTTP {e.code}: {e.read()[:200]!r}")
    return [m["name"].removeprefix("models/") for m in d.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
