"""LLM inference client (pluggable).

Default endpoint is Nebius Token Factory (OpenAI-compatible); override via .env:
    LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1
    LLM_API_KEY=<nebius key>
    LLM_MODEL=deepseek-ai/DeepSeek-V4.1-Flash-1017
When LLM_API_KEY is unset, falls back to a local auth file (dev convenience).
No other code needs to change.

Hardening:
- transient failures (network/429/5xx) retry with exponential backoff, at most 2 retries;
  auth errors fail fast
- content=None (some models take a tool-call branch) raises explicitly instead of returning
  an empty string masquerading as an answer
- requests.Session connection reuse
"""

import json
import os
import time

import requests

TIMEOUT = 120
DEFAULT_BASE = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
RETRIES = 2
BACKOFF = (2, 5)

# Local auth file: the key already lives on this machine, avoiding plaintext copies
LOCAL_AUTH_PATH = os.path.expanduser("~/.local/share/opencode/auth.json")

_session = requests.Session()


class LLMError(RuntimeError):
    pass


def load_env(path: str = None) -> None:
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _local_auth_key() -> str:
    try:
        with open(LOCAL_AUTH_PATH, encoding="utf-8") as f:
            return json.load(f)["opencode"]["key"]
    except Exception:
        return ""


def chat(messages: list, model: str = None, temperature: float = 0.2) -> str:
    """OpenAI-compatible chat completions; returns the first reply text.
    Raises LLMError on failure, never fails silently."""
    load_env()
    base = os.environ.get("LLM_BASE_URL", DEFAULT_BASE).rstrip("/")
    key = os.environ.get("LLM_API_KEY", "").strip() or _local_auth_key()
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    if not key:
        raise LLMError("No LLM key: set LLM_API_KEY in .env")

    last_err = None
    for attempt in range(RETRIES + 1):
        try:
            resp = _session.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages, "temperature": temperature},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            last_err = f"LLM network request failed: {e}"
            if attempt < RETRIES:
                time.sleep(BACKOFF[attempt])
                continue
            raise LLMError(last_err) from e

        if resp.status_code in (401, 403):
            raise LLMError("LLM key invalid (401/403)")
        if resp.status_code == 429 or resp.status_code >= 500:
            last_err = f"LLM rate-limited/server error ({resp.status_code})"
            if attempt < RETRIES:
                time.sleep(BACKOFF[attempt])
                continue
            raise LLMError(last_err)
        if resp.status_code != 200:
            raise LLMError(f"LLM returned {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM response malformed: {resp.text[:200]}") from e
        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                "LLM returned empty content (content is None/empty) -- the model may have "
                "taken a tool-call branch or been safety-blocked; retry or switch models"
            )
        return content
    raise LLMError(last_err or "LLM unknown error")  # unreachable in practice; kept defensively
