PERSON_EXPANSIONS = [
    "{query}",
    "{query} LinkedIn",
    "{query} CEO",
    "{query} founder",
    "{query} profile",
    "{query} biography",
]

COMPANY_EXPANSIONS = [
    "{query}",
    "{query} official",
    "{query} LinkedIn",
    "{query} Crunchbase",
    "{query} funding",
    "{query} news",
]

TECH_EXPANSIONS = [
    "{query}",
    "{query} documentation",
    "{query} GitHub",
    "{query} tutorial",
    "{query} API",
    "{query} examples",
]

NEWS_EXPANSIONS = [
    "{query}",
    "{query} latest",
    "{query} 2026",
    "{query} news",
    "{query} update",
]

GENERAL_EXPANSIONS = [
    "{query}",
    "{query} official",
    "{query} profile",
    "{query} biography",
    "{query} company",
    "{query} career",
]

PURPOSE_EXPANSIONS = {
    "answer": [],
    "verify": ["{query} source", "{query} evidence", "{query} fact check", "{query} official"],
    "complement": ["{query} background", "{query} overview", "{query} summary", "{query} introduction"],
    "current_info": ["{query} latest", "{query} 2026", "{query} news", "{query} update"],
    "sources": ["{query} source", "{query} citation", "{query} reference", "{query} references"],
    "explore": [],
}


def _expand_queries(query: str, depth: str, purpose: str = "answer", query_type: str = "general") -> list[str]:
    base_queries = [query]
    expansions_needed = {"quick": 1, "standard": 3, "deep": 6}.get(depth, 3)

    type_map = {
        "person": PERSON_EXPANSIONS,
        "company": COMPANY_EXPANSIONS,
        "technical": TECH_EXPANSIONS,
        "news": NEWS_EXPANSIONS,
        "general": GENERAL_EXPANSIONS,
    }
    type_expansions = type_map.get(query_type, GENERAL_EXPANSIONS)

    for tpl in type_expansions:
        if len(base_queries) >= expansions_needed:
            break
        q = tpl.format(query=query)
        if q != query and q not in base_queries:
            base_queries.append(q)

    purpose_extra = PURPOSE_EXPANSIONS.get(purpose, [])
    for tpl in purpose_extra:
        if len(base_queries) >= expansions_needed:
            break
        q = tpl.format(query=query)
        if q not in base_queries:
            base_queries.append(q)

    return base_queries[:expansions_needed]


def _build_followup_queries(query: str, query_type: str, discovered: list[str], depth: str) -> list[str]:
    needs = {"quick": 0, "standard": 2, "deep": 5}.get(depth, 2)
    if not discovered or needs == 0:
        return []

    queries: list[str] = []
    for term in discovered:
        if len(queries) >= needs:
            break
        q = f"{query} {term}"
        if q not in queries:
            queries.append(q)

    return queries
