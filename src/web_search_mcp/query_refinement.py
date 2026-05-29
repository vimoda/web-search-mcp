_SIMPLE_QUERY_MAX_WORDS = 3

_AMBIGUOUS_ACRONYMS = {"api", "sdk", "cli", "mcp", "ftp", "ssh", "http", "tcp",
                       "dns", "ssl", "db", "ui", "ux", "gui", "json", "xml",
                       "csv", "yaml", "toml", "sql", "orm", "aws", "gcp", "az"}

_REFINEMENT_BY_TYPE: dict[str, list[str]] = {
    "person": [
        "who is {query}",
        "{query} professional profile",
        "{query} CEO founder",
        "{query} LinkedIn biography",
    ],
    "company": [
        "{query} company official",
        "{query} founder CEO",
        "{query} LinkedIn",
        "{query} Crunchbase funding",
    ],
    "technical": [
        "{query} documentation",
        "{query} GitHub",
        "{query} API reference",
        "{query} tutorial examples",
    ],
    "news": [
        "{query} latest news",
        "{query} 2026 update",
        "{query} today recent",
    ],
    "general": [
        "{query} official",
        "{query} overview",
        "{query} profile",
        "{query} background",
    ],
}


def _is_simple_or_ambiguous_query(query: str, search_context: str | None = None) -> tuple[bool, str]:
    q = query.strip()

    if len(q.split()) == 1:
        words = q.lower()
        if words in _AMBIGUOUS_ACRONYMS or words in ("python", "java", "go", "rust", "cpp", "js", "ts"):
            return True, f"Short/acronym query \"{q}\" needs context: docs, official, or reference."
        return True, f"Single-word query \"{q}\" is generic. Add context based on intent."

    words = q.split()
    if len(words) <= 2:
        if all(w[0].isupper() for w in words if w[0].isalpha()):
            return True, f"Short name/entity query \"{q}\" needs professional/research context."
        if any(kw in q.lower() for kw in
               ("linkedin", "ceo", "founder", "company", "official",
                "docs", "documentation", "github", "api", "news",
                "latest", "profile", "biography", "funding",
                "tutorial", "reference", "guide")):
            return False, ""
        if not search_context:
            return True, f"Short query \"{q}\" may be ambiguous. Add context for better results."

    if len(words) <= 2 and not search_context:
        return True, f"Short generic query \"{q}\" needs subject context."

    if not search_context and not any(kw in q.lower() for kw in
                                      ("linkedin", "ceo", "founder", "company", "official",
                                       "docs", "documentation", "github", "api", "news",
                                       "latest", "profile", "biography", "funding",
                                       "tutorial", "reference", "guide")):
        return True, f"Query \"{q}\" lacks intent keywords. Adding research context."

    return False, ""


def _refine_query(query: str, query_type: str, purpose: str,
                  search_context: str | None = None) -> str:
    is_simple, reason = _is_simple_or_ambiguous_query(query, search_context)
    if not is_simple:
        return query

    refinements = _REFINEMENT_BY_TYPE.get(query_type, _REFINEMENT_BY_TYPE["general"])
    refined = query

    for tmpl in refinements:
        candidate = tmpl.format(query=query)
        if candidate.lower() != query.lower():
            refined = candidate
            break

    if search_context and search_context not in refined:
        refined = f"{refined} ({search_context})"

    return refined
