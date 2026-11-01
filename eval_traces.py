# -*- coding: utf-8 -*-
"""Sourced离线评测器：解析traces/ 研究轨迹，对回答质量做规则类check + 可选LLM-as-Judge。

规则类check（零LLM，机械可复现）：
  1. citation_integrity — 回答里的每个 [n] 引用都必须 ≤ 来源编号上限（引用不悬空）
  2. citations_used     — 最终回答至少使用过一次引用
  3. answer_present     — 最终回答非空
  4. search_executed    — 至少执行过一轮搜索
  5. source_diversity   — 来源去重域名 ≥ 2（单来源回声是风险信号）
  6. evaluation_recorded— 评估事件存在（证据充分/不足的判定被记录）

LLM-as-Judge（--llm，需OpenAI兼容接口）：对「回答是否忠实于引用来源、
有无无引用的强断言」做1-5打分；任何失败返回None，不影响规则结论。

用法::

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
# 轨迹解析
# ---------------------------------------------------------------------------

_URL_LINE = re.compile(r"^\s*\[?(\d+)\]?\s*(https?://\S+)\s*$", re.M)
_SOURCE_ITEM = re.compile(r"^\[(\d+)\]\s+(.+?)$", re.M)


def parse_trace(text: str) -> dict:
    """把一份轨迹markdown解析成结构化字典。"""
    question_m = re.search(r"## 问题\n(.+)", text)
    answer_m = re.search(r"## 最终回答\n(.*?)(?=\n来源：|\Z)", text, re.S)
    process_m = re.search(r"## 过程\n(.*?)(?=\n## |\Z)", text, re.S)

    # 来源表取最后一个「来源：」块（部分轨迹会因CLI打印两次）
    blocks = text.split("来源：")
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
    rounds = sorted({int(n) for n in re.findall(r"\[第(\d+)轮\]", process)})
    demote_m = re.search(
        r"\[排序\]\s*降权：内容聚合站 (\d+) 条、社交平台 (\d+) 条", process
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
        "n_followups": len(re.findall(r"\[补搜\]", process)),
        "evaluation_recorded": ("[评估]" in process),
        "coverage_sufficient": ("[评估] 证据充分" in process),
        "demoted": {"aggregator": int(demote_m.group(1)), "social": int(demote_m.group(2))}
        if demote_m else None,
        "insufficient_answer": answer.startswith("现有证据不足以回答"),
    }


# ---------------------------------------------------------------------------
# 规则类check（零LLM）
# ---------------------------------------------------------------------------

def rule_checks(trace: dict) -> list[dict]:
    checks = []

    def add(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": passed, "detail": detail})

    add("answer_present", bool(trace["answer"]), "最终回答非空" if trace["answer"] else "最终回答为空")

    dangling = [n for n in trace["citations"] if n > trace["n_sources"]]
    add(
        "citation_integrity",
        not dangling,
        f"引用 {trace['citations']} vs 来源数 {trace['n_sources']}"
        + (f"，悬空引用: {dangling}" if dangling else ""),
    )
    add("citations_used", bool(trace["citations"]), "回答含引用标记" if trace["citations"] else "回答无任何引用")
    add("search_executed", trace["n_rounds"] >= 1, f"搜索轮数 {trace['n_rounds']}")

    diversity_ok = trace["n_sources"] <= 1 or trace["n_domains"] >= 2
    add(
        "source_diversity",
        diversity_ok,
        f"来源 {trace['n_sources']} 条 / 去重域名 {trace['n_domains']} 个",
    )
    add(
        "evaluation_recorded",
        trace["evaluation_recorded"],
        "证据评估事件已记录" if trace["evaluation_recorded"] else "缺少评估事件",
    )
    return checks


# ---------------------------------------------------------------------------
# LLM-as-Judge（可选）：回答忠实度 + 无引用强断言检查
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "你是研究型问答系统的评审。给你一个问题、一段最终回答。只依据回答文本本身："
    "1) faithfulness：关键结论是否都标注了 [n] 引用（1-5，5=所有关键结论均有引用）；"
    "2) hedging：对证据不足处的处理是否恰当（1-5）。"
    "只输出 JSON：{\"faithfulness\":n,\"hedging\":n,\"reason\":\"...\"}。"
    "不要编造事实，无法判断就给低分并说明。"
)


def llm_judge(question: str, answer: str, *, base_url: str, api_key: str,
              model: str = "MiniMaxAI/MiniMax-M3", timeout: int = 60) -> Optional[dict]:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": f"问题：{question}\n\n最终回答：\n{answer[:4000]}"},
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
# 汇总
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

    parser = argparse.ArgumentParser(description="Sourced 轨迹离线评测")
    parser.add_argument("--dir", default="traces", help="轨迹目录（默认 traces/）")
    parser.add_argument("--llm", action="store_true", help="启用 LLM-as-Judge（需 LLM_BASE_URL/LLM_API_KEY）")
    parser.add_argument("--out", default=None, help="结果 JSON 输出路径")
    args = parser.parse_args(argv)

    llm_kwargs = {
        "base_url": os.environ.get("LLM_BASE_URL", ""),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "MiniMaxAI/MiniMax-M3"),
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
