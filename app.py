"""Sourced — 研究型 Agent 的 Web 界面（Streamlit 薄适配层）

启动：streamlit run app.py
定位通用：不绑定任何专业领域，问题由用户自由输入。

工程要点：
- 只消费 agent.research_events() 事件流，不复制任何核心逻辑
- 引用 [n] 渲染为可点击链接（评委现场核验）
- 研究轨迹实时展示（15% 展示面）；"证据不足"原样呈现，不美化
"""

import sys
import os

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

question = st.text_input("Your research question", placeholder="Ask anything you need to verify…")
col1, _ = st.columns([1, 3])
run = col1.button("Research", type="primary", use_container_width=True)

if not question.strip():
    for ex in EXAMPLES:
        if st.button(ex, key=ex):
            question = ex
            run = True
            break

if run and question.strip():
    trace_box = st.empty()
    answer, sources, lines = None, [], []

    # 消费事件流：轨迹区实时刷新
    for ev in research_events(question.strip()):
        t = ev["type"]
        if t == "plan":
            lines.append(f"🗺 规划查询: {', '.join(ev['queries'])}")
        elif t == "round":
            for e in ev.get("errors", []):
                lines.append(f"⚠️ {e}")
            if ev["round"] > 0:
                lines.append(f"🔍 第 {ev['round']} 轮：{ev['queries']} 个查询，"
                             f"新增 {ev['added']} 条，累计 {ev['total']} 条")
        elif t == "judge":
            if ev["sufficient"]:
                lines.append(f"✅ 证据充分，停止搜索：{ev['reason']}")
            else:
                lines.append(f"➕ 证据不足，补搜：{ev['reason']}")
        elif t == "rank":
            lines.append(f"⚖️ 降权：聚合站 {ev['aggregator']} 条 / 社交平台 {ev['social']} 条（后置不删除）")
        elif t == "cap":
            lines.append(f"✂️ 证据池 {ev['before']} → {ev['after']} 条")
        elif t == "answer":
            answer, sources = ev["text"], ev["sources"]
        trace_box.markdown(
            "```text\n" + "\n".join(lines) + "\n```",
            help="Research trace — live decision log of the agent"
        )

    st.divider()
    if sources:
        st.markdown(linkify_citations(answer, sources))
        st.subheader("Sources")
        for i, s in enumerate(sources, 1):
            st.markdown(f"{i}. [{s['title'] or s['url']}]({s['url']})")
    else:
        st.warning(answer)  # 证据不足路径：原样呈现
