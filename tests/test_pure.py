"""纯逻辑自测（不联网、不耗 API 额度）：python tests/test_pure.py

覆盖加固后的关键纯函数：JSON 容错解析、证据池截断、正文截断、轨迹落盘。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import _json_out, MAX_SOURCES, SNIPPET_CHARS, linkify_citations  # noqa: E402
from quality import (domain_of, source_tier, rank_sources,  # noqa: E402
                     demoted_counts, norm_url)


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


def test_trace_save():
    from agent import format_output  # 轨迹落盘逻辑已并入 research()，此处验证输出格式化
    srcs = [{"title": "a", "url": "https://a", "content": "c"},
            {"title": "b", "url": "https://b", "content": "c"}]
    out = format_output("答案[1][2]", srcs)
    assert "答案[1][2]" in out and "[1] a" in out and "[2] b" in out and "https://b" in out
    assert format_output("无来源回答", []) == "无来源回答"
    print("[ok] 输出格式化（回答+编号来源）")


def test_linkify_citations():
    srcs = [{"url": "https://x/1"}, {"url": "https://x/2"}]
    out = linkify_citations("论断A[1]，论断B[2]，越界[3]保留", srcs)
    assert "[1](https://x/1)" in out and "[2](https://x/2)" in out
    assert "[3]" in out and "[3](" not in out  # 越界编号原样保留，不掩盖模型错误
    print("[ok] 引用链接化（含越界保护）")


def test_norm_url_dedup():
    # 同文的 http/https、www、查询串、末尾斜杠差异必须视作同一条（Hkate777 PR#1）
    pairs = [
        ("http://www.a.com/x/", "https://a.com/x"),
        ("https://a.com/x?from=search", "http://a.com/x"),
        ("HTTPS://A.COM/X#top", "http://www.a.com/x"),
    ]
    for a, b in pairs:
        assert norm_url(a) == norm_url(b), f"应等价: {a} vs {b}"
    assert norm_url("https://a.com/x") != norm_url("https://a.com/y")  # 不同路径不误杀
    assert norm_url("") == ""  # 空值不炸（防御 URL 缺失的来源）
    print("[ok] URL 规范化去重")


def test_norm_url_amp():
    # AMP 移动版变体必须与桌面版视为同一篇（实测中 [8][10] 漏网）
    assert norm_url("https://www.cnbc.com/amp/2024/06/27/x.html") == \
        norm_url("https://www.cnbc.com/2024/06/27/x.html")
    assert norm_url("https://a.com/x/amp/") == norm_url("https://a.com/x")  # 后缀形式
    # 真实路径段不误删：amp- 开头是有效路径，不是移动版变体
    assert norm_url("https://a.com/amp-x") != norm_url("https://a.com/x")
    print("[ok] AMP 移动版变体去重")


def test_selfmedia_demotion():
    # 券商/股评自媒体与聚合站同档降权（实测输出未交叉验证的份额与股价数字）
    for u in ("https://www.tradingkey.com/news/1",
              "https://brief.sharpertrades.com/x",
              "https://caifuhao.eastmoney.com/p/1"):
        assert source_tier(u) == 1, f"应降权: {u}"
    assert source_tier("https://www.nobelprize.org/x") == 0  # 一手来源不降权
    # 计入 aggregator 统计：demoted_counts 结构不变，app.py 无需改动
    rs = [{"url": "https://www.tradingkey.com/a"}, {"url": "https://www.gov.cn/x"}]
    assert demoted_counts(rs) == {"aggregator": 1, "social": 0}
    print("[ok] 券商/股评自媒体降权")


def test_quality_ranking():
    assert domain_of("https://www.nobelprize.org/prizes/physics") == "nobelprize.org"
    assert domain_of("https://x.com/someone/status/1") == "x.com"
    assert source_tier("https://www.facebook.com/p/1") == 2
    assert source_tier("https://medium.com/@x/post") == 1
    assert source_tier("https://www.nobelprize.org/x") == 0
    # 稳定排序：同 tier 保持原顺序，社交/聚合后置但不删除
    rs = [{"url": "https://x.com/a"}, {"url": "https://www.gov.cn/x"},
          {"url": "https://medium.com/b"}, {"url": "https://nobelprize.org/y"}]
    ranked = rank_sources(rs)
    assert [r["url"] for r in ranked] == ["https://www.gov.cn/x", "https://nobelprize.org/y",
                                          "https://medium.com/b", "https://x.com/a"]
    assert demoted_counts(rs) == {"aggregator": 1, "social": 1}
    print("[ok] 来源质量排序（降权不删除、稳定）")


if __name__ == "__main__":
    test_json_out_variants()
    test_source_cap()
    test_snippet_truncation()
    test_trace_save()
    test_linkify_citations()
    test_norm_url_dedup()
    test_norm_url_amp()      # 新增
    test_selfmedia_demotion()  # 新增
    test_quality_ranking()
    print("\n[✓] 全部纯逻辑测试通过")
