# -*- coding: utf-8 -*-
"""judge_evidence regression tests: evaluation failure must be distinct from
"sufficient evidence" (a real defect we fixed).

Background: previously, when judge_evidence raised, it returned sufficient=True with no
failure flag, so the UI and traces displayed "evaluation failed" as "sufficient evidence".
After the fix, the exception path carries eval_failed=True and the event line differs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent  # noqa: E402


def _results():
    return [
        {"title": "A", "url": "https://a.com/x", "content": "Content A" * 30},
        {"title": "B", "url": "https://b.com/y", "content": "Content B" * 30},
    ]


def _setup(monkeypatch, chat_impl):
    monkeypatch.setattr(agent.llm, "chat", chat_impl)


def test_llm_exception_marks_eval_failed(monkeypatch):
    def broken(messages):
        raise RuntimeError("LLM timeout")

    _setup(monkeypatch, broken)
    verdict = agent.judge_evidence("Test question", _results())
    assert verdict["eval_failed"] is True
    assert verdict["sufficient"] is True  # budget control still stops the search
    assert "Evaluation failed" in verdict["reason"]


def test_normal_path_not_marked_failed(monkeypatch):
    def ok(messages):
        return '{"sufficient": true, "reason": "covers all sub-questions", "coverage": {"q": true}, "follow_up": []}'

    _setup(monkeypatch, ok)
    verdict = agent.judge_evidence("Test question", _results())
    assert verdict["eval_failed"] is False
    assert verdict["sufficient"] is True
    assert verdict["coverage"] == {"q": True}


def test_malformed_json_counts_as_eval_failed(monkeypatch):
    def malformed(messages):
        return "this is not JSON"

    _setup(monkeypatch, malformed)
    verdict = agent.judge_evidence("Test question", _results())
    assert verdict["eval_failed"] is True


def test_insufficient_still_drives_followup(monkeypatch):
    def insufficient(messages):
        return ('{"sufficient": false, "reason": "winner list missing", '
                '"coverage": {"winners": false}, "follow_up": ["search winner list"]}')

    _setup(monkeypatch, insufficient)
    verdict = agent.judge_evidence("Test question", _results())
    assert verdict["sufficient"] is False
    assert verdict["eval_failed"] is False
    assert verdict["follow_up"] == ["search winner list"]
