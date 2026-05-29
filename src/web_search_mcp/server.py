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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _handle_http_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 403:
            return f"Error 403: Acceso denegado por el sitio (posible bloqueo de bots)."
        if code == 404:
            return "Error 404: Página no encontrada."
        if code == 429:
            return "Error 429: Rate limit alcanzado. Espera unos segundos."
        return f"Error HTTP {code}: {e.response.reason_phrase}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Timeout al conectar con el servidor."
    if isinstance(e, httpx.ConnectError):
        return "Error: No se pudo conectar. Verifica la URL o tu conexión."
    return f"Error inesperado: {type(e).__name__}: {e}"


async def _ddg_search(query: str, max_results: int) -> list[dict]:
    """
    Hace una búsqueda en DuckDuckGo (HTML endpoint) y retorna una lista de resultados.
    Cada resultado tiene: title, url, snippet.
    """
    log.info("Buscando: \"%s\" (max=%d, region=%s)", query, max_results, SEARCH_REGION)
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

    log.info("Resultados para \"%s\": %d", query, len(results))
    return results


async def _fetch_page(url: str, max_chars: int = MAX_TEXT_LENGTH) -> str:
    """Hace fetch de una URL con crawl4ai (soporta JS) y retorna markdown limpio."""
    log.info("Fetching: %s", url)
    config = CrawlerRunConfig(
        word_count_threshold=10,       # ignora bloques con menos de 10 palabras
        exclude_external_links=True,   # quita links externos del markdown
        remove_overlay_elements=True,  # cierra popups/overlays si los detecta
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)

    if not result.success:
        raise RuntimeError(result.error_message or "crawl4ai no pudo obtener la página")

    text = result.markdown or result.cleaned_html or ""
    chars = len(text[:max_chars])
    log.info("Fetch exitoso: %s (%d chars)", url, chars)
    return text[:max_chars]


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


def _score_source(url: str, snippet: str, content: str | None = None) -> dict:
    """Score a source and return quality metadata."""
    domain = urllib.parse.urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    for low_domain, reason in LOW_QUALITY_DOMAINS.items():
        if low_domain in domain:
            return {"score": 0.1, "quality": "low", "reason": reason}

    for high_domain, reason in HIGH_QUALITY_DOMAINS.items():
        if high_domain in domain:
            return {"score": 0.9, "quality": "high", "reason": reason}

    if not snippet or len(snippet.strip()) < 30:
        return {"score": 0.3, "quality": "low", "reason": "very short or empty snippet"}

    if content and len(content.strip()) < 100:
        return {"score": 0.4, "quality": "low", "reason": "fetched content too short"}

    return {"score": 0.7, "quality": "medium", "reason": "standard web source"}


