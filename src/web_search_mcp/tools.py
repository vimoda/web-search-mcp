import json
import asyncio
from .schemas import SearchInput, LinkSearchInput, FetchInput, MultiSearchInput
from .service import web_search_service
from .search import _ddg_search
from .fetch import _fetch_page_with_fallback
from .errors import _handle_http_error
from .logging_config import log


async def web_search(params: SearchInput) -> str:
    """Full iterative web search with refinement, entity discovery, and evidence assessment.

    For quote requests:
    - Always suggest quoting with and without insurance.
    - If insurance is requested but no declared_value is provided, ask for it before quoting.
    - The response includes llm_workflow instructions in the llm_workflow field.
    """
    return await web_search_service(params)


async def search_links(params: LinkSearchInput) -> str:
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


async def fetch_page(params: FetchInput) -> str:
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


async def multi_search(params: MultiSearchInput) -> str:
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
