"""
Provider-agnostic LLM client used by scoring.py and outreach.py.

What it adds over a bare API call:
  - one JSON contract for Gemini and Claude (the rubric is the spec, the model is swappable)
  - an on-disk response cache (output/llm_cache.jsonl): re-runs cost nothing, and a run
    that hits the free-tier DAILY quota resumes tomorrow exactly where it stopped
  - rate pacing (requests per minute) plus retry with the server's own retryDelay
  - loud, typed failures: a bad key or retired model aborts the run immediately
    instead of silently falling back on every row

Providers:
  gemini - FREE key from https://aistudio.google.com/apikey  (env GEMINI_API_KEY)
  claude - paid key                                           (env ANTHROPIC_API_KEY)
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Free-tier Flash models change often; override with --model or GEMINI_MODEL.
DEFAULT_MODELS = {
    "gemini": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    "claude": os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5"),
}
KEY_ENV = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


class LLMError(Exception):
    """A single call failed (bad JSON, transient error) - caller may fall back for this row."""


class FatalLLMError(Exception):
    """The run cannot succeed (bad key, unknown model) - abort, don't fall back 500 times."""


class QuotaExhausted(Exception):
    """Free-tier daily quota is used up - stop now, cached work resumes on the next run."""


def extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        raise LLMError(f"no JSON object in response: {text[:120]!r}")
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as e:
        raise LLMError(f"malformed JSON: {e}") from e


def parse_gemini_429(body_text: str) -> tuple:
    """Return (is_daily_quota, retry_after_seconds_or_None) from a Gemini 429 body."""
    daily = "PerDay" in body_text or "per day" in body_text.lower()
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body_text)
    return daily, (float(m.group(1)) if m else None)


class LLMClient:
    def __init__(self, provider: str, model: str = None, cache_path: Path = None,
                 rpm: float = 6, max_attempts: int = 5):
        if provider not in KEY_ENV:
            raise ValueError(f"unknown provider {provider!r}")
        if not os.environ.get(KEY_ENV[provider]):
            hint = (" (free key: https://aistudio.google.com/apikey)"
                    if provider == "gemini" else "")
            raise FatalLLMError(f"Set {KEY_ENV[provider]}{hint}")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self.cache_path = cache_path
        self.min_interval = 60.0 / rpm if rpm else 0.0
        self.max_attempts = max_attempts
        self._last_call = 0.0
        self.network_calls = 0
        self.cache_hits = 0
        self._cache = self._load_cache()
        self._anthropic = None
        if provider == "claude":
            import anthropic
            self._anthropic = anthropic.Anthropic()

    # ------------------------------------------------------------------ cache
    def _load_cache(self) -> dict:
        cache = {}
        if self.cache_path and self.cache_path.exists():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    cache[rec["key"]] = rec["response"]
        return cache

    def _key(self, system: str, user: str) -> str:
        raw = json.dumps([self.provider, self.model, system, user])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _store(self, key: str, response: dict) -> None:
        self._cache[key] = response
        if self.cache_path:
            self.cache_path.parent.mkdir(exist_ok=True)
            with self.cache_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "provider": self.provider,
                                    "model": self.model, "response": response}) + "\n")

    # ------------------------------------------------------------------- call
    def complete_json(self, system: str, user: str) -> dict:
        key = self._key(system, user)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()
        self.network_calls += 1
        if self.provider == "gemini":
            response = self._gemini(system, user)
        else:
            response = self._claude(system, user)
        self._store(key, response)
        return response

    def _gemini(self, system: str, user: str) -> dict:
        import requests
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json",
                                     "temperature": 0}}
        headers = {"x-goog-api-key": os.environ[KEY_ENV["gemini"]],
                   "Content-Type": "application/json"}
        for attempt in range(self.max_attempts):
            try:
                resp = requests.post(GEMINI_URL.format(model=self.model), json=body,
                                     headers=headers, timeout=60)
            except requests.RequestException as e:
                time.sleep(2 ** attempt)
                last = str(e)
                continue
            if resp.status_code == 429:
                daily, retry_after = parse_gemini_429(resp.text)
                if daily:
                    raise QuotaExhausted("Gemini free-tier daily quota exhausted")
                time.sleep(retry_after or 15 * (attempt + 1))
                last = "rate limited (429)"
                continue
            if resp.status_code == 404:
                raise FatalLLMError(
                    f"Model '{self.model}' not found - it may be retired. Pass "
                    "--model <id> (see https://ai.google.dev/gemini-api/docs/models).")
            if resp.status_code in (400, 401, 403):
                raise FatalLLMError(f"Gemini rejected the request ({resp.status_code}): "
                                    f"{resp.text[:300]}")
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                last = f"server error {resp.status_code}"
                continue
            try:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, ValueError) as e:
                raise LLMError(f"unexpected Gemini response shape: {resp.text[:200]}") from e
            return extract_json(text)
        raise LLMError(f"gave up after {self.max_attempts} attempts: {last}")

    def _claude(self, system: str, user: str) -> dict:
        import anthropic
        try:
            msg = self._anthropic.messages.create(
                model=self.model, max_tokens=600, temperature=0, system=system,
                messages=[{"role": "user", "content": user}])
        except (anthropic.AuthenticationError, anthropic.NotFoundError,
                anthropic.PermissionDeniedError) as e:
            raise FatalLLMError(f"Claude rejected the request: {e}") from e
        except anthropic.APIError as e:
            raise LLMError(str(e)) from e
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return extract_json(text)
