"""
Web Search MCP Server
Búsqueda web sin APIs de pago usando DuckDuckGo + crawl4ai.
crawl4ai usa Playwright internamente para soportar páginas con JavaScript.
"""

import json
import os
import asyncio
import logging
import urllib.parse
import re
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
import httpx
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from mcp.server.fastmcp import FastMCP

# ── Constantes (configurables via env vars) ───────────────────────────────────

MAX_TEXT_LENGTH = int(os.getenv("WEB_SEARCH_MAX_CHARS", "4000"))
SEARCH_REGION   = os.getenv("WEB_SEARCH_REGION", "mx-es")
REQUEST_TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "15"))
WEB_SEARCH_DEFAULT_DEPTH = os.getenv("WEB_SEARCH_DEFAULT_DEPTH", "standard")
WEB_SEARCH_MAX_CONCURRENT_FETCHES = int(os.getenv("WEB_SEARCH_MAX_CONCURRENT_FETCHES", "3"))
WEB_SEARCH_FETCH_TIMEOUT = int(os.getenv("WEB_SEARCH_FETCH_TIMEOUT", "20"))
LOG_LEVEL = os.getenv("WEB_SEARCH_LOG_LEVEL", "")

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_SILENT = LOG_LEVEL.upper().strip() in ("OFF", "SILENT", "")

# ── Inicialización ────────────────────────────────────────────────────────────

mcp_log_level = "CRITICAL" if _SILENT else LOG_LEVEL.upper().strip()
mcp = FastMCP("web_search_mcp", log_level=mcp_log_level)

# ── Logger de la app ──────────────────────────────────────────────────────────

log = logging.getLogger("web-search-mcp")
log.propagate = False
_configured_level = LOG_LEVELS.get(LOG_LEVEL.upper().strip())
if _SILENT:
    log.disabled = True
    log.setLevel(logging.CRITICAL + 1)
    for _name in ("mcp", "httpx", "httpcore"):
        _l = logging.getLogger(_name)
        _l.disabled = True
        _l.setLevel(logging.CRITICAL + 1)
        _l.propagate = False
