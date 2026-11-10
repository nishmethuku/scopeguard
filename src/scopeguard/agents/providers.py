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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class ProviderError(RuntimeError):
    pass


class Provider:
    spec = ""

    def __init__(self):
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.resolved_model = ""
        self.first_call_utc = ""

    def _post(self, url: str, headers: dict, body: dict, retries: int = 4) -> dict:
        data = json.dumps(body).encode()
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                raise ProviderError(f"HTTP {e.code} from {url.split('?')[0]}: {e.read()[:300]!r}")
            except urllib.error.URLError as e:
                if attempt < retries:
                    time.sleep(2 ** attempt)
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
        self.spec = f"{label}:{model}" if label == "openai" else f"compat:{base_url}|{model}"
        self.key = os.environ.get(key_env, "")

    def complete(self, system, messages, max_tokens=700, temperature=0.0):
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
        r = self._post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}", {},
                       {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}})
        text = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
        u = r.get("usageMetadata", {})
        self._note(u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), r.get("modelVersion", self.model))
        return text, u


def make_provider(spec: str) -> Provider:
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
    raise ValueError(f"unknown provider spec '{spec}'")
