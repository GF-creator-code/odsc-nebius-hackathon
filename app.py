"""Sourced - Web UI for the research agent (thin Streamlit adapter layer).

Start: streamlit run app.py   (or python -m streamlit run app.py)
Domain-agnostic: no binding to any professional domain; users type any question.

Engineering notes:
- Only consumes the agent.research_events() event stream; duplicates no core logic
- Staged live feedback (st.status): plan / search / judge / synthesize visible at every step,
  so long tasks never look frozen
- The result placeholder is rebuilt on the same path each run (st.empty) -> a new research
  run replaces the old result instantly; the last finished result lives in session_state and
  is restored on non-run re-renders, so interactions never wipe the screen
- [n] citations render as clickable links (on-site verification by judges)
- "Insufficient evidence" is shown as-is, unembellished; errors surface explicitly, never silent
"""

import os
import sys
import time

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm  # noqa: E402
from agent import (  # noqa: E402
    MAX_ROUNDS, MAX_SOURCES, linkify_citations, research_events,
)

st.set_page_config(page_title="Sourced — research with evidence",
                   layout="centered")

st.title("Sourced")
st.caption("A research agent that turns questions into **sourced, verifiable answers** — "
           "every claim carries a citation you can open.")

# Sidebar: runtime transparency -- during a demo, judges can verify the inference endpoint and
# model directly, without digging through trace files.
# Load .env before reading config, otherwise the sidebar shows code defaults instead of the
# values actually in effect (llm.chat only loads env on first call).
llm.load_env()
_base = os.environ.get("LLM_BASE_URL", llm.DEFAULT_BASE)
_model = os.environ.get("LLM_MODEL", llm.DEFAULT_MODEL)
with st.sidebar:
    st.header("Runtime config")
    st.markdown("**Inference endpoint**")
    st.code(_base, language=None)
    st.markdown("**Model**")
    st.code(_model, language=None)
    st.markdown("**Search budget**")
    st.code(f"max {MAX_ROUNDS} rounds · max {MAX_SOURCES} sources", language=None)
    st.caption("API keys load from a local .env only; never committed to the repo.")

EXAMPLES = [
    "What won the 2026 Nobel Prize in Physics, and for what work?",
    "Compare the current charging standards for electric vehicles in the EU and China",
    "What are the current corporate income tax rates in major Southeast Asian countries?",
]


def _use_example(ex: str) -> None:
    st.session_state["question"] = ex
    st.session_state["autorun"] = True


def _go_home() -> None:
    """Clear the last result and input, back to the blank home page
    (callbacks run before the re-render, so the click takes effect immediately)."""
    st.session_state.pop("last_result", None)
    st.session_state.pop("autorun", None)
    st.session_state["question"] = ""


question = st.text_input("Your research question", key="question",
                         placeholder="Ask anything you need to verify...")
col1, _ = st.columns([1, 3])
run = col1.button("Research", type="primary", use_container_width=True) \
    or st.session_state.pop("autorun", False)

if not question.strip():
    st.caption("Try an example:")
    for ex in EXAMPLES:
        st.button(ex, on_click=_use_example, args=(ex,), use_container_width=True)


def _answer_md(answer: str, sources: list) -> str:
    """Join the answer and the numbered sources into Markdown for download
    (judges can verify citations offline)."""
    parts = [answer, "", "## Sources", ""]
    parts += [f"{i}. [{s['title'] or s['url']}]({s['url']})" for i, s in enumerate(sources, 1)]
    return "\n".join(parts)


def _render_metrics(box, metrics: dict) -> None:
    """Result metric row: sources / rounds / elapsed -- the scale of this run at a glance."""
    m1, m2, m3 = box.columns(3)
    m1.metric("Sources", metrics["sources"])
    m2.metric("Search rounds", metrics["rounds"])
    m3.metric("Elapsed", metrics["elapsed"])


def _render_result(box, trace_lines: list, answer: str, sources: list,
                   label: str, state: str, metrics: dict = None) -> None:
    """Render one finished research result into the box (shared by the run-completion path
    and the restore-last-result path)."""
    status = box.status(label, state=state, expanded=False)
    status.markdown("```text\n" + "\n".join(trace_lines) + "\n```",
                    help="Research trace - decision log of the agent")
    if metrics:
        _render_metrics(box, metrics)
    if sources:
        box.divider()
        box.markdown(linkify_citations(answer, sources))
        box.subheader("Sources")
        for i, s in enumerate(sources, 1):
            box.markdown(f"{i}. [{s['title'] or s['url']}]({s['url']})")
        box.download_button("Download answer (Markdown)", _answer_md(answer, sources),
                            file_name="sourced-answer.md", mime="text/markdown")
    else:
        box.warning(answer)


