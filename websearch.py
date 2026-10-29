"""Tavily 搜索客户端（ODSC × Nebius Hackathon）

Tavily 负责"取证据"：实时联网搜索，返回正文摘要 + 原始来源链接。
评分要求来源链接一路存活到最终答案（Sourced and verifiable answers, 30%），
所以 search() 返回的每条结果都保留 url / title / content，供引用层使用。

加固点：
- 瞬时失败（网络抖动/429/5xx）指数退避重试，最多 2 次；鉴权/额度错误快速失败
- 响应结构校验：畸形 JSON 不静默返回空，显式报错
- requests.Session 连接复用

配置：在 .env 里写 TAVILY_API_KEY=tvly-xxxx（app.tavily.com 免费注册，每月 1000 次）。
"""

import os
import time

import requests

API = "https://api.tavily.com/search"
TIMEOUT = 30
RETRIES = 2          # 瞬时失败重试次数
BACKOFF = (1, 3)     # 每次重试前等待秒数

# 低可信来源域名：社交平台与 UGC 聚合站。
# 命中者不丢弃而是"降权"——排到证据池末尾，超过上限时被优先淘汰，
# 既避免误杀有用中文资料，又保证优质来源优先进入上下文（对应 30% 有据可查）。
LOW_TRUST_DOMAINS = frozenset({
    # 社交平台
    "reddit.com", "twitter.com", "x.com", "weibo.com", "quora.com",
    "facebook.com", "zhihu.com", "tieba.baidu.com",
    # UGC / 聚合 / 自媒体
    "medium.com", "blogspot.com", "csdn.net", "jianshu.com", "toutiao.com",
    "eastmoney.com", "baijiahao.baidu.com", "sohu.com",
})

_session = requests.Session()


class TavilyError(RuntimeError):
    """key 未配置 / 无效 / 网络不可达等，message 面向使用者。"""


class TavilySearch:
    def __init__(self, api_key: str):
        if not api_key:
            raise TavilyError(
                "TAVILY_API_KEY 未配置：在项目根目录 .env 写入 "
                "TAVILY_API_KEY=tvly-xxxx（app.tavily.com 控制台复制）"
            )
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5, search_depth: str = "basic") -> dict:
        """搜索并返回 {"results": [{"title", "url", "content"}], "answer": str|None}

        search_depth: "basic" 1 credit / "advanced" 2 credits（相关性更好，决赛演示可用）。
        失败抛 TavilyError，不静默返回空结果（比赛要求处理失败且不得编造）。
        """
        payload = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": True,  # 让 Tavily 顺带给一句综合答案，可作合成参考
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
                last_err = f"网络请求失败（代理/防火墙？）：{e}"
                if attempt < RETRIES:
                    time.sleep(BACKOFF[attempt])
                    continue
                raise TavilyError(last_err) from e

            if resp.status_code in (401, 403):
                raise TavilyError(
                    "API key 无效或被拒（401/403）：检查 .env 里的 TAVILY_API_KEY 是否完整"
                )
            if resp.status_code == 432:
                raise TavilyError("额度用尽（432）：app.tavily.com 查看本月剩余 credits")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"Tavily 返回 {resp.status_code}（限流/服务端错误）"
                if attempt < RETRIES:
                    time.sleep(BACKOFF[attempt])
                    continue
                raise TavilyError(last_err)
            if resp.status_code != 200:
                raise TavilyError(f"Tavily 返回 {resp.status_code}: {resp.text[:200]}")

            # 结构校验：畸形响应宁可报错也不给下游一个"看似空的正常结果"
            try:
                data = resp.json()
            except ValueError as e:
                raise TavilyError(f"Tavily 响应不是合法 JSON: {resp.text[:200]}") from e
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise TavilyError(f"Tavily 响应结构异常: {str(data)[:200]}")

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
        raise TavilyError(last_err or "Tavily 未知错误")  # 逻辑上不可达，防御性保留


def load_env(path: str = None) -> None:
    """极简 .env 加载：KEY=VALUE 逐行读入环境变量（不覆盖已有值）。"""
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
