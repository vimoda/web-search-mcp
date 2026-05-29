import re
from .url_utils import _get_domain

LOW_QUALITY_DOMAINS: dict[str, str] = {
    "instagram.com": "social media, limited accessible content",
    "facebook.com": "social media, limited accessible content",
    "tiktok.com": "social media, limited accessible content",
    "pinterest.com": "social media, limited accessible content",
    "x.com": "social media, limited accessible content",
    "twitter.com": "social media, limited accessible content",
}

HIGH_QUALITY_DOMAINS: dict[str, str] = {
    "linkedin.com": "professional profile",
    "wikipedia.org": "encyclopedic source",
    "bloomberg.com": "news source",
    "reuters.com": "news source",
}

OFFICIAL_DOMAIN_PATTERNS = [
    r"\.(gov|gob|edu|org)\.[a-z]{2}$",
    r"^([a-z]+\.)?(github\.io|readthedocs\.io|medium\.com)$",
    r"stackoverflow\.com$",
]


def _score_source(
    query: str,
    url: str,
    snippet: str,
    content: str | None = None,
    title: str = "",
    discovered_terms: list[str] | None = None,
) -> dict:
    domain = _get_domain(url)
    reasons: list[str] = []
    score = 0.5

    for low_domain, reason in LOW_QUALITY_DOMAINS.items():
        if low_domain in domain:
            return {
                "score": 0.1,
                "quality": "low",
                "reason": reason,
                "ranking_reasons": [f"low quality domain: {reason}"],
            }

    for high_domain, reason in HIGH_QUALITY_DOMAINS.items():
        if high_domain in domain:
            score = 0.85
            reasons.append(reason)
            break

    for pattern in OFFICIAL_DOMAIN_PATTERNS:
        if re.search(pattern, domain):
            score = max(score, 0.8)
            reasons.append("official or authoritative domain")
            break

    query_lower = query.lower()
    text_lower = title.lower() if title else ""
    if snippet:
        text_lower += " " + snippet.lower()

    query_words = set(query_lower.split())
    text_words = set(text_lower.split())
    common = query_words & text_words

    if len(common) >= len(query_words) * 0.5:
        score = min(score + 0.1, 1.0)
        reasons.append("query words matched content")

    if discovered_terms:
        matched_entities = [t for t in discovered_terms if t.lower() in text_lower]
        if len(matched_entities) >= 3:
            score = min(score + 0.25, 1.0)
            reasons.append(f"relates to {len(matched_entities)} discovered entities")
        elif len(matched_entities) >= 1:
            score = min(score + 0.12, 1.0)
            reasons.append("mentions discovered entity")

    if not snippet or len(snippet.strip()) < 30:
        reasons.append("very short or empty snippet")
    else:
        score = min(score + 0.05, 1.0)
        reasons.append("snippet available")

    if content:
        content_len = len(content.strip())
        if content_len >= 100:
            score = min(score + 0.15, 1.0)
            reasons.append("full content extracted")
        else:
            reasons.append("fetched content too short")

    if score >= 0.75:
        quality = "high"
    elif score >= 0.35:
        quality = "medium"
    else:
        quality = "low"

    return {
        "score": round(score, 2),
        "quality": quality,
        "reason": reasons[0] if reasons else "standard web source",
        "ranking_reasons": reasons,
    }
