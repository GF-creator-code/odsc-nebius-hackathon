"""Sourced — 研究型 Agent 的 Web 界面（Streamlit 薄适配层）

启动：streamlit run app.py   （或 python -m streamlit run app.py）
定位通用：不绑定任何专业领域，问题由用户自由输入。

工程要点：
- 只消费 agent.research_events() 事件流，不复制任何核心逻辑
- 阶段化实时反馈（st.status）：规划/搜索/评估/综合每步可见，长任务不"假死"
- 结果占位符每次运行在同一路径重建（st.empty）→ 新研究开始"立即"替换旧结果；
  上次完成的结果存 session_state，非运行的重渲染时恢复，交互不会清屏
- 引用 [n] 渲染为可点击链接（评委现场核验）
- "证据不足"原样呈现，不美化；异常显式报错，绝不静默
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import research_events, linkify_citations  # noqa: E402

st.set_page_config(page_title="Sourced — research with evidence",
                   page_icon="🔎", layout="centered")

st.title("🔎 Sourced")
st.caption("A research agent that turns questions into **sourced, verifiable answers** — "
           "every claim carries a citation you can open.")

EXAMPLES = [
    "What won the 2026 Nobel Prize in Physics, and for what work?",
    "Compare the current charging standards for electric vehicles in the EU and China",
    "一家公司要出海东南亚，目前各主要国家的企业所得税率是多少？",
]


def _use_example(ex: str) -> None:
    st.session_state["question"] = ex
    st.session_state["autorun"] = True

def _go_home() -> None:
    """清空上次结果与输入，回到空白主页（回调在重渲染前执行，点击即生效）。"""
    st.session_state.pop("last_result", None)
    st.session_state.pop("autorun", None)
    st.session_state["question"] = ""


question = st.text_input("Your research question", key="question",
                         placeholder="Ask anything you need to verify…")
col1, _ = st.columns([1, 3])
run = col1.button("Research", type="primary", use_container_width=True) \
    or st.session_state.pop("autorun", False)

if not question.strip():
    st.caption("Try an example:")
    for ex in EXAMPLES:
        st.button(ex, on_click=_use_example, args=(ex,), use_container_width=True)


def _render_result(box, trace_lines: list, answer: str, sources: list,
                   label: str, state: str) -> None:
    """把一份完成的研究结果渲染进 box（运行完成时与恢复上次结果共用）。"""
    status = box.status(label, state=state, expanded=False)
    status.markdown("```text\n" + "\n".join(trace_lines) + "\n```",
                    help="Research trace — decision log of the agent")
    if sources:
        box.divider()
        box.markdown(linkify_citations(answer, sources))
        box.subheader("Sources")
        for i, s in enumerate(sources, 1):
            box.markdown(f"{i}. [{s['title'] or s['url']}]({s['url']})")
    else:
        box.warning(answer)


# 结果占位符：每次运行同路径重建 —— 新研究开始的瞬间即替换掉旧结果
ph = st.empty()

if run and question.strip():
    q = question.strip()
    result_box = ph.container()

    status = result_box.status(f"🗺 Researching: {q[:80]}", expanded=True)
    trace_ph = status.empty()
    answer, sources, lines = None, [], []

    def _flush(next_hint: str) -> None:
        trace_ph.markdown("```text\n" + "\n".join(lines + [next_hint]) + "\n```")

    try:
        for ev in research_events(q):
            t = ev["type"]
            if t == "plan":
                lines.append(f"🗺 规划查询: {', '.join(ev['queries'])}")
                _flush("🔍 搜索中…")
                status.update(label="🔍 Searching…")
            elif t == "round":
                for e in ev.get("errors", []):
                    lines.append(f"⚠️ {e}")
                if ev["round"] > 0:
                    lines.append(f"🔍 第 {ev['round']} 轮：{ev['queries']} 个查询，"
                                 f"新增 {ev['added']} 条，累计 {ev['total']} 条")
                _flush("🧠 评估证据是否充分…")
            elif t == "judge":
                if ev["sufficient"]:
                    cov = ev.get("coverage") or {}
                    lines.append(f"✅ 证据充分，停止搜索：{ev['reason']}"
                                 + (f"｜覆盖度 {list(cov.keys())}" if cov else ""))
                else:
                    lines.append(f"➕ 证据不足：{ev['reason']}")
                    if ev.get("gaps"):
                        lines.append(f"🕳 未覆盖子问题：{ev['gaps']}")
                _flush("🧠 评估证据是否充分…")
            elif t == "rank":
                lines.append(f"⚖️ 降权：聚合站 {ev['aggregator']} 条 / "
                             f"社交平台 {ev['social']} 条（后置不删除）")
                _flush("📝 综合答案中…")
                status.update(label="📝 Synthesizing answer…")
            elif t == "cap":
                lines.append(f"✂️ 证据池 {ev['before']} → {ev['after']} 条"
                             + (f"（淘汰 {len(ev.get('dropped', []))} 条）" if ev.get("dropped") else ""))
                _flush("📝 综合答案中…")
            elif t == "answer":
                answer, sources = ev["text"], ev["sources"]
    except Exception as e:  # 失败绝不静默：界面明确呈现错误
        status.update(label="❌ Research failed", state="error", expanded=True)
        trace_ph.markdown("```text\n" + "\n".join(lines) + "\n```")
        result_box.error(f"研究过程出错：{e}")
        st.stop()

    # 完成态：收起轨迹、结果落在同一容器内（不整块重绘，避免闪烁）；
    # 存 session_state，后续交互触发的重渲染用 _render_result 恢复同样的内容
    label = (f"✅ Done · {len(sources)} sources"
             if sources else "⚠️ Insufficient evidence")
    status.update(label=label, state="complete" if sources else "error", expanded=False)
    trace_ph.markdown("```text\n" + "\n".join(lines) + "\n```",
                      help="Research trace — decision log of the agent")
    if sources:
        result_box.divider()
        result_box.markdown(linkify_citations(answer, sources))
        result_box.subheader("Sources")
        for i, s in enumerate(sources, 1):
            result_box.markdown(f"{i}. [{s['title'] or s['url']}]({s['url']})")
    else:
        result_box.warning(answer)  # 证据不足路径：原样呈现，不美化
    st.session_state["last_result"] = {
        "trace": lines, "answer": answer, "sources": sources, "label": label,
        "state": "complete" if sources else "error",
    }
    st.button("🏠 返回主页（开始新的研究）", on_click=_go_home, use_container_width=True)

else:
    # 非运行的交互（输入、点击）不丢结果：恢复上次完成态
    last = st.session_state.get("last_result")
    if last:
        _render_result(ph.container(), last["trace"], last["answer"],
                       last["sources"], last["label"], last["state"])
        st.button("🏠 返回主页（开始新的研究）", on_click=_go_home, use_container_width=True)
