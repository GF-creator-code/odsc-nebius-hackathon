# -*- coding: utf-8 -*-
"""eval_traces 评测器测试：轨迹解析 + 引用完整性规则。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_traces import parse_trace, rule_checks  # noqa: E402

TRACE = """# 研究轨迹 · 2026-10-31 00:47:20

推理端点：https://api.tokenfactory.nebius.com/v1
推理模型：test-model

## 问题
测试问题是什么？

## 过程
[规划] ['测试查询']
[第1轮] 查询1个，新增 2 条，累计 2 条
[评估] 证据充分：（覆盖度：{'测试问题是什么': True}）
[排序] 降权：内容聚合站 1 条、社交平台 0 条（不删除，仅后置）

## 最终回答
测试答案内容 [1][2]。

来源：
[1] 来源A
    https://alpha-news.org/2026/report
[2] 来源B
    https://beta-institute.net/paper
"""


def _parsed():
    return parse_trace(TRACE)


def test_parse_question_and_answer():
    t = _parsed()
    assert t["question"] == "测试问题是什么？"
    assert "测试答案内容" in t["answer"]
    assert t["citations"] == [1, 2]


def test_parse_sources_and_domains():
    t = _parsed()
    assert t["n_sources"] == 2
    assert t["n_domains"] == 2


def test_parse_process_metadata():
    t = _parsed()
    assert t["n_rounds"] == 1
    assert t["evaluation_recorded"] is True
    assert t["coverage_sufficient"] is True
    assert t["demoted"] == {"aggregator": 1, "social": 0}


def test_all_checks_pass_on_clean_trace():
    checks = rule_checks(_parsed())
    assert all(c["passed"] for c in checks), checks


def test_dangling_citation_fails():
    t = _parsed()
    t["answer"] = "越界引用 [5]。"
    t["citations"] = [5]
    checks = rule_checks(t)
    failed = [c["name"] for c in checks if not c["passed"]]
    assert "citation_integrity" in failed


def test_no_citations_fails_usage_check():
    t = _parsed()
    t["answer"] = "无引用的回答。"
    t["citations"] = []
    checks = rule_checks(t)
    failed = [c["name"] for c in checks if not c["passed"]]
    assert "citations_used" in failed


def test_single_domain_fails_diversity():
    t = _parsed()
    t["n_domains"] = 1
    t["n_sources"] = 2
    checks = rule_checks(t)
    failed = [c["name"] for c in checks if not c["passed"]]
    assert "source_diversity" in failed


def test_missing_evaluation_fails():
    t = _parsed()
    t["evaluation_recorded"] = False
    checks = rule_checks(t)
    failed = [c["name"] for c in checks if not c["passed"]]
    assert "evaluation_recorded" in failed
