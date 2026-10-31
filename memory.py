# -*- coding: utf-8 -*-
"""会话记忆：把每轮研究的证据池与结论持久化，供追问继承。

设计：
- 文件存储（memory/sessions/<session_id>.json），与 traces/ 同风格，零依赖；
- 追问时继承既有证据池（按规范化 URL 去重）与历史 Q&A，只对缺口增量检索，
  避免重复搜索烧额度；
- 记忆不是无限堆叠：证据池超过 EVIDENCE_CAP 时按 tier 降权口径淘汰最旧的
  低可信来源，一手来源优先保留。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from quality import domain_of, norm_url, source_tier

EVIDENCE_CAP = 24  # 记忆里证据池的总量上限（多轮累计）


class SessionMemory:
    """单个会话的记忆存取。session_id 建议用时间戳或用户自定义短 ID。"""

    def __init__(self, session_id: str, root: str = "memory/sessions"):
        self.session_id = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
        self.path = Path(root) / f"{self.session_id}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = None

    # ---- 存取 ----

    def _load(self) -> dict:
        if self._data is None:
            if self.path.exists():
                try:
                    self._data = json.loads(self.path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    self._data = {}
            else:
                self._data = {}
        return self._data

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        self._data = data

    # ---- 读写 ----

    def evidence_pool(self) -> list[dict]:
        """既有证据池（已按规范化 URL 去重）。"""
        return self._load().get("evidence_pool", [])

    def history(self) -> list[dict]:
        """历史问答（question / answer / sources 摘要）。"""
        return self._load().get("history", [])

    def remember_turn(
        self,
        question: str,
        answer: str,
        sources: list[dict],
        coverage: Optional[dict] = None,
    ) -> dict:
        """记录一轮问答，并把新证据合并进证据池（规范化 URL 去重 + 上限淘汰）。"""
        data = self._load()
        seen = {norm_url(s.get("url", "")) for s in data.get("evidence_pool", [])}
        pool = list(data.get("evidence_pool", []))
        added = 0
        for s in sources:
            key = norm_url(s.get("url", ""))
            if key and key not in seen:
                seen.add(key)
                pool.append(s)
                added += 1
        # 上限淘汰：先降权档（tier 高者），同档淘汰最早入库的
        if len(pool) > EVIDENCE_CAP:
            pool.sort(key=lambda s: (source_tier(s.get("url", "")),))  # 稳定：tier 升序
            overflow = len(pool) - EVIDENCE_CAP
            for i in range(len(pool) - 1, -1, -1):
                if source_tier(pool[i].get("url", "")) > 0 and overflow > 0:
                    pool.pop(i)
                    overflow -= 1
            pool = pool[:EVIDENCE_CAP]

        data["evidence_pool"] = pool
        data.setdefault("history", []).append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "question": question,
            "answer": answer,
            "n_sources": len(sources),
            "coverage": coverage or {},
        })
        data["n_turns"] = len(data["history"])
        self._save(data)
        return {"pool_total": len(pool), "added": added, "n_turns": data["n_turns"]}

    def context_brief(self) -> str:
        """给提示词的记忆摘要（历史问题 + 各自结论一句话），控制长度。"""
        hist = self.history()[-3:]  # 最近 3 轮足够定位上下文
        if not hist:
            return ""
        lines = [f"- 已问：{h['question']}" for h in hist]
        return "（会话记忆：以下是本会话已研究过的问题，追问时避免重复检索）\n" + "\n".join(lines)


def inherit_evidence(memory: Optional[SessionMemory], seen: set, results: list) -> int:
    """把记忆中的证据池注入本轮检索的 seen/results（原地修改），返回继承条数。

    seen 是规范化 URL 集合，注入后本轮搜索自然跳过已持有来源。
    """
    if memory is None:
        return 0
    inherited = 0
    for s in memory.evidence_pool():
        key = norm_url(s.get("url", ""))
        if key and key not in seen:
            seen.add(key)
            results.append(s)
            inherited += 1
    return inherited
