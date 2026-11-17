# -*- coding: utf-8 -*-
"""Session memory: persists each research round's evidence pool and conclusion so that
follow-up questions can inherit them.

Design:
- File storage (memory/sessions/<session_id>.json), same style as traces/, zero dependencies;
- On follow-up questions, the existing evidence pool (deduped by normalized URL) and the
  Q&A history are inherited, and only the gaps are searched incrementally -- no repeated
  searches burning quota;
- Memory is not an unbounded pile: when the evidence pool exceeds EVIDENCE_CAP, demoted
  low-trust sources are evicted first (by tier), primary sources are kept preferentially.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from quality import domain_of, norm_url, source_tier

EVIDENCE_CAP = 24  # total cap on the evidence pool across rounds


class SessionMemory:
    """Per-session memory store. session_id should be a timestamp or a short user-defined ID."""

    def __init__(self, session_id: str, root: str = "memory/sessions"):
        self.session_id = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
        self.path = Path(root) / f"{self.session_id}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = None

    # ---- persistence ----

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

    # ---- read/write ----

    def evidence_pool(self) -> list[dict]:
        """Existing evidence pool (already deduped by normalized URL)."""
        return self._load().get("evidence_pool", [])

    def history(self) -> list[dict]:
        """Q&A history (question / answer / source summary)."""
        return self._load().get("history", [])

    def remember_turn(
        self,
        question: str,
        answer: str,
        sources: list[dict],
        coverage: Optional[dict] = None,
    ) -> dict:
        """Record one Q&A round and merge new evidence into the pool (normalized-URL dedup
        plus cap eviction)."""
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
        # Cap eviction: higher tier (less trustworthy) evicted first; within a tier the
        # stable sort keeps insertion order and eviction walks from the tail (most recent)
        if len(pool) > EVIDENCE_CAP:
            pool.sort(key=lambda s: (source_tier(s.get("url", "")),))  # stable: ascending tier
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
        """Memory summary for prompts (recent questions + one-line conclusions), length-capped."""
        hist = self.history()[-3:]  # the last 3 rounds are enough to locate the context
        if not hist:
            return ""
        lines = [f"- Asked: {h['question']}" for h in hist]
        return ("(Session memory: questions already researched in this session; "
                "avoid re-searching them in follow-ups)\n" + "\n".join(lines))


def inherit_evidence(memory: Optional[SessionMemory], seen: set, results: list) -> int:
    """Inject the remembered evidence pool into this round's seen/results (in place);
    returns the number of inherited items.

    `seen` is the normalized-URL set, so after injection this round's searches naturally
    skip already-held sources.
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
