"""Tavily 连通性自检：python test_tavily.py

通过标准：跑一个真实查询，打印 Tavily 的综合答案与带来源链接的结果列表。
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
print(f"[*] key: {key[:8]}...{key[-4:] if len(key) > 12 else ''}")

query = "ODSC AI West 2026 hackathon Nebius"
print(f"[*] 查询: {query}\n")
data = client.search(query, max_results=3)

print(f"[✓] 综合答案: {data['answer']}\n")
print("[✓] 来源:")
for i, r in enumerate(data["results"], 1):
    print(f"  {i}. {r['title']}\n     {r['url']}\n     {r['content'][:80]}...\n")
print("[✓] Tavily API 配置完成，来源链接可用于引用层。")
