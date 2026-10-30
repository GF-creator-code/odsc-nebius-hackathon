"""来源质量排序（通用，不绑定任何专业领域）

只按"来源结构属性"降权，不做领域判断：社交平台与内容聚合站的证据可靠性
通常低于一手来源。**只降权、不删除**——被降权的来源仍留在池中（证据完整性
优先，排序影响进入综合提示词的优先级与截断顺序）。

新增领域/站点只需改下面的集合；纯函数，测试见 tests/test_pure.py。
"""

SOCIAL = {
    "facebook.com", "x.com", "twitter.com", "reddit.com", "quora.com",
    "tiktok.com", "instagram.com", "weibo.com", "zhihu.com", "tieba.baidu.com",
}
AGGREGATOR = {
    "medium.com", "substack.com", "csdn.net", "jianshu.com", "toutiao.com",
    "163.com", "sohu.com", "baijiahao.baidu.com",
}


def domain_of(url: str) -> str:
    """取注册域名（去 www 等前缀、去路径）。畸形 URL 返回空串。"""
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    except (AttributeError, ValueError):
        return ""
    parts = host.split(".")
    # 处理 co.uk / com.cn 这类双段后缀：保留末三段（够用且简单）
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def source_tier(url: str) -> int:
    """0=普通来源（默认） 1=内容聚合/博客平台 2=社交平台。"""
    d = domain_of(url)
    if d in SOCIAL:
        return 2
    if d in AGGREGATOR:
        return 1
    return 0


def rank_sources(results: list) -> list:
    """稳定排序：tier 升序（一手在前），同 tier 保持原始顺序（搜索相关性序）。"""
    return sorted(results, key=lambda r: source_tier(r.get("url", "")))


def demoted_counts(results: list) -> dict:
    """统计被降权的来源数，供研究轨迹展示（不静默）。"""
    tiers = [source_tier(r.get("url", "")) for r in results]
    return {"aggregator": tiers.count(1), "social": tiers.count(2)}
