"""Tavily search client (ODSC x Nebius Hackathon).

Tavily handles evidence gathering: live web search returning content snippets plus original
source links. The judging criteria require source links to survive all the way into the
final answer (Sourced and verifiable answers, 30%), so every result keeps url / title /
content for the citation layer.

Hardening:
- transient failures (network blips/429/5xx) retry with exponential backoff, at most 2;
  auth/quota errors fail fast
- response structure validation: malformed JSON raises explicitly instead of silently
  returning an empty result set
- requests.Session connection reuse

Config: put TAVILY_API_KEY=tvly-xxxx in .env (free signup at app.tavily.com, 1000 credits/month).
"""

import os
import time

import requests

API = "https://api.tavily.com/search"
TIMEOUT = 30
RETRIES = 2          # retries on transient failures
BACKOFF = (1, 3)     # seconds to wait before each retry

_session = requests.Session()


class TavilyError(RuntimeError):
    """Key missing / invalid / network unreachable, etc.; message is user-facing."""


class TavilySearch:
    def __init__(self, api_key: str):
        if not api_key:
            raise TavilyError(
                "TAVILY_API_KEY not set: write TAVILY_API_KEY=tvly-xxxx "
                "into a .env in the project root (copy from the app.tavily.com console)"
            )
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5, search_depth: str = "basic") -> dict:
        """Search and return {"results": [{"title", "url", "content"}], "answer": str|None}

        search_depth: "basic" 1 credit / "advanced" 2 credits (better relevance; fine for
        a final demo). Raises TavilyError on failure, never returns empty silently
        (the competition requires failures to be handled without fabrication).
        """
        payload = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": True,  # let Tavily add a one-line synthesized answer as reference
        }
        last_err = None
        for attempt in range(RETRIES + 1):
            try:
                resp = _session.post(
                    API,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                    timeout=TIMEOUT,
                )
            except requests.RequestException as e:
                last_err = f"Network request failed (proxy/firewall?): {e}"
                if attempt < RETRIES:
                    time.sleep(BACKOFF[attempt])
                    continue
                raise TavilyError(last_err) from e

            if resp.status_code in (401, 403):
                raise TavilyError(
                    "API key invalid or rejected (401/403): check TAVILY_API_KEY in .env is complete"
                )
            if resp.status_code == 432:
                raise TavilyError("Quota exhausted (432): check monthly credits at app.tavily.com")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"Tavily returned {resp.status_code} (rate limit/server error)"
                if attempt < RETRIES:
                    time.sleep(BACKOFF[attempt])
                    continue
                raise TavilyError(last_err)
            if resp.status_code != 200:
                raise TavilyError(f"Tavily returned {resp.status_code}: {resp.text[:200]}")

            # Structure validation: a malformed response must error out rather than flow
            # downstream as a "normal but empty-looking" result
            try:
                data = resp.json()
            except ValueError as e:
                raise TavilyError(f"Tavily response is not valid JSON: {resp.text[:200]}") from e
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise TavilyError(f"Tavily response structure malformed: {str(data)[:200]}")

            return {
                "answer": data.get("answer"),
                "results": [
                    {
                        "title": str(r.get("title", "")),
                        "url": str(r.get("url", "")),
                        "content": str(r.get("content", "")),
                    }
                    for r in data["results"] if isinstance(r, dict)
                ],
            }
        raise TavilyError(last_err or "Tavily unknown error")  # unreachable; kept defensively


def load_env(path: str = None) -> None:
    """Minimal .env loader: KEY=VALUE lines into the environment (no override)."""
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


def get_client() -> TavilySearch:
    load_env()
    return TavilySearch(os.environ.get("TAVILY_API_KEY", "").strip())
