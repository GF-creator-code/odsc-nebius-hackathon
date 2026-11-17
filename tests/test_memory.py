# -*- coding: utf-8 -*-
"""Session-memory tests: save/load roundtrip, evidence-inheritance dedup, cap eviction,
context brief injection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory import SessionMemory, inherit_evidence  # noqa: E402


def _src(url, title="t"):
    return {"url": url, "title": title, "content": "c"}


def test_save_and_load_roundtrip(tmp_path):
    mem = SessionMemory("s1", root=str(tmp_path))
    stats = mem.remember_turn("Q1?", "Answer [1].", [_src("https://a.com/x")], {"q1": True})
    assert stats["added"] == 1
    mem2 = SessionMemory("s1", root=str(tmp_path))
    assert mem2.evidence_pool()[0]["url"] == "https://a.com/x"
    assert mem2.history()[0]["question"] == "Q1?"


def test_dedup_across_turns(tmp_path):
    mem = SessionMemory("s2", root=str(tmp_path))
    mem.remember_turn("Q1?", "a1", [_src("https://a.com/x")])
    # http/https variants of the same article normalize to the same source: not re-added
    stats = mem.remember_turn("Q2?", "a2", [_src("http://a.com/x"), _src("https://b.org/y")])
    assert stats["added"] == 1
    assert mem.evidence_pool().__len__() == 2


def test_evidence_cap_drops_low_tier_first(tmp_path):
    mem = SessionMemory("s3", root=str(tmp_path))
    # 23 primary sources (tier 0) + 1 social (tier 2) -> pool full
    mem.remember_turn("Q1?", "a", [_src(f"https://site{i}.com/x") for i in range(23)]
                      + [_src("https://reddit.com/r/1")])
    mem.remember_turn("Q2?", "b", [_src("https://newone.com/y")])
    pool = mem.evidence_pool()
    assert len(pool) <= 24
    urls = [s["url"] for s in pool]
    assert "https://reddit.com/r/1" not in urls  # least trustworthy evicted first
    assert "https://newone.com/y" in urls        # new primary source kept


def test_inherit_evidence_dedups(tmp_path):
    mem = SessionMemory("s4", root=str(tmp_path))
    mem.remember_turn("Q1?", "a", [_src("https://a.com/x"), _src("https://b.org/y")])
    seen, results = set(), []
    seen.add("a.com/x")  # already in the local pool
    n = inherit_evidence(mem, seen, results)
    assert n == 1
    assert results[0]["url"] == "https://b.org/y"


def test_context_brief_lists_recent_questions(tmp_path):
    mem = SessionMemory("s5", root=str(tmp_path))
    mem.remember_turn("Question one?", "a", [])
    mem.remember_turn("Question two?", "b", [])
    brief = mem.context_brief()
    assert "Question one?" in brief and "Question two?" in brief


def test_none_memory_is_noop(tmp_path):
    from memory import inherit_evidence as inherit
    seen, results = set(), []
    assert inherit(None, seen, results) == 0
    assert not results