# Result placeholder: rebuilt on the same path every run -- a new research run replaces
# the old result the moment it starts
ph = st.empty()

if run and question.strip():
    q = question.strip()
    result_box = ph.container()

    status = result_box.status(f"Researching: {q[:80]}", expanded=True)
    trace_ph = status.empty()
    answer, sources, lines = None, [], []
    t0, rounds = time.time(), 0

    def _flush(next_hint: str) -> None:
        trace_ph.markdown("```text\n" + "\n".join(lines + [next_hint]) + "\n```")

    try:
        for ev in research_events(q):
            t = ev["type"]
            if t == "plan":
                lines.append(f"Planned queries: {', '.join(ev['queries'])}")
                _flush("Searching...")
                status.update(label="Searching...")
            elif t == "round":
                rounds = max(rounds, ev["round"])
                for e in ev.get("errors", []):
                    lines.append(f"Warning: {e}")
                if ev["round"] > 0:
                    lines.append(f"Round {ev['round']}: {ev['queries']} queries, "
                                 f"+{ev['added']} new, {ev['total']} total")
                _flush("Evaluating evidence...")
            elif t == "judge":
                if ev.get("eval_failed"):  # evaluation failure != sufficient: show it honestly
                    lines.append(f"Evaluation failed; stopping at budget limit: {ev['reason']}")
                elif ev["sufficient"]:
                    cov = ev.get("coverage") or {}
                    lines.append(f"Sufficient evidence, stopping: {ev['reason']}"
                                 + (f" | coverage {list(cov.keys())}" if cov else ""))
                else:
                    lines.append(f"Insufficient evidence: {ev['reason']}")
                    if ev.get("gaps"):
                        lines.append(f"Uncovered sub-questions: {ev['gaps']}")
                _flush("Evaluating evidence...")
            elif t == "rank":
                lines.append(f"Demoted: {ev['aggregator']} aggregator / "
                             f"{ev['social']} social (moved to back, not deleted)")
                _flush("Synthesizing answer...")
                status.update(label="Synthesizing answer...")
            elif t == "cap":
                lines.append(f"Evidence pool {ev['before']} -> {ev['after']}"
                             + (f" (dropped {len(ev.get('dropped', []))})" if ev.get("dropped") else ""))
                _flush("Synthesizing answer...")
            elif t == "answer":
                answer, sources = ev["text"], ev["sources"]
    except Exception as e:  # failures are never silent: the UI shows the error explicitly
        status.update(label="Research failed", state="error", expanded=True)
        trace_ph.markdown("```text\n" + "\n".join(lines) + "\n```")
        result_box.error(f"Research failed: {e}")
        st.stop()

    # Completion: collapse the trace, keep the result in the same container (no full
    # re-draw, no flicker); store in session_state so later interaction re-renders restore
    # the same content via _render_result
    label = (f"Done · {len(sources)} sources"
             if sources else "Insufficient evidence")
    status.update(label=label, state="complete" if sources else "error", expanded=False)
    trace_ph.markdown("```text\n" + "\n".join(lines) + "\n```",
                      help="Research trace - decision log of the agent")
    metrics = {"sources": len(sources), "rounds": rounds,
               "elapsed": f"{time.time() - t0:.0f}s"}
    _render_metrics(result_box, metrics)
    if sources:
        result_box.divider()
        result_box.markdown(linkify_citations(answer, sources))
        result_box.subheader("Sources")
        for i, s in enumerate(sources, 1):
            result_box.markdown(f"{i}. [{s['title'] or s['url']}]({s['url']})")
        result_box.download_button("Download answer (Markdown)", _answer_md(answer, sources),
                                   file_name="sourced-answer.md", mime="text/markdown")
    else:
        result_box.warning(answer)  # insufficient-evidence path: shown as-is, unembellished
    st.session_state["last_result"] = {
        "trace": lines, "answer": answer, "sources": sources, "label": label,
        "state": "complete" if sources else "error", "metrics": metrics,
    }
    st.button("Back to home (start a new research)", on_click=_go_home, use_container_width=True)

else:
    # Non-run interactions (typing, clicks) must not lose the result: restore the last state
    last = st.session_state.get("last_result")
    if last:
        _render_result(ph.container(), last["trace"], last["answer"],
                       last["sources"], last["label"], last["state"],
                       last.get("metrics"))
        st.button("Back to home (start a new research)", on_click=_go_home, use_container_width=True)
