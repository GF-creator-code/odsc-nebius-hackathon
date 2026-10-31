# -*- coding: utf-8 -*-
"""会话记忆测试：存取往返、证据继承去重、上限淘汰、追问注入。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory import SessionMemory, inherit_evidence  # noqa: E402


def _src(url, title="t"):
    return {"url": url, "title": title, "content": "c"}


def test_save_and_load_roundtrip(tmp_path):
    mem = SessionMemory("s1", root=str(tmp_path))
    stats = mem.remember_turn("Q1?", "答案 [1]。", [_src("https://a.com/x")], {"q1": True})
    assert stats["added"] == 1
    mem2 = SessionMemory("s1", root=str(tmp_path))
    assert mem2.evidence_pool()[0]["url"] == "https://a.com/x"
    assert mem2.history()[0]["question"] == "Q1?"


def test_dedup_across_turns(tmp_path):
    mem = SessionMemory("s2", root=str(tmp_path))
    mem.remember_turn("Q1?", "a1", [_src("https://a.com/x")])
    # 同文 http/https 两个版本：规范化后视为同源，不重复入池
    stats = mem.remember_turn("Q2?", "a2", [_src("http://a.com/x"), _src("https://b.org/y")])
    assert stats["added"] == 1
    assert mem.evidence_pool().__len__() == 2


def test_evidence_cap_drops_low_tier_first(tmp_path):
    mem = SessionMemory("s3", root=str(tmp_path))
    # 24 条一手来源（tier 0）+ 1 条社交（tier 2）→ 池满
    mem.remember_turn("Q1?", "a", [_src(f"https://site{i}.com/x") for i in range(23)]
                      + [_src("https://reddit.com/r/1")])
    mem.remember_turn("Q2?", "b", [_src("https://newone.com/y")])
    pool = mem.evidence_pool()
    assert len(pool) <= 24
    urls = [s["url"] for s in pool]
    assert "https://reddit.com/r/1" not in urls  # 低可信最先淘汰
    assert "https://newone.com/y" in urls        # 新一手来源保留


def test_inherit_evidence_dedups(tmp_path):
    mem = SessionMemory("s4", root=str(tmp_path))
    mem.remember_turn("Q1?", "a", [_src("https://a.com/x"), _src("https://b.org/y")])
    seen, results = set(), []
    seen.add("a.com/x")  # 已在本地池
    n = inherit_evidence(mem, seen, results)
    assert n == 1
    assert results[0]["url"] == "https://b.org/y"


def test_context_brief_lists_recent_questions(tmp_path):
    mem = SessionMemory("s5", root=str(tmp_path))
    mem.remember_turn("问题一？", "a", [])
    mem.remember_turn("问题二？", "b", [])
    brief = mem.context_brief()
    assert "问题一？" in brief and "问题二？" in brief


def test_none_memory_is_noop(tmp_path):
    from memory import inherit_evidence as inherit
    seen, results = set(), []
    assert inherit(None, seen, results) == 0
    assert not results
