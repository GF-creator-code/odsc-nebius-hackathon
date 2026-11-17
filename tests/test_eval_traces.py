# -*- coding: utf-8 -*-
"""eval_traces evaluator tests: trace parsing + citation-integrity rules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_traces import parse_trace, rule_checks  # noqa: E402

TRACE = """# Research trace - 2026-11-16 00:47:20

Inference endpoint: https://api.tokenfactory.nebius.com/v1
Inference model: test-model

## Question
What is the test question?

## Process
[Plan] ['test query']
[Round 1] 1 queries, +2 new, 2 total
[Judge] Sufficient evidence: reason here (coverage: {'What is the test question?': True})
[Rank] Demoted: 1 content-aggregator / 0 social (kept, moved to back)

## Final answer
Test answer content [1][2].

Sources:
[1] Source A
    https://alpha-news.org/2026/report
[2] Source B
    https://beta-institute.net/paper
"""


def _parsed():
    return parse_trace(TRACE)


def test_parse_question_and_answer():
    t = _parsed()
    assert t["question"] == "What is the test question?"
    assert "Test answer content" in t["answer"]
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
    t["answer"] = "Out-of-range citation [5]."
    t["citations"] = [5]
    checks = rule_checks(t)
    failed = [c["name"] for c in checks if not c["passed"]]
    assert "citation_integrity" in failed


def test_no_citations_fails_usage_check():
    t = _parsed()
    t["answer"] = "An answer with no citations."
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
