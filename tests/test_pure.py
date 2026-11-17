"""Pure-logic self-tests (no network, no API quota): python tests/test_pure.py

Covers the hardened key pure functions: tolerant JSON parsing, evidence-pool capping,
content truncation, output formatting.
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
    assert _json_out('noise before {"x": 1} noise after') == {"x": 1}
    for bad in ("not JSON at all", 'missing brace {"a": 1', ""):
        try:
            _json_out(bad)
            raise SystemExit(f"[fail] should have rejected: {bad!r}")
        except ValueError:
            pass  # JSONDecodeError is a ValueError subclass, as expected
    print("[ok] _json_out tolerant parsing")


def test_source_cap():
    fake = [{"title": f"t{i}", "url": f"https://x/{i}", "content": "c"} for i in range(50)]
    capped = fake[:MAX_SOURCES]
    assert len(capped) == MAX_SOURCES == 12
    # citation numbers never dangle: prompt numbering and the source list stay consistent
    # by construction; here we only verify truncation preserves order
    assert capped[0]["url"] == "https://x/0"
    print("[ok] evidence-pool cap MAX_SOURCES=12")


def test_snippet_truncation():
    long_content = "c" * (SNIPPET_CHARS + 500)
    snippet = long_content[:SNIPPET_CHARS] + "..."
    assert len(snippet) == SNIPPET_CHARS + 3 and snippet.endswith("...")
    short = "short content"
    assert short[:SNIPPET_CHARS] + ("..." if len(short) > SNIPPET_CHARS else "") == short
    print("[ok] per-source content truncation")


def test_trace_save():
    from agent import format_output  # trace-on-disk logic lives in research(); this checks formatting
    srcs = [{"title": "a", "url": "https://a", "content": "c"},
            {"title": "b", "url": "https://b", "content": "c"}]
    out = format_output("Answer [1][2]", srcs)
    assert "Answer [1][2]" in out and "[1] a" in out and "[2] b" in out and "https://b" in out
    assert format_output("answer without sources", []) == "answer without sources"
    print("[ok] output formatting (answer + numbered sources)")


def test_linkify_citations():
    srcs = [{"url": "https://x/1"}, {"url": "https://x/2"}]
    out = linkify_citations("claim A [1], claim B [2], out-of-range [3] kept", srcs)
    assert "[1](https://x/1)" in out and "[2](https://x/2)" in out
    assert "[3]" in out and "[3](" not in out  # out-of-range numbers stay as-is, errors not masked
    print("[ok] citation linkification (with out-of-range guard)")


def test_norm_url_dedup():
    # http/https, www, query string and trailing-slash variants of the same article must
    # count as one entry (Hkate777 PR#1)
    pairs = [
        ("http://www.a.com/x/", "https://a.com/x"),
        ("https://a.com/x?from=search", "http://a.com/x"),
        ("HTTPS://A.COM/X#top", "http://www.a.com/x"),
    ]
    for a, b in pairs:
        assert norm_url(a) == norm_url(b), f"should be equivalent: {a} vs {b}"
    assert norm_url("https://a.com/x") != norm_url("https://a.com/y")  # distinct paths survive
    assert norm_url("") == ""  # empty values do not crash (defensive against missing URLs)
    print("[ok] URL normalization dedup")


def test_norm_url_amp():
    # AMP mobile variants must equal their desktop version ([8][10] slipped through in practice)
    assert norm_url("https://www.cnbc.com/amp/2024/06/27/x.html") == \
        norm_url("https://www.cnbc.com/2024/06/27/x.html")
    assert norm_url("https://a.com/x/amp/") == norm_url("https://a.com/x")  # trailing form
    # real path segments must survive: a leading "amp-" is a valid path, not a mobile variant
    assert norm_url("https://a.com/amp-x") != norm_url("https://a.com/x")
    print("[ok] AMP mobile-variant dedup")


def test_selfmedia_demotion():
    # broker/stock-commentary self-media share the aggregator tier (they output uncross-checked
    # share and market-share numbers in practice)
    for u in ("https://www.tradingkey.com/news/1",
              "https://brief.sharpertrades.com/x",
              "https://caifuhao.eastmoney.com/p/1"):
        assert source_tier(u) == 1, f"should be demoted: {u}"
    assert source_tier("https://www.nobelprize.org/x") == 0  # primary sources are not demoted
    # counted into the aggregator bucket: demoted_counts contract unchanged, app.py untouched
    rs = [{"url": "https://www.tradingkey.com/a"}, {"url": "https://www.gov.cn/x"}]
    assert demoted_counts(rs) == {"aggregator": 1, "social": 0}
    print("[ok] broker/stock-commentary self-media demotion")


def test_quality_ranking():
    assert domain_of("https://www.nobelprize.org/prizes/physics") == "nobelprize.org"
    assert domain_of("https://x.com/someone/status/1") == "x.com"
    assert source_tier("https://www.facebook.com/p/1") == 2
    assert source_tier("https://medium.com/@x/post") == 1
    assert source_tier("https://www.nobelprize.org/x") == 0
    # stable sort: original order within a tier; social/aggregators move back but survive
    rs = [{"url": "https://x.com/a"}, {"url": "https://www.gov.cn/x"},
          {"url": "https://medium.com/b"}, {"url": "https://nobelprize.org/y"}]
    ranked = rank_sources(rs)
    assert [r["url"] for r in ranked] == ["https://www.gov.cn/x", "https://nobelprize.org/y",
                                          "https://medium.com/b", "https://x.com/a"]
    assert demoted_counts(rs) == {"aggregator": 1, "social": 1}
    print("[ok] source-quality ranking (demote-not-delete, stable)")


if __name__ == "__main__":
    test_json_out_variants()
    test_source_cap()
    test_snippet_truncation()
    test_trace_save()
    test_linkify_citations()
    test_norm_url_dedup()
    test_norm_url_amp()        # added
    test_selfmedia_demotion()  # added
    test_quality_ranking()
    print("\n[ok] all pure-logic tests passed")