def _deduplicate(results: list[dict]) -> list[dict]:
    """Remove duplicate URLs, keeping the first occurrence."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        key = r["url"].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def _expand_queries(query: str, depth: str) -> list[str]:
    """Generate related queries for deeper research."""
    queries = [query]
    if depth == "standard":
        queries.append(f"{query} profile")
        queries.append(f"{query} official")
    elif depth == "deep":
        queries.append(f"{query} profile")
        queries.append(f"{query} official")
        queries.append(f"{query} biography")
        queries.append(f"{query} career")
        queries.append(f"{query} company")
    return queries


# ── Modelos de entrada ────────────────────────────────────────────────────────

class SearchInput(BaseModel):
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
    fetch_content: Optional[bool] = Field(
        default=True,
        description="Si True (default), hace fetch del contenido completo de cada página además del snippet",
    )
    max_chars_per_result: Optional[int] = Field(
        default=4000,
        description="Máximo de caracteres a retornar por cada página (500-10000)",
        ge=500,
        le=10000,
    )
    depth: Optional[str] = Field(
        default="standard",
        description="Profundidad de investigación: 'quick' (1 query, resultados directos), 'standard' (3 queries, calidad), 'deep' (6 queries, exhaustivo)",
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
        "title": "Buscar y leer contenido de la web (recomendado)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def web_search(params: SearchInput) -> str:
    """Herramienta PRINCIPAL para responder preguntas usando información de internet.

    Realiza investigación multi-query automática:
    - quick: 1 búsqueda, resultados directos con fetch opcional
    - standard (default): 3 búsquedas relacionadas, filtra fuentes pobres,
      prioriza páginas con contenido, fetch de las mejores fuentes
    - deep: 6 búsquedas relacionadas, cobertura exhaustiva

    Después de buscar, evalúa calidad de cada fuente, penaliza redes sociales
    y contenido vacío, y hace fetch selectivo solo de los mejores resultados.

    Usa esta herramienta para cualquier pregunta que requiera información
    actual, externa o factual. NO uses search_links para respuestas concretas.

    Args:
        params (SearchInput):
            - query (str): Consulta de búsqueda
            - max_results (int): Resultados a retornar (default: 5)
            - fetch_content (bool): Si traer el contenido (default: true)
            - max_chars_per_result (int): Carácteres por página (default: 4000)
            - depth (str): Profundidad: 'quick', 'standard', 'deep' (default: 'standard')

    Returns:
        str: JSON con:
            - query (str): Consulta original
            - depth (str): Profundidad usada
            - searches_performed (list): Queries ejecutadas
            - total (int): Resultados devueltos
            - results (list): Cada resultado:
                - title (str), url (str), snippet (str)
                - content (str, si fetch_content)
                - source_quality (str): 'high' | 'medium' | 'low'
                - content_available (bool)
            - low_quality_sources (list): Fuentes pobres omitidas
    """
    log.info(
        "Tool web_search: \"%s\" (depth=%s, fetch=%s, max=%d)",
        params.query, params.depth, params.fetch_content, params.max_results,
    )

    depth = params.depth.strip().lower() if params.depth else "standard"
    if depth not in ("quick", "standard", "deep"):
        depth = "standard"

    try:
        if depth == "quick":
            expanded = [params.query]
            internal_limit = params.max_results
        else:
            expanded = _expand_queries(params.query, depth)
            internal_limit = params.max_results * (2 if depth == "standard" else 3)

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

        if not all_results:
            payload = {"query": params.query, "results": [], "message": "Sin resultados"}
            if expanded:
                payload["searches_performed"] = expanded
            return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Error en web_search: %s", _handle_http_error(e))
        return json.dumps({"error": _handle_http_error(e), "results": []})

    all_results = _deduplicate(all_results)

    scored = []
    for r in all_results:
        meta = _score_source(r["url"], r.get("snippet", ""))
        scored.append((meta["score"], meta, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    to_fetch = scored[: params.max_results]
    low_quality = [s for s in scored[params.max_results :] if s[1]["quality"] == "low"]

    if params.fetch_content:
        async def enrich(item: tuple[float, dict, dict]) -> dict:
            _, meta, r = item
            try:
                r["content"] = await _fetch_page(r["url"], params.max_chars_per_result)
                content_text = r.get("content") or ""
                if len(content_text.strip()) < 100:
                    meta = _score_source(r["url"], r.get("snippet", ""), content_text)
                r["content_available"] = bool(r.get("content"))
            except Exception as e:
                r["content"] = None
                r["content_available"] = False
            r["source_quality"] = meta["quality"]
            return r

        final_results = await asyncio.gather(*[enrich(item) for item in to_fetch])
    else:
        final_results = []
        for _, meta, r in to_fetch:
            r["source_quality"] = meta["quality"]
            r["content_available"] = False
            final_results.append(r)

    low_list = []
    for _, meta, r in low_quality:
        low_list.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "reason": meta.get("reason", "low quality source"),
        })

    payload: dict = {
        "query": params.query,
        "depth": depth,
        "searches_performed": expanded,
        "total": len(final_results),
        "results": final_results,
    }
    if low_list:
        payload["low_quality_sources"] = low_list
    if search_errors:
        payload["search_errors"] = search_errors

    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="search_links",
    annotations={
        "title": "Buscar links y snippets (solo resultados rápidos)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search_links(params: LinkSearchInput) -> str:
    """Busca en la web y retorna solo links, títulos y snippets (sin contenido).

    Usa esta herramienta SOLO cuando el usuario pida expresamente:
    - Links o URLs de búsqueda
    - Resultados rápidos sin leer el contenido
    - Una lista de páginas relacionadas

    NO uses esta herramienta cuando el usuario necesite una respuesta,
    explicación o resumen basado en el contenido de las páginas.
    Para eso usa web_search.

    Args:
        params (LinkSearchInput): Parámetros de búsqueda:
            - query (str): Consulta de búsqueda
            - max_results (int): Resultados a retornar (default: 5)

    Returns:
        str: JSON con:
            - query (str): Consulta original
            - total (int): Número de resultados
            - results (list): Lista de resultados, cada uno con:
                - title (str): Título de la página
                - url (str): URL de la página
                - snippet (str): Extracto del contenido
    """
    log.info("Tool search_links: \"%s\"", params.query)
    try:
        results = await _ddg_search(params.query, params.max_results)
    except Exception as e:
        log.error("Error en search_links: %s", _handle_http_error(e))
        return json.dumps({"error": _handle_http_error(e), "results": []})

    if not results:
        return json.dumps({"query": params.query, "results": [], "message": "Sin resultados"})

    return json.dumps(
        {"query": params.query, "total": len(results), "results": results},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool(
    name="fetch_page",
    annotations={
        "title": "Leer contenido de una página web",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fetch_page(params: FetchInput) -> str:
    """Lee y extrae el texto limpio de una página web específica.

    Usa esta herramienta solo cuando el usuario proporciona una URL concreta
    o cuando necesitas inspeccionar una página conocida.
    NO la uses para responder preguntas generales; para eso usa web_search.

    Args:
        params (FetchInput): Parámetros:
            - url (str): URL completa a leer
            - max_chars (int): Máximo de caracteres a retornar (default: 4000)

    Returns:
        str: JSON con:
            - url (str): URL leída
            - content (str): Texto extraído de la página
            - chars (int): Número de caracteres retornados
    """
    log.info("Tool fetch_page: %s", params.url)
    try:
        text = await _fetch_page(params.url, params.max_chars)
        return json.dumps(
            {"url": params.url, "content": text, "chars": len(text)},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        log.error("Error en fetch_page %s: %s", params.url, e)
        return json.dumps({"url": params.url, "error": str(e)})


@mcp.tool(
    name="multi_search",
    annotations={
        "title": "Múltiples búsquedas en paralelo (solo links/snippets)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def multi_search(params: MultiSearchInput) -> str:
    """Ejecuta varias búsquedas en paralelo y retorna links/snippets por cada una.

    Usa esta herramienta cuando el usuario pida investigar múltiples subtemas
    al mismo tiempo y solo necesite links y resúmenes rápidos.
    Si necesitas contenido completo para cada query, usa web_search por cada una.

    Args:
        params (MultiSearchInput): Parámetros:
            - queries (list[str]): Lista de hasta 5 consultas
            - max_results_per_query (int): Resultados por query (default: 3)

    Returns:
        str: JSON con resultados agrupados por query:
            - query (str): Consulta original
            - results (list): Lista de resultados para esa query
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


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
