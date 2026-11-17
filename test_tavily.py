"""Tavily connectivity self-check: python test_tavily.py

Pass criteria: run one real query and print Tavily's synthesized answer plus the result
list with source links.
"""

from websearch import get_client, load_env, TavilyError
import os

try:
    client = get_client()
except TavilyError as e:
    print(f"[x] {e}")
    raise SystemExit(1)

load_env()
key = os.environ.get("TAVILY_API_KEY", "")
print(f"[*] key: {key[:5]}*** (prefix only, so a screen recording never leaks the full key)")

query = "ODSC AI West 2026 hackathon Nebius"
print(f"[*] query: {query}\n")
data = client.search(query, max_results=3)

print(f"[ok] synthesized answer: {data['answer']}\n")
print("[ok] sources:")
for i, r in enumerate(data["results"], 1):
    print(f"  {i}. {r['title']}\n     {r['url']}\n     {r['content'][:80]}...\n")
print("[ok] Tavily API ready; source links are available to the citation layer.")
