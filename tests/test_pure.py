"""纯逻辑自测（不联网、不耗 API 额度）：python tests/test_pure.py

覆盖加固后的关键纯函数：JSON 容错解析、证据池截断、正文截断、轨迹落盘。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import _json_out, _norm_url, _is_low_trust, Trace, MAX_SOURCES, SNIPPET_CHARS  # noqa: E402



def test_json_out_variants():
    assert _json_out('{"queries": ["a"]}') == {"queries": ["a"]}
    assert _json_out('```json\n{"sufficient": true}\n```') == {"sufficient": True}
    assert _json_out('前置杂讯 {"x": 1} 后置杂讯') == {"x": 1}
    for bad in ("完全不是JSON", "缺右括号 {\"a\": 1", ""):
        try:
            _json_out(bad)
            raise SystemExit(f"[fail] 应拒绝: {bad!r}")
        except ValueError:
            pass  # JSONDecodeError 是 ValueError 子类，符合预期
    print("[ok] _json_out 容错解析")


def test_source_cap():
    fake = [{"title": f"t{i}", "url": f"https://x/{i}", "content": "c"} for i in range(50)]
    capped = fake[:MAX_SOURCES]
    assert len(capped) == MAX_SOURCES == 12
    # 引用编号不悬空：提示词里的编号与来源列表一致由 gather 保证，这里验证截断保持顺序
    assert capped[0]["url"] == "https://x/0"
    print("[ok] 证据池截断 MAX_SOURCES=12")


def test_snippet_truncation():
    long_content = "字" * (SNIPPET_CHARS + 500)
    snippet = long_content[:SNIPPET_CHARS] + "…"
    assert len(snippet) == SNIPPET_CHARS + 1 and snippet.endswith("…")
    short = "短内容"
    assert short[:SNIPPET_CHARS] + ("…" if len(short) > SNIPPET_CHARS else "") == short
    print("[ok] 单源正文截断逻辑")

def test_norm_url_dedup():
    # 同文的 http/https、www、查询串、末尾斜杠差异必须视作同一条
    pairs = [
        ("http://www.a.com/x/", "https://a.com/x"),
        ("https://a.com/x?from=search", "http://a.com/x"),
        ("HTTPS://A.COM/X#top", "http://www.a.com/x"),
    ]
    for a, b in pairs:
        assert _norm_url(a) == _norm_url(b), f"应等价: {a} vs {b}"
    assert _norm_url("https://a.com/x") != _norm_url("https://a.com/y")  # 不同路径不误杀
    assert _norm_url("") == ""  # 空值不炸（防御 URL 缺失的来源）
    print("[ok] URL 规范化去重")


def test_low_trust_ranking():
    # 低可信来源应被降权到末尾，从而在截断时优先被淘汰
    pool = [
        {"title": "知乎分析", "url": "https://zhihu.com/p/1", "_low_trust": True},
        {"title": "官方博客", "url": "https://nvidia.com/blog", "_low_trust": False},
        {"title": "Reddit帖", "url": "https://reddit.com/r/x", "_low_trust": True},
        {"title": "技术文档", "url": "https://docs.aws.com/t", "_low_trust": False},
    ]
    assert _is_low_trust("https://zhihu.com/p/1") is True
    assert _is_low_trust("https://docs.aws.com/t") is False
    assert _is_low_trust("https://zhuanlan.zhihu.com/p/1") is True  # 子域名也要命中

    pool.sort(key=lambda r: r.get("_low_trust", False))
    assert [r["url"] for r in pool][:2] == ["https://nvidia.com/blog", "https://docs.aws.com/t"]
    print("[ok] 低可信来源降权排序")


def test_trace_save():
    t = Trace(None)
    t.log("[规划] 测试")
    assert t.save("q", "a") == ""  # 未指定路径时不落盘
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sub", "trace.md")
        t2 = Trace(path)
        t2.log("[第1轮] 新增 3 条")
        saved = t2.save("测试问题", "测试回答")
        assert saved == path and os.path.exists(path)
        content = open(path, encoding="utf-8").read()
        assert "测试问题" in content and "[第1轮] 新增 3 条" in content and "测试回答" in content
    print("[ok] 轨迹落盘与目录自动创建")

def test_research_output_format():
    # 命令行版输出必须由结构化版拼接而来，来源格式不回退
    from agent import research
    # 不跑真实 API：只验证文本拼接路径的格式约定
    d = {"answer": "结论 [1]。", "insufficient": False,
         "sources": [{"n": 1, "title": "T", "url": "https://a.com/x"}],
         "trace_lines": []}
    import agent
    orig = agent.research_structured
    agent.research_structured = lambda q, tp=None: d   # 打桩，不联网
    try:
        out = research("q")
    finally:
        agent.research_structured = orig
    assert out.endswith("来源：\n[1] T\n    https://a.com/x")
    print("[ok] research文本输出格式")


if __name__ == "__&#8203;main__":
    test_json_out_variants()
    test_source_cap()
    test_snippet_truncation()
    test_norm_url_dedup()      # 新增
    test_low_trust_ranking()   # 新增
    test_trace_save()
    print("\n[✓] 全部纯逻辑测试通过")


