"""Web Search MCP Server.

Entry point: re-exports all symbols for backward compatibility.
"""

from .config import (
    MAX_TEXT_LENGTH, SEARCH_REGION, REQUEST_TIMEOUT,
    WEB_SEARCH_DEFAULT_DEPTH, WEB_SEARCH_MAX_CONCURRENT_FETCHES,
    WEB_SEARCH_FETCH_TIMEOUT, LOG_LEVEL, LOG_LEVELS, _SILENT,
    HEADERS, DDGS_SEARCH_URL,
)
from .logging_config import log
from .errors import _handle_http_error
from .url_utils import _get_domain, _normalize_url, _deduplicate
from .schemas import SearchInput, LinkSearchInput, FetchInput, MultiSearchInput
from .query_intent import _detect_query_type
from .query_refinement import _is_simple_or_ambiguous_query, _refine_query
from .query_expansion import _expand_queries, _build_followup_queries
from .source_scoring import _score_source
from .evidence import _compute_evidence_status
from .search import _ddg_search
from .fetch import _fetch_page, _fetch_page_with_fallback
from .response_intent import (
    _detect_response_intent, _get_response_intent_display, _detect_quote_requirements,
)
from .workflow_guidance import _build_llm_workflow_guidance
from .service import _extract_discovered_terms, web_search_service
from .tools import web_search, search_links, fetch_page, multi_search
from .prompts import (
    web_research_assistant, investigate_person, investigate_company,
    verify_claim, find_sources, answer_from_evidence, quote_or_guide_router,
    choose_quote_flow,
)
from .app import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
