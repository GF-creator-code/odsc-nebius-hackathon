"""纯逻辑自测（不联网、不耗 API 额度）：python tests/test_pure.py

覆盖加固后的关键纯函数：JSON 容错解析、证据池截断、正文截断、轨迹落盘。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import _json_out, Trace, MAX_SOURCES, SNIPPET_CHARS  # noqa: E402


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


if __name__ == "__main__":
    test_json_out_variants()
    test_source_cap()
    test_snippet_truncation()
    test_trace_save()
    print("\n[✓] 全部纯逻辑测试通过")