else:
    log.disabled = False
    log.setLevel(_configured_level)
    handler = logging.StreamHandler()
    handler.setLevel(_configured_level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    log.addHandler(handler)
    for _name in ("httpx", "httpcore"):
        _l = logging.getLogger(_name)
        _l.setLevel(_configured_level)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

DDGS_SEARCH_URL = "https://html.duckduckgo.com/html/"

# ── Concurrencia ──────────────────────────────────────────────────────────────

_fetch_semaphore = asyncio.Semaphore(WEB_SEARCH_MAX_CONCURRENT_FETCHES)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _handle_http_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 403:
            return f"Error 403: Access denied by the site (possible bot blocking)."
        if code == 404:
            return "Error 404: Page not found."
        if code == 429:
            return "Error 429: Rate limit reached. Wait a few seconds."
        return f"Error HTTP {code}: {e.response.reason_phrase}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Timeout connecting to the server."
    if isinstance(e, httpx.ConnectError):
        return "Error: Could not connect. Check the URL or your connection."
    return f"Unexpected error: {type(e).__name__}: {e}"


async def _ddg_search(query: str, max_results: int) -> list[dict]:
    """
    Search DuckDuckGo (HTML endpoint) and return a list of results.
    Each result has: title, url, snippet.
    """
    log.info("Searching: \"%s\" (max=%d, region=%s)", query, max_results, SEARCH_REGION)
    async with httpx.AsyncClient(headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        r = await client.post(DDGS_SEARCH_URL, data={"q": query, "kl": SEARCH_REGION})
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for result in soup.select(".result")[:max_results]:
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        # DuckDuckGo a veces wrappea la URL — la limpiamos
        if url.startswith("//duckduckgo.com/l/?uddg="):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = urllib.parse.unquote(qs.get("uddg", [url])[0])

        if url and title:
            results.append({"title": title, "url": url, "snippet": snippet})

    log.info("Results for \"%s\": %d", query, len(results))
    return results


# ── Extracción con fallback ───────────────────────────────────────────────────

async def _fetch_page(url: str, max_chars: int = MAX_TEXT_LENGTH) -> str:
    """Fetch a URL with crawl4ai (JS support) and return clean markdown."""
    log.info("Fetching: %s", url)
    config = CrawlerRunConfig(
        word_count_threshold=10,
        exclude_external_links=True,
        remove_overlay_elements=True,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)

    if not result.success:
        raise RuntimeError(result.error_message or "crawl4ai no pudo obtener la página")

    text = result.markdown or result.cleaned_html or ""
    return text[:max_chars]


async def _fetch_page_with_fallback(url: str, max_chars: int = MAX_TEXT_LENGTH) -> dict:
    """Intenta crawl4ai, fallback a httpx+bs4, luego a metadata HTML."""
    method = "none"
    content = ""
    error = None

    # Intento 1: crawl4ai
    try:
        async with _fetch_semaphore:
            content = await _fetch_page(url, max_chars)
        if content and len(content.strip()) > 100:
            return {"content": content, "method": "crawl4ai", "error": None}
        method = "crawl4ai (partial)"
    except Exception as e:
        error = str(e)
        method = "crawl4ai (failed)"

    # Intento 2: httpx + BeautifulSoup
    try:
        async with _fetch_semaphore:
            async with httpx.AsyncClient(
                headers={**HEADERS, "Accept": "text/html"},
                timeout=WEB_SEARCH_FETCH_TIMEOUT,
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        if text and len(text) > 100:
            return {"content": text[:max_chars], "method": "httpx+bs4", "error": None}

        method = "httpx+bs4 (partial)"
    except Exception as e2:
        if not error:
            error = str(e2)
        method = "httpx+bs4 (failed)"

    # Intento 3: metadata HTML (title + description + og tags)
    try:
        soup = BeautifulSoup(r.text, "html.parser") if 'soup' in dir() else BeautifulSoup("", "html.parser")
        if not soup.get_text(strip=True):
            async with httpx.AsyncClient(timeout=WEB_SEARCH_FETCH_TIMEOUT, follow_redirects=True) as client:
                r = await client.get(url, headers=HEADERS)
                soup = BeautifulSoup(r.text, "html.parser")

        meta_parts = []
        title = soup.find("title")
        if title:
            meta_parts.append(title.get_text(strip=True))
        for name in ("description", "og:description", "og:title"):
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                meta_parts.append(tag["content"].strip())

        content = " — ".join(meta_parts) if meta_parts else ""
        if content:
            return {"content": content[:max_chars], "method": "html metadata", "error": None}
    except Exception:
        pass

    return {"content": "", "method": method, "error": error or "no content extracted"}


# ── Calidad de fuentes y expansión de búsqueda ───────────────────────────────

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


def _get_domain(url: str) -> str:
    domain = urllib.parse.urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _score_source(
    query: str,
    url: str,
    snippet: str,
    content: str | None = None,
    title: str = "",
    discovered_terms: list[str] | None = None,
) -> dict:
    """Score a source and return quality metadata with ranking_reasons."""
    domain = _get_domain(url)
    reasons: list[str] = []
    score = 0.5

    # Penalizar redes sociales
    for low_domain, reason in LOW_QUALITY_DOMAINS.items():
        if low_domain in domain:
            return {
                "score": 0.1,
                "quality": "low",
                "reason": reason,
                "ranking_reasons": [f"low quality domain: {reason}"],
            }

    # Boost para dominios de alta calidad
    for high_domain, reason in HIGH_QUALITY_DOMAINS.items():
        if high_domain in domain:
            score = 0.85
            reasons.append(reason)
            break

    # Boost para dominios oficiales
    for pattern in OFFICIAL_DOMAIN_PATTERNS:
        if re.search(pattern, domain):
            score = max(score, 0.8)
            reasons.append("official or authoritative domain")
            break

    # Query matching contra título
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

    # Boost por entidades descubiertas
    if discovered_terms:
        matched_entities = [t for t in discovered_terms if t.lower() in text_lower]
        if len(matched_entities) >= 3:
            score = min(score + 0.25, 1.0)
            reasons.append(f"relates to {len(matched_entities)} discovered entities")
        elif len(matched_entities) >= 1:
            score = min(score + 0.12, 1.0)
            reasons.append("mentions discovered entity")

    # Snippet corto o vacío
    if not snippet or len(snippet.strip()) < 30:
        reasons.append("very short or empty snippet")
    else:
        score = min(score + 0.05, 1.0)
        reasons.append("snippet available")

    # Contenido extraído
    if content:
        content_len = len(content.strip())
        if content_len >= 100:
            score = min(score + 0.15, 1.0)
            reasons.append("full content extracted")
        else:
            reasons.append("fetched content too short")

    # Calidad final
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


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    path = parsed.path.rstrip("/") or "/"

    # Quitar parámetros de tracking
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
    """Remove duplicate URLs using normalized keys."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        key = _normalize_url(r["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


# ── Extracción de entidades descubiertas ──────────────────────────────────────

_STOP_WORDS = {
    "the", "this", "that", "with", "from", "your", "our", "their", "about",
    "what", "how", "why", "when", "where", "which", "who", "whom", "more",
    "most", "some", "any", "all", "each", "every", "both", "few", "many",
    "much", "such", "only", "own", "same", "so", "than", "too", "very",
    "just", "also", "not", "no", "nor", "none", "nothing", "never", "none",
    "home", "blog", "page", "site", "web", "menu", "login", "sign", "search",
    "news", "article", "contact", "privacy", "terms", "about", "help", "faq",
    "index", "default", "main", "content", "more", "read", "view", "click",
    "https", "http", "www", "com", "org", "net", "html", "php", "jsp",
}


def _extract_discovered_terms(results: list[dict], original_query: str) -> list[str]:
    """Extract notable entities from search results for query refinement.

    Looks for capitalized multi-word terms, notable domain names,
    and entities that appear across multiple results.
    """
    query_words = set(original_query.lower().split())
    text = ""
    for r in results:
        text += f" {r.get('title', '')} {r.get('snippet', '')}"
        url = r.get('url', '')
        parsed = urllib.parse.urlparse(url)
        path_parts = [
            p for p in parsed.path.split('/')
            if p and not p.startswith(('?', '#'))
        ]
        text += ' ' + ' '.join(path_parts)

    # Proper nouns: capitalized words and acronyms (e.g., "CEO", "Monadic", "T1")
    candidates = re.findall(
        r'\b[A-Z][A-Za-záéíóúñ0-9]+(?:\s[A-Z][A-Za-záéíóúñ0-9]+)*\b',
        text,
    )

    freq: dict[str, int] = {}
    for c in candidates:
        c_lower = c.lower()
        if c_lower in query_words or c_lower in _STOP_WORDS or len(c) < 3:
            continue
        freq[c] = freq.get(c, 0) + 1

    sorted_terms = sorted(freq.items(), key=lambda x: -x[1])

    # Domain-derived names (e.g., "monadic" from monadic.com)
    domains: dict[str, int] = {}
    for r in results:
        domain = _get_domain(r.get('url', ''))
        parts = domain.replace('.com', '').replace('.org', '').replace('.mx', '').split('.')
        for p in parts:
            p_lower = p.lower()
            if p_lower not in query_words and len(p) > 2 and not p.isdigit():
                key = p.capitalize()
                domains[key] = domains.get(key, 0) + 1

    # Merge: terms with freq >= 2 get priority
    terms = [t for t, c in sorted_terms if c >= 2][:6]
    seen_lower = {t.lower() for t in terms}

    for d, c in sorted(domains.items(), key=lambda x: -x[1]):
        if d.lower() not in seen_lower and len(terms) < 8:
            terms.append(d)
            seen_lower.add(d.lower())

    return terms


# ── Refinamiento de queries simples / ambiguas ────────────────────────────────

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
    """Check if the query is too short, generic, or ambiguous to search directly.

    Returns (is_simple, reason).
    """
    q = query.strip()

    # Single word (likely ambiguous or too generic)
    if len(q.split()) == 1:
        words = q.lower()
        if words in _AMBIGUOUS_ACRONYMS or words in ("python", "java", "go", "rust", "cpp", "js", "ts"):
            return True, f"Short/acronym query \"{q}\" needs context: docs, official, or reference."
        return True, f"Single-word query \"{q}\" is generic. Add context based on intent."

    # Two words with only capitalized names → likely a person/entity
    words = q.split()
    if len(words) <= 2:
        if all(w[0].isupper() for w in words if w[0].isalpha()):
            return True, f"Short name/entity query \"{q}\" needs professional/research context."
        # Check if it already has intent keywords
        if any(kw in q.lower() for kw in
               ("linkedin", "ceo", "founder", "company", "official",
                "docs", "documentation", "github", "api", "news",
                "latest", "profile", "biography", "funding",
                "tutorial", "reference", "guide")):
            return False, ""
        if not search_context:
            return True, f"Short query \"{q}\" may be ambiguous. Add context for better results."

    # Two words that are not capitalized → might be generic
    if len(words) <= 2 and not search_context:
        return True, f"Short generic query \"{q}\" needs subject context."

    # No known intent keywords and no search_context
    if not search_context and not any(kw in q.lower() for kw in
                                      ("linkedin", "ceo", "founder", "company", "official",
                                       "docs", "documentation", "github", "api", "news",
                                       "latest", "profile", "biography", "funding",
                                       "tutorial", "reference", "guide")):
        return True, f"Query \"{q}\" lacks intent keywords. Adding research context."

    return False, ""


def _refine_query(query: str, query_type: str, purpose: str,
                  search_context: str | None = None) -> str:
    """Build a refined version of the query by adding context.

    Returns a more descriptive query string.
    """
    is_simple, reason = _is_simple_or_ambiguous_query(query, search_context)
    if not is_simple:
        return query

    # Build refinement from type-specific templates
    refinements = _REFINEMENT_BY_TYPE.get(query_type, _REFINEMENT_BY_TYPE["general"])
    refined = query

    for tmpl in refinements:
        candidate = tmpl.format(query=query)
        if candidate.lower() != query.lower():
            refined = candidate
            # For simple/ambiguous queries, combine up to 3 refinements
            break

    # Add search_context if available
    if search_context and search_context not in refined:
        refined = f"{refined} ({search_context})"

    return refined


# ── Detección de intención ────────────────────────────────────────────────────

PERSON_KEYWORDS = {"linkedin", "profile", "biography", "biografía", "person", "founder",
                   "ceo", "cto", "co-founder"}
COMPANY_KEYWORDS = {"company", "empresa", "startup", "inc", "corp", "ltd", "funding",
                    "crunchbase", "official"}
TECH_KEYWORDS = {"api", "docs", "documentation", "library", "npm", "pypi", "github",
                 "stackoverflow", "error", "bug", "tutorial", "sdk", "cli"}
NEWS_KEYWORDS = {"news", "noticias", "latest", "update", "recent", "2024", "2025", "2026",
                 "today", "yesterday", "announcement"}


def _detect_query_type(query: str, search_context: str | None = None) -> str:
    """Detect intent type using simple keyword matching."""
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

    # Heurística: si el query es corto (2-4 palabras) parece nombre
    words = query.strip().split()
    if len(words) <= 4 and all(w[0].isupper() for w in words if w[0].isalpha()):
        return "person"

    # Heurística: preguntas sobre personas
    person_question_prefixes = ("who is", "who was", "who are", "who were",
                                "tell me about", "tell me who", "quién es",
                                "quien es", "quién fue", "quien fue")
    if any(query.lower().startswith(p) for p in person_question_prefixes):
        return "person"

    return "general"


# ── Expansión de queries ──────────────────────────────────────────────────────

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
    """Generate related queries based on depth, purpose, and query_type."""
    base_queries = [query]
    expansions_needed = {"quick": 1, "standard": 3, "deep": 6}.get(depth, 3)

    # Base expansions by type
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

    # Additional expansions by purpose
    purpose_extra = PURPOSE_EXPANSIONS.get(purpose, [])
    for tpl in purpose_extra:
        if len(base_queries) >= expansions_needed:
            break
        q = tpl.format(query=query)
        if q not in base_queries:
            base_queries.append(q)

    return base_queries[:expansions_needed]


# ── Búsqueda de segunda fase ───────────────────────────────────────────────────

def _build_followup_queries(query: str, query_type: str, discovered: list[str], depth: str) -> list[str]:
    """Build second-pass queries from discovered entities.

    Returns refined queries that combine the original query with discovered
    terms like company names, roles, or related entities.
    """
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


# ── Evidencia ─────────────────────────────────────────────────────────────────

def _compute_evidence_status(
    results: list[dict],
    low_quality: list[dict],
    total_queries: int,
) -> dict:
    """Compute evidence status and recommended action for the LLM."""
    high_count = sum(1 for r in results if r.get("source_quality") == "high" and r.get("content_available"))
    medium_count = sum(1 for r in results if r.get("source_quality") == "medium" and r.get("content_available"))
    low_count = sum(1 for r in results if r.get("source_quality") == "low")
    fetched_count = sum(1 for r in results if r.get("content_available"))

    if high_count >= 2 and fetched_count >= 3:
        status = "strong"
        action = "answer_normally"
        caveat = None
    elif high_count >= 1 or (medium_count >= 2 and fetched_count >= 2):
        status = "partial"
        action = "answer_with_caveat"
        caveat = "Available sources provide some information but may be limited or partial."
    elif fetched_count >= 1 or low_quality:
        status = "weak"
        action = "answer_with_caveat"
        caveat = "Only limited or low-quality sources were found. Consider asking for more details."
    else:
        status = "none"
        action = "ask_for_more_context"
        caveat = "No useful sources were found for this query."

    if action == "answer_normally":
        framing = "Based on the information found on the web"
    elif action == "answer_with_caveat":
        framing = "Based on available sources"
    else:
        framing = ""

    return {
        "evidence_status": status,
        "recommended_action": action,
        "answer_guidance": {
            "should_answer": action != "ask_for_more_context",
            "confidence": {"strong": "high", "partial": "medium", "weak": "low", "none": "none"}.get(status, "unknown"),
            "caveat": caveat,
            "suggested_framing": framing,
        },
    }


# ── Modelos de entrada ────────────────────────────────────────────────────────

class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="Consulta de búsqueda (ej: 'Antar Nakid', 'Python asyncio tutorial', 'latest AI news 2026')",
        min_length=1,
        max_length=300,
    )
    max_results: Optional[int] = Field(
        default=5,
        description="Número máximo de resultados a retornar (1-10)",
        ge=1,
        le=10,
    )
    fetch_content: Optional[bool] = Field(
        default=True,
        description="Si True (default), extrae contenido completo de cada página",
    )
    max_chars_per_result: Optional[int] = Field(
        default=4000,
        description="Máximo de caracteres a retornar por cada página (500-10000)",
        ge=500,
        le=10000,
    )
    depth: Optional[str] = Field(
        default="standard",
        description="Profundidad: 'quick' (rápido), 'standard' (default, 3 queries), 'deep' (exhaustivo, 6 queries)",
    )
    purpose: Optional[str] = Field(
        default="answer",
        description="Propósito: 'answer' (default, responder pregunta), 'verify' (verificar algo), 'complement' (complementar lo conocido), 'current_info' (información reciente), 'sources' (conseguir fuentes/citas), 'explore' (exploración abierta)",
    )
    search_context: Optional[str] = Field(
        default=None,
        description="Contexto adicional para mejorar la búsqueda. Ej: 'The user asks who this person is.'",
        max_length=500,
    )


class LinkSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="Consulta de búsqueda (ej: 'python async tips 2024')",
        min_length=1,
        max_length=300,
    )
    max_results: Optional[int] = Field(
        default=5,
        description="Número máximo de resultados a retornar (1-10)",
        ge=1,
        le=10,
    )


class FetchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    url: str = Field(
        ...,
        description="URL completa a leer (ej: 'https://docs.python.org/3/library/asyncio.html')",
        min_length=10,
    )
    max_chars: Optional[int] = Field(
        default=4000,
        description="Máximo de caracteres a retornar del contenido (100-10000)",
        ge=100,
        le=10000,
    )


class MultiSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    queries: list[str] = Field(
        ...,
        description="Lista de consultas de búsqueda a ejecutar en paralelo",
        min_length=1,
        max_length=5,
    )
    max_results_per_query: Optional[int] = Field(
        default=3,
        description="Resultados por cada query (1-5)",
        ge=1,
        le=5,
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool(
    name="web_search",
    annotations={
        "title": "Web search with iterative research (recommended for external info)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def web_search(params: SearchInput) -> str:
    """Primary tool for external knowledge research. Performs full iterative search internally.

    USE web_search WHEN:
    - The answer may need current, specific, local, obscure, or little-known information.
    - The user asks about a person, company, product, event, API, news, or factual data.
    - The user asks to verify, investigate, compare, cite, or complement knowledge.
    - Your internal knowledge may be incomplete or outdated.
    - You are unsure about the answer and need sources.

    DO NOT USE web_search WHEN:
    - The question is about stable general knowledge (math, physics, basic concepts).
    - The task is writing, translation, or simple reasoning.
    - It is basic programming or well-known algorithms.
    - The user explicitly says not to search.

    IMPORTANT: Do NOT chain multiple calls. This tool runs a complete internal workflow:
      1. Query refinement (detects short/ambiguous queries and adds context).
      2. Multi-query search based on detected intent (person, company, tech, news, general).
      3. Automatic entity discovery (companies, roles, technologies from phase 1 results).
      4. Follow-up search phase with discovered entities.
      5. Content fetching with fallback (crawl4ai -> httpx+bs4 -> HTML metadata).
      6. Source scoring with ranking_reasons and evidence assessment.
      7. Answer guidance: evidence_status, recommended_action, language_instruction.

    LANGUAGE RULE: Always answer in the same language the user is using, unless
    the user explicitly asks you to use a different language.

    If the user query is short, generic, or ambiguous, this tool refines it automatically
    before searching. For example: "Antar Nakid" -> "who is Antar Nakid professional profile".

    Args:
        params (SearchInput):
            - query (str): Search query
            - max_results (int, default: 5): Results to return (1-10)
            - fetch_content (bool, default: true): Fetch full page content
            - max_chars_per_result (int, default: 4000): Characters per page
            - depth (str, default: 'standard'): 'quick' | 'standard' | 'deep'
            - purpose (str, default: 'answer'): 'answer' | 'verify' | 'complement' | 'current_info' | 'sources' | 'explore'
            - search_context (str, optional): Additional context to refine search queries

    Returns:
        str: JSON with:
            - original_query, refined_query, query_was_refined, refinement_reason
            - depth, purpose, searches_performed
            - follow_up_searches_performed (second-phase queries)
            - discovered_terms (entities found in phase 1)
            - evidence_status: 'strong' | 'partial' | 'weak' | 'none'
            - recommended_action: 'answer_normally' | 'answer_with_caveat' | 'ask_for_more_context'
            - answer_guidance: { language_instruction, should_answer, confidence, caveat, suggested_framing }
            - total, results[] (each: title, url, snippet, content, source_quality, score, ranking_reasons, content_available)
            - low_quality_sources[]
    """
    log.info(
        "Tool web_search: query=\"%s\" depth=%s purpose=%s fetch=%s",
        params.query, params.depth, params.purpose, params.fetch_content,
    )

    depth = (params.depth or WEB_SEARCH_DEFAULT_DEPTH).strip().lower()
    if depth not in ("quick", "standard", "deep"):
        depth = "standard"

    purpose = (params.purpose or "answer").strip().lower()
    valid_purposes = {"answer", "verify", "complement", "current_info", "sources", "explore"}
    if purpose not in valid_purposes:
        purpose = "answer"

    try:
        original_query = params.query
        query_type = _detect_query_type(original_query, params.search_context)
        log.info("Query type detected: %s", query_type)

        # ── Query refinement ──
        is_simple, refinement_reason = _is_simple_or_ambiguous_query(
            original_query, params.search_context,
        )
        refined_query = _refine_query(original_query, query_type, purpose, params.search_context)
        query_was_refined = refined_query != original_query

        if query_was_refined:
            log.info(
                "Query refined: \"%s\" -> \"%s\" (reason: %s)",
                original_query, refined_query, refinement_reason,
            )
        search_query = refined_query if query_was_refined else original_query

        # ── Phase 1: initial expanded search ──
        expanded = _expand_queries(search_query, depth, purpose, query_type)
        internal_limit = {
            "quick": params.max_results,
            "standard": params.max_results * 2,
            "deep": params.max_results * 3,
        }.get(depth, params.max_results * 2)

        searches = await asyncio.gather(
            *[_ddg_search(q, internal_limit) for q in expanded],
            return_exceptions=True,
        )

        all_results: list[dict] = []
        search_errors: list[str] = []
        for q, search_result in zip(expanded, searches):
            if isinstance(search_result, Exception):
                search_errors.append(f'"{q}": {_handle_http_error(search_result)}')
                continue
            all_results.extend(search_result)

        # ── Phase 2: discover entities + follow-up queries ──
        discovered: list[str] = []
        followup_searches_performed: list[str] = []

        if all_results:
            discovered = _extract_discovered_terms(all_results, original_query)
            followup_queries = _build_followup_queries(
                search_query, query_type, discovered, depth,
            )

            if followup_queries:
                followup_limit = max(3, internal_limit // 2)
                followup_searches = await asyncio.gather(
                    *[_ddg_search(q, followup_limit) for q in followup_queries],
                    return_exceptions=True,
                )
                for q, search_result in zip(followup_queries, followup_searches):
                    if isinstance(search_result, Exception):
                        search_errors.append(f'"{q}": {_handle_http_error(search_result)}')
                        continue
                    followup_searches_performed.append(q)
                    all_results.extend(search_result)

                log.info(
                    "Phase 2: discovered=%d followups=%d",
                    len(discovered), len(followup_searches_performed),
                )

        if not all_results:
            payload: dict = {
                "original_query": original_query,
                "refined_query": refined_query,
                "query_was_refined": query_was_refined,
                "refinement_reason": refinement_reason if query_was_refined else None,
                "depth": depth,
                "purpose": purpose,
                "searches_performed": expanded,
                "follow_up_searches_performed": followup_searches_performed,
                "discovered_terms": discovered,
                "results": [],
                "evidence_status": "none",
                "recommended_action": "ask_for_more_context",
                "answer_guidance": {
                    "language_instruction": "Answer in the same language as the user.",
                    "should_answer": False,
                    "confidence": "none",
                    "caveat": "No results were found. Consider refining the query.",
                    "suggested_framing": "",
                },
                "message": "No results found.",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Error en web_search: %s", _handle_http_error(e))
        return json.dumps({"error": _handle_http_error(e), "results": []})

    all_searches = expanded + followup_searches_performed

    all_results = _deduplicate(all_results)

    scored = []
    for r in all_results:
        meta = _score_source(
            original_query, r["url"], r.get("snippet", ""),
            title=r.get("title", ""),
            discovered_terms=discovered,
        )
        scored.append((meta["score"], meta, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    to_fetch = scored[: params.max_results]
    low_quality = [s for s in scored[params.max_results:] if s[1]["quality"] == "low"]

    if params.fetch_content:

        async def enrich(item: tuple[float, dict, dict]) -> dict:
            _, meta, r = item
            try:
                fetch_result = await _fetch_page_with_fallback(r["url"], params.max_chars_per_result)
                r["content"] = fetch_result["content"]
                r["extraction_method"] = fetch_result["method"]
                has_content = bool(fetch_result["content"] and len(fetch_result["content"].strip()) >= 100)
                r["content_available"] = has_content
                meta = _score_source(
                    original_query, r["url"], r.get("snippet", ""),
                    fetch_result["content"] if has_content else "",
                    title=r.get("title", ""),
                    discovered_terms=discovered,
                )
            except Exception as e:
                r["content"] = None
                r["content_available"] = False
                r["extraction_method"] = "failed"
            r["source_quality"] = meta["quality"]
            r["score"] = meta["score"]
            r["ranking_reasons"] = meta.get("ranking_reasons", [])
            return r

        final_results = await asyncio.gather(*[enrich(item) for item in to_fetch])
    else:
        final_results = []
        for _, meta, r in to_fetch:
            r["source_quality"] = meta["quality"]
            r["score"] = meta["score"]
            r["ranking_reasons"] = meta.get("ranking_reasons", [])
            r["content_available"] = False
            final_results.append(r)

    low_list = []
    for _, meta, r in low_quality:
        low_list.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "source_quality": meta["quality"],
            "score": meta["score"],
            "reason": meta.get("reason", "low quality source"),
        })

    evidence = _compute_evidence_status(final_results, low_list, len(all_searches))

    payload = {
        "original_query": original_query,
        "refined_query": refined_query,
        "query_was_refined": query_was_refined,
        "refinement_reason": refinement_reason if query_was_refined else None,
        "depth": depth,
        "purpose": purpose,
        "searches_performed": expanded,
        "follow_up_searches_performed": followup_searches_performed,
        "discovered_terms": discovered,
        "total": len(final_results),
        "results": final_results,
        "evidence_status": evidence["evidence_status"],
        "recommended_action": evidence["recommended_action"],
        "answer_guidance": {
            "language_instruction": "Answer in the same language as the user.",
            **evidence["answer_guidance"],
        },
    }
    if low_list:
        payload["low_quality_sources"] = low_list
    if search_errors:
        payload["search_errors"] = search_errors

    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="search_links",
    annotations={
        "title": "Search links and snippets only (fast results, no content fetch)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search_links(params: LinkSearchInput) -> str:
    """Search the web and return only links, titles, and snippets (no content fetch).

    Use this tool ONLY when the user explicitly asks for:
    - Links, URLs, or search results list
    - Quick results without reading the page content
    - A list of related pages

    DO NOT use this tool to answer specific questions — use web_search instead.
    This tool does NOT fetch page content or evaluate source quality.

    LANGUAGE RULE: Answer in the same language as the user.

    Args:
        params (LinkSearchInput):
            - query (str): Search query
            - max_results (int, default: 5): Number of results (1-10)

    Returns:
        str: JSON with results[] (each: title, url, snippet)
    """
    log.info("Tool search_links: \"%s\"", params.query)
    try:
        results = await _ddg_search(params.query, params.max_results)
    except Exception as e:
        log.error("Error en search_links: %s", _handle_http_error(e))
        return json.dumps({"error": _handle_http_error(e), "results": []})

    if not results:
        return json.dumps({"query": params.query, "results": [], "message": "No results found."})

    return json.dumps(
        {"query": params.query, "total": len(results), "results": results},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool(
    name="fetch_page",
    annotations={
        "title": "Read content from a specific web page",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fetch_page(params: FetchInput) -> str:
    """Fetch and extract clean text from a specific URL with extraction fallback.

    Use this tool ONLY when the user provides a specific URL or when
    you need to inspect a known page in detail.

    DO NOT use for general questions — use web_search instead.
    This tool does not search; it only reads a given URL.

    LANGUAGE RULE: Answer in the same language as the user.

    Args:
        params (FetchInput):
            - url (str): Full URL to read
            - max_chars (int, default: 4000): Max characters (100-10000)

    Returns:
        str: JSON with { url, content, chars, method (extraction method) }
    """
    log.info("Tool fetch_page: %s", params.url)
    try:
        result = await _fetch_page_with_fallback(params.url, params.max_chars)
        return json.dumps(
            {
                "url": params.url,
                "content": result["content"],
                "chars": len(result["content"]),
                "method": result["method"],
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        log.error("Error en fetch_page %s: %s", params.url, e)
        return json.dumps({"url": params.url, "error": str(e)})


@mcp.tool(
    name="multi_search",
    annotations={
        "title": "Multiple parallel searches (links/snippets only, no full content)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def multi_search(params: MultiSearchInput) -> str:
    """Run multiple searches in parallel and return links/snippets per query.

    Use for quick exploration of multiple subtopics when only links and brief
    summaries are needed. Does NOT return full page content.

    If you need detailed information on each topic, use web_search separately
    for each one.

    LANGUAGE RULE: Answer in the same language as the user.

    Args:
        params (MultiSearchInput):
            - queries (list[str]): List of up to 5 search queries
            - max_results_per_query (int, default: 3): Results per query (1-5)

    Returns:
        str: JSON with data[] grouped by query
    """
    log.info("Tool multi_search: %d queries", len(params.queries))

    async def search_one(q: str) -> dict:
        try:
            results = await _ddg_search(q, params.max_results_per_query)
            return {"query": q, "results": results}
        except Exception as e:
            log.error("Error en multi_search query \"%s\": %s", q, _handle_http_error(e))
            return {"query": q, "error": _handle_http_error(e), "results": []}

    all_results = await asyncio.gather(*[search_one(q) for q in params.queries])

    return json.dumps(
        {"searches": len(params.queries), "data": list(all_results)},
        ensure_ascii=False,
        indent=2,
    )


# ── MCP Prompts ───────────────────────────────────────────────────────────────
# Each prompt instructs the LLM on research workflow, tool usage, and how to
# interpret evidence guidance. Prompts are in English (MCP-facing) and include
# the language instruction so the LLM answers in the user's language.

_LANGUAGE_RULE = (
    "IMPORTANT LANGUAGE RULE: Always answer in the same language the user is "
    "communicating in, unless they explicitly ask you to use a different language."
)


@mcp.prompt()
def web_research_assistant() -> str:
    """System prompt: general web research behavior.

    Attach this prompt at the start of a conversation to establish the
    correct research workflow for every question.
    """
    return f"""
You are a web research assistant backed by the web-search-mcp server.

Your core tool is **web_search** — a full iterative research tool that
internally performs query refinement, multi-query expansion, entity
discovery, follow-up searches, content fetching, source scoring, and
evidence assessment.

## When to use web_search

USE it when:
- The user asks about a person, company, event, product, API, news, or
  any specific factual topic.
- You need to verify, compare, complement, or cite information.
- Your internal knowledge may be incomplete or outdated.

DO NOT use it when:
- The question is stable general knowledge (math, physics, basic concepts).
- The task is writing, translation, or simple reasoning.
- The user explicitly asks you not to search.

## How web_search works internally

1. **Query refinement** — short or ambiguous queries are enriched with
   context (e.g. "Antar Nakid" → "who is Antar Nakid professional profile").
2. **Multi-query expansion** — up to 6 related searches based on detected
   intent (person, company, technical, news, general).
3. **Entity discovery** — after the first pass, notable entities are extracted
   from titles and snippets (company names, roles, technologies).
4. **Follow-up search** — discovered entities are used to build refined
   second-pass queries.
5. **Content extraction** — pages are fetched with fallback
   (crawl4ai → httpx+bs4 → HTML metadata).
6. **Source scoring** — each result is scored for quality, domain authority,
   content length, and relevance to discovered entities.
7. **Evidence assessment** — returns evidence_status, recommended_action,
   and answer_guidance.

## How to interpret the response

The JSON response includes:

- `evidence_status`: "strong" | "partial" | "weak" | "none"
- `recommended_action`: "answer_normally" | "answer_with_caveat" |
  "ask_for_more_context"
- `answer_guidance.language_instruction`: Always follow this.
- `answer_guidance.caveat`: Read this if present — it explains limitations.

### Response guidelines

- **strong evidence**: Answer confidently based on the results.
- **partial / weak evidence**: Answer with a caveat. Frame as
  "Based on available sources..." and note the limitations.
- **no evidence / empty results**: Do NOT fabricate. Say you couldn't
  find relevant information and suggest refining the query.
- **language_instruction**: Always follow this rule.

## Do NOT chain multiple tool calls unnecessarily

web_search already does multi-phase research internally. Only call it once
per question. If evidence_status remains "weak" or "none", you may try a
different query with more context or narrower scope.

{_LANGUAGE_RULE}
"""


@mcp.prompt()
def investigate_person(name: str) -> str:
    """Specialized prompt to research a person.

    Args:
        name: Full name of the person to investigate.
    """
    return f"""
Research the person "{name}".

Use web_search with depth="standard" (or "deep" if the name is uncommon).
The tool will automatically refine short name queries, expand to LinkedIn,
professional profiles, CEO/founder context, and run follow-up searches
discovering associated companies and roles.

After receiving the results:
1. Identify the person's primary role, company, and notable achievements.
2. Include relevant professional context (education, location, industry).
3. If evidence is partial, say so clearly.
4. Do not fabricate details not found in the results.

{_LANGUAGE_RULE}
"""


@mcp.prompt()
def investigate_company(company: str) -> str:
    """Specialized prompt to research a company.

    Args:
        company: Company name to investigate.
    """
    return f"""
Research the company or organization "{company}".

Use web_search with depth="standard" and purpose="complement".
The tool will expand the query with official site, LinkedIn, Crunchbase,
funding, and news context automatically.

After receiving the results:
1. Describe what the company does (product/service, industry).
2. Identify founders, leadership, location, and size if available.
3. Note funding, partnerships, or recent news if found.
4. Flag any low-quality sources — prefer official sites and professional media.

{_LANGUAGE_RULE}
"""


@mcp.prompt()
def verify_claim(claim: str) -> str:
    """Specialized prompt to fact-check or verify a claim.

    Args:
        claim: The statement to verify.
    """
    return f"""
Verify the following claim:

> {claim}

Use web_search with purpose="verify" and depth="standard".
The tool will add "source", "evidence", "fact check", and "official"
expansions automatically.

After receiving the results:
1. State whether the claim is supported, contradicted, or unverifiable.
2. Cite specific sources that support or contradict it.
3. If sources conflict, explain the conflicting positions.
4. If evidence_status is "weak" or "none", say the claim could not be verified.
5. Do not lean toward one side without clear source backing.

{_LANGUAGE_RULE}
"""


@mcp.prompt()
def find_sources(topic: str) -> str:
    """Specialized prompt to find authoritative sources on a topic.

    Args:
        topic: Topic to find sources for.
    """
    return f"""
Find authoritative sources for the topic "{topic}".

Use web_search with purpose="sources" and depth="deep".
The tool will prioritize official documentation, academic/professional
domains, and high-quality media. Low-quality social media sources are
penalized automatically.

After receiving the results:
1. List the most reliable sources found (official sites, docs, reputable media).
2. Note the source_quality and ranking_reasons for each.
3. Recommend the best 2-3 sources for the user to consult.
4. Avoid citing low-quality or unverified sources.

{_LANGUAGE_RULE}
"""


@mcp.prompt()
def answer_from_evidence() -> str:
    """How to structure answers using web_search evidence.

    Attach when you have just received web_search results and need to
    formulate an answer.
    """
    return f"""
You have received web_search results. Follow this structure:

1. **Check evidence_status**:
   - "strong" → answer with confidence
   - "partial" → answer with "Based on available sources..."
   - "weak" → answer with clear caveats
   - "none" → do not answer; ask for more context

2. **Read recommended_action**:
   - "answer_normally" → go ahead
   - "answer_with_caveat" → explain limitations
   - "ask_for_more_context" → ask the user to clarify

3. **Synthesize the results**:
   - Combine information from multiple high-quality sources.
   - Prioritize results with higher scores and ranking_reasons like
     "relates to discovered entities" or "full content extracted".
   - Cross-check: if sources disagree, note the discrepancy.

4. **Cite your sources**:
   - Mention which source(s) each piece of information came from.
   - Include URLs when relevant.

5. **Language**:
   - Answer in the user's language.

{_LANGUAGE_RULE}
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
