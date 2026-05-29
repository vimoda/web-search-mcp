import urllib.parse


def _get_domain(url: str) -> str:
    domain = urllib.parse.urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    path = parsed.path.rstrip("/") or "/"
    query = urllib.parse.parse_qs(parsed.query)
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                       "fbclid", "gclid", "gclsrc", "dclid", "ref", "source"}
    cleaned_query = {k: v for k, v in query.items() if k not in tracking_params}
    query_string = urllib.parse.urlencode(cleaned_query, doseq=True) if cleaned_query else ""
    normalized = f"{domain}{path}"
    if query_string:
        normalized += f"?{query_string}"
    return normalized


def _deduplicate(results: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        key = _normalize_url(r["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped
