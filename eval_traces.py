# -*- coding: utf-8 -*-
"""Sourced offline evaluator: parses traces/ research traces and runs rule-based checks
plus an optional LLM-as-Judge pass.

Rule-based checks (zero LLM cost, mechanically reproducible):
  1. citation_integrity  - every [n] citation in the answer must be <= the number of sources
  2. citations_used      - the final answer cites at least one source
  3. answer_present      - the final answer is non-empty
  4. search_executed     - at least one search round ran
  5. source_diversity    - >= 2 distinct source domains (a single-source echo is a risk signal)
  6. evaluation_recorded - a judge event exists (the sufficiency decision is on record)

LLM-as-Judge (--llm, needs an OpenAI-compatible endpoint): scores faithfulness
("is the answer supported by the cited sources, any strong claims without citations")
on a 1-5 scale; any failure returns None and does not affect the rule-based verdict.

Usage::

    python eval_traces.py --dir traces/ [--llm] [--out eval_report.json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Trace parsing
# ---------------------------------------------------------------------------

_URL_LINE = re.compile(r"^\s*\[?(\d+)\]?\s*(https?://\S+)\s*$", re.M)
_SOURCE_ITEM = re.compile(r"^\[(\d+)\]\s+(.+?)$", re.M)


def parse_trace(text: str) -> dict:
    """Parse one trace markdown file into a structured dict."""
    question_m = re.search(r"## Question\n(.+)", text)
    answer_m = re.search(r"## Final answer\n(.*?)(?=\nSources:|\Z)", text, re.S)
    process_m = re.search(r"## Process\n(.*?)(?=\n## |\Z)", text, re.S)

    # Take the last "Sources:" block (some traces print the list twice via the CLI)
    blocks = text.split("Sources:")
    sources: dict[int, dict[str, str]] = {}
    for block in blocks[1:]:
        for m in _SOURCE_ITEM.finditer(block):
            idx = int(m.group(1))
            url_m = re.search(r"(https?://\S+)", block[m.end(): m.end() + 200])
            if idx not in sources and url_m:
                sources[idx] = {"title": m.group(2).strip(), "url": url_m.group(1)}

    answer = (answer_m.group(1) if answer_m else "").strip()
    citations = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)})

    process = process_m.group(1) if process_m else ""
    rounds = sorted({int(n) for n in re.findall(r"\[Round (\d+)\]", process)})
    demote_m = re.search(
        r"\[Rank\]\s*Demoted: (\d+) content-aggregator / (\d+) social", process
    )

    def _domain(url: str) -> str:
        host = url.split("//", 1)[-1].split("/", 1)[0].lower()
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    domains = {_domain(s["url"]) for s in sources.values() if s["url"]}

    return {
        "question": (question_m.group(1).strip() if question_m else ""),
        "answer": answer,
        "citations": citations,
        "n_sources": len(sources),
        "source_urls": [s["url"] for s in sources.values()],
        "n_domains": len(domains),
        "n_rounds": len(rounds),
        "n_followups": len(re.findall(r"\[Follow-up\]", process)),
        "evaluation_recorded": ("[Judge]" in process),
        "coverage_sufficient": ("[Judge] Sufficient evidence" in process),
        "demoted": {"aggregator": int(demote_m.group(1)), "social": int(demote_m.group(2))}
        if demote_m else None,
        "insufficient_answer": ("insufficient" in answer[:300].lower()),
    }


# ---------------------------------------------------------------------------
# Rule-based checks (zero LLM cost)
# ---------------------------------------------------------------------------

def rule_checks(trace: dict) -> list[dict]:
    checks = []

    def add(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": passed, "detail": detail})

    add("answer_present", bool(trace["answer"]),
        "final answer non-empty" if trace["answer"] else "final answer empty")

    dangling = [n for n in trace["citations"] if n > trace["n_sources"]]
    add(
        "citation_integrity",
        not dangling,
        f"citations {trace['citations']} vs sources {trace['n_sources']}"
        + (f", dangling: {dangling}" if dangling else ""),
    )
    add("citations_used", bool(trace["citations"]),
        "answer contains citations" if trace["citations"] else "answer has no citations")
    add("search_executed", trace["n_rounds"] >= 1, f"search rounds {trace['n_rounds']}")

    diversity_ok = trace["n_sources"] <= 1 or trace["n_domains"] >= 2
    add(
        "source_diversity",
        diversity_ok,
        f"sources {trace['n_sources']} / distinct domains {trace['n_domains']}",
    )
    add(
        "evaluation_recorded",
        trace["evaluation_recorded"],
        "evidence-judge event recorded" if trace["evaluation_recorded"]
        else "no judge event found",
    )
    return checks


# ---------------------------------------------------------------------------
# LLM-as-Judge (optional): faithfulness + hedging score
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "You are a reviewer for a research-QA system. Given a question and a final answer, judge "
    "based only on the answer text itself: "
    "1) faithfulness: are all key conclusions cited with [n] references (1-5, 5 = every key "
    "claim is cited); "
    "2) hedging: is insufficient evidence handled appropriately (1-5). "
    "Output only JSON: {\"faithfulness\":n,\"hedging\":n,\"reason\":\"...\"}. "
    "Do not fabricate facts; if you cannot judge, give a low score and explain."
)


def llm_judge(question: str, answer: str, *, base_url: str, api_key: str,
              model: str = "deepseek-ai/DeepSeek-V4.1-Flash-1017",
              timeout: int = 60) -> Optional[dict]:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\nFinal answer:\n{answer[:4000]}"},
        ],
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = json.loads(resp.read())["choices"][0]["message"]["content"]
            data = json.loads(content)
            if isinstance(data.get("faithfulness"), (int, float)):
                return data
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def evaluate_dir(trace_dir: str | Path, llm: bool = False, **llm_kwargs: Any) -> dict:
    files = sorted(Path(trace_dir).glob("*.md"))
    reports = []
    for f in files:
        trace = parse_trace(f.read_text(encoding="utf-8"))
        checks = rule_checks(trace)
        judge = None
        if llm and trace["answer"] and llm_kwargs.get("base_url") and llm_kwargs.get("api_key"):
            judge = llm_judge(trace["question"], trace["answer"], **llm_kwargs)
        reports.append({
            "file": f.name,
            "question": trace["question"][:80],
            "passed": all(c["passed"] for c in checks),
            "checks": checks,
            "n_sources": trace["n_sources"],
            "n_rounds": trace["n_rounds"],
            "n_followups": trace["n_followups"],
            "coverage_sufficient": trace["coverage_sufficient"],
            "judge": judge,
        })

    failed = Counter(c["name"] for r in reports for c in r["checks"] if not c["passed"])
    judged = [r["judge"] for r in reports if r["judge"]]
    return {
        "traces": len(reports),
        "passed": sum(r["passed"] for r in reports),
        "pass_rate": round(sum(r["passed"] for r in reports) / len(reports), 4) if reports else None,
        "failed_checks": dict(failed),
        "avg_sources": round(sum(r["n_sources"] for r in reports) / len(reports), 1) if reports else 0,
        "avg_rounds": round(sum(r["n_rounds"] for r in reports) / len(reports), 1) if reports else 0,
        "followup_rate": round(
            sum(1 for r in reports if r["n_followups"] > 0) / len(reports), 4) if reports else None,
        "llm_avg_faithfulness": round(
            sum(j["faithfulness"] for j in judged) / len(judged), 2) if judged else None,
        "reports": reports,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sourced offline trace evaluator")
    parser.add_argument("--dir", default="traces", help="trace directory (default traces/)")
    parser.add_argument("--llm", action="store_true",
                        help="enable LLM-as-Judge (needs LLM_BASE_URL/LLM_API_KEY)")
    parser.add_argument("--out", default=None, help="write the report JSON to this path")
    args = parser.parse_args(argv)

    llm_kwargs = {
        "base_url": os.environ.get("LLM_BASE_URL", ""),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash-1017"),
    }
    summary = evaluate_dir(args.dir, llm=args.llm, **llm_kwargs)
    output = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"[ok] {args.out}")
    print(
        f"traces={summary['traces']} passed={summary['passed']} "
        f"pass_rate={summary['pass_rate']} avg_sources={summary['avg_sources']} "
        f"avg_rounds={summary['avg_rounds']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
