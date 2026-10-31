# -*- coding: utf-8 -*-
"""judge_evidence 回归测试：评估失败必须与「证据充分」状态区分（真实缺陷修复）。

缺陷背景：此前 judge_evidence 异常时返回 sufficient=True 且无失败标记，
界面与轨迹会把「评估失败」显示成「证据充分」。修复后异常路径携带
eval_failed=True，事件行据此显示不同文案。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent  # noqa: E402


def _results():
    return [
        {"title": "A", "url": "https://a.com/x", "content": "内容A" * 30},
        {"title": "B", "url": "https://b.com/y", "content": "内容B" * 30},
    ]


def _setup(monkeypatch, chat_impl):
    monkeypatch.setattr(agent.llm, "chat", chat_impl)


def test_llm_exception_marks_eval_failed(monkeypatch):
    def broken(messages):
        raise RuntimeError("LLM 超时")

    _setup(monkeypatch, broken)
    verdict = agent.judge_evidence("测试问题", _results())
    assert verdict["eval_failed"] is True
    assert verdict["sufficient"] is True  # 停止检索的预算控制仍生效
    assert "评估失败" in verdict["reason"]


def test_normal_path_not_marked_failed(monkeypatch):
    def ok(messages):
        return '{"sufficient": true, "reason": "覆盖全部子问题", "coverage": {"q": true}, "follow_up": []}'

    _setup(monkeypatch, ok)
    verdict = agent.judge_evidence("测试问题", _results())
    assert verdict["eval_failed"] is False
    assert verdict["sufficient"] is True
    assert verdict["coverage"] == {"q": True}


def test_malformed_json_counts_as_eval_failed(monkeypatch):
    def malformed(messages):
        return "这不是 JSON"

    _setup(monkeypatch, malformed)
    verdict = agent.judge_evidence("测试问题", _results())
    assert verdict["eval_failed"] is True


def test_insufficient_still_drives_followup(monkeypatch):
    def insufficient(messages):
        return ('{"sufficient": false, "reason": "缺少获奖者名单", '
                '"coverage": {"获奖者": false}, "follow_up": ["补搜获奖名单"]}')

    _setup(monkeypatch, insufficient)
    verdict = agent.judge_evidence("测试问题", _results())
    assert verdict["sufficient"] is False
    assert verdict["eval_failed"] is False
    assert verdict["follow_up"] == ["补搜获奖名单"]
