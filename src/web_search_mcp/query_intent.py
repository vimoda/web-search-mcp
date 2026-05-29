PERSON_KEYWORDS = {"linkedin", "profile", "biography", "biografía", "person", "founder",
                   "ceo", "cto", "co-founder"}
COMPANY_KEYWORDS = {"company", "empresa", "startup", "inc", "corp", "ltd", "funding",
                    "crunchbase", "official"}
TECH_KEYWORDS = {"api", "docs", "documentation", "library", "npm", "pypi", "github",
                 "stackoverflow", "error", "bug", "tutorial", "sdk", "cli"}
NEWS_KEYWORDS = {"news", "noticias", "latest", "update", "recent", "2024", "2025", "2026",
                 "today", "yesterday", "announcement"}


def _detect_query_type(query: str, search_context: str | None = None) -> str:
    text = f"{query} {search_context or ''}".lower()

    person_score = sum(2 for kw in PERSON_KEYWORDS if f" {kw} " in f" {text} ")
    company_score = sum(2 for kw in COMPANY_KEYWORDS if f" {kw} " in f" {text} ")
    tech_score = sum(2 for kw in TECH_KEYWORDS if f" {kw} " in f" {text} ")
    news_score = sum(2 for kw in NEWS_KEYWORDS if kw in text)

    if tech_score > 0 and tech_score >= company_score and tech_score >= person_score and tech_score >= news_score:
        return "technical"
    if news_score > 0 and news_score >= person_score and news_score >= company_score:
        return "news"
    if person_score >= company_score and person_score > 0:
        return "person"
    if company_score > 0:
        return "company"

    words = query.strip().split()
    if len(words) <= 4 and all(w[0].isupper() for w in words if w[0].isalpha()):
        return "person"

    person_question_prefixes = ("who is", "who was", "who are", "who were",
                                "tell me about", "tell me who", "quién es",
                                "quien es", "quién fue", "quien fue")
    if any(query.lower().startswith(p) for p in person_question_prefixes):
        return "person"

    return "general"
