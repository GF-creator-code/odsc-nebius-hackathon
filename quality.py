"""Source-quality ranking (generic, domain-agnostic).

Demotes only by structural source attributes, never by domain judgment: social platforms
and content aggregators are generally less reliable than primary sources. **Demote only,
never delete** -- demoted sources stay in the pool (evidence completeness first; ranking
affects their priority in the synthesis prompt and their truncation order).

To add domains, edit the sets below. Pure functions; tests in tests/test_pure.py.
"""

SOCIAL = {
    "facebook.com", "x.com", "twitter.com", "reddit.com", "quora.com",
    "tiktok.com", "instagram.com", "weibo.com", "zhihu.com", "tieba.baidu.com",
}
AGGREGATOR = {
    "medium.com", "substack.com", "csdn.net", "jianshu.com", "toutiao.com",
    "163.com", "sohu.com", "baijiahao.baidu.com",
}
# Broker notes / stock-commentary / advisory self-media: typically restate second-hand data
# and give share-price or market-share numbers without a primary source. In practice they
# floated to the top of the evidence pool with uncross-checked claims (e.g. "AMD up 125%"),
# so they share the aggregator tier (tier 1). Still demote-only, never delete -- their
# industry commentary can occasionally add value.
SELFMEDIA = {
    "tradingkey.com", "sharpertrades.com", "datamintelligence.com",
    "dataknobs.com", "oplexa.com", "siliconanalysts.com",
    "investing.com", "benzinga.com", "stocktwits.com", "eastmoney.com",
}


def norm_url(url: str) -> str:
    """URL normalization (the dedup key): flattens protocol, www, trailing slash,
    query string and fragment differences.

    The same article is often indexed twice under http/https; deduping by raw URL wastes
    two source slots ([7][8] were the same article in practice). After normalization the
    two are equivalent; distinct paths are untouched. Improvement from Hkate777 PR#1.
    """
    u = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
            break
    if u.startswith("www."):
        u = u[4:]
    u = u.rstrip("/").split("#")[0].split("?")[0]
    # AMP mobile and desktop versions are the same article:
    # /amp/2024/06/27/x == /2024/06/27/x. Only a standalone "amp" path segment is dropped;
    # real segments starting with "amp-" are unaffected.
    host, _, path = u.partition("/")
    segs = [s for s in path.split("/") if s and s != "amp"]
    return host + ("/" + "/".join(segs) if segs else "")


def domain_of(url: str) -> str:
    """Registered domain (strip www etc. and path). Malformed URLs return an empty string."""
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    except (AttributeError, ValueError):
        return ""
    parts = host.split(".")
    # handle two-part suffixes like co.uk / com.cn: keep the last three labels (good enough)
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def source_tier(url: str) -> int:
    """0 = ordinary source (default), 1 = content aggregator / blog platform / self-media,
    2 = social platform."""
    d = domain_of(url)
    if d in SOCIAL:
        return 2
    if d in AGGREGATOR or d in SELFMEDIA:
        return 1
    return 0


def rank_sources(results: list) -> list:
    """Stable sort: ascending tier (primary sources first), original order preserved within
    a tier (search-relevance order)."""
    return sorted(results, key=lambda r: source_tier(r.get("url", "")))


def demoted_counts(results: list) -> dict:
    """Count demoted sources, for display in the research trace (never silent)."""
    tiers = [source_tier(r.get("url", "")) for r in results]
    return {"aggregator": tiers.count(1), "social": tiers.count(2)}
