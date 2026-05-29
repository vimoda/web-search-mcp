import json
import asyncio
import re
import urllib.parse
from .config import WEB_SEARCH_DEFAULT_DEPTH
from .logging_config import log
from .url_utils import _get_domain, _deduplicate
from .source_scoring import _score_source
from .search import _ddg_search
from .fetch import _fetch_page_with_fallback
from .query_intent import _detect_query_type
from .query_refinement import _is_simple_or_ambiguous_query, _refine_query
from .query_expansion import _expand_queries, _build_followup_queries
from .evidence import _compute_evidence_status
from .errors import _handle_http_error
from .response_intent import (
    _detect_response_intent, _get_response_intent_display, _detect_quote_requirements,
)
from .workflow_guidance import _build_llm_workflow_guidance
from .schemas import SearchInput

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

    domains: dict[str, int] = {}
    for r in results:
        domain = _get_domain(r.get('url', ''))
        parts = domain.replace('.com', '').replace('.org', '').replace('.mx', '').split('.')
        for p in parts:
            p_lower = p.lower()
            if p_lower not in query_words and len(p) > 2 and not p.isdigit():
                key = p.capitalize()
                domains[key] = domains.get(key, 0) + 1

    terms = [t for t, c in sorted_terms if c >= 2][:6]
    seen_lower = {t.lower() for t in terms}

    for d, c in sorted(domains.items(), key=lambda x: -x[1]):
        if d.lower() not in seen_lower and len(terms) < 8:
            terms.append(d)
            seen_lower.add(d.lower())

    return terms


async def web_search_service(params: SearchInput) -> str:
    log.info(
        "Tool web_search: query=\"%s\" depth=%s purpose=%s fetch=%s",
        params.query, params.depth, params.purpose, params.fetch_content,
    )

    depth = (params.depth or WEB_SEARCH_DEFAULT_DEPTH).strip().lower()
    if depth not in ("quick", "standard", "deep"):
        depth = "standard"

    purpose = (params.purpose or "answer").strip().lower()
    valid_purposes = {"answer", "verify", "complement", "current_info", "sources", "explore", "quote", "guide"}
    if purpose not in valid_purposes:
        purpose = "answer"

    try:
        original_query = params.query
        query_type = _detect_query_type(original_query, params.search_context)
        log.info("Query type detected: %s", query_type)

        response_intent = _detect_response_intent(original_query, purpose, params.search_context)
        log.info("Response intent detected: %s", response_intent)

        if response_intent == "quote_only":
            quote_reqs = _detect_quote_requirements(original_query, params.search_context)
            if quote_reqs["missing_declared_value"]:
                log.info("Blocking quote: insurance requested without declared value")
                payload = {
                    "original_query": original_query,
                    "purpose": purpose,
                    "response_intent": "quote_only",
                    "response_intent_label": _get_response_intent_display(response_intent),
                    "recommended_action": "ask_for_declared_value",
                    "should_generate_quote": False,
                    "should_generate_guide": False,
                    "missing_required_fields": ["declared_value"],
                    "message": (
                        "Insurance was requested but no declared value was provided. "
                        "Please provide the declared value before requesting a quote."
                    ),
                    "answer_guidance": {
                        "language_instruction": "Answer in the same language as the user.",
                        "should_answer": True,
                        "confidence": "high",
                        "caveat": None,
                        "suggested_framing": "",
                    },
                }
                return json.dumps(payload, ensure_ascii=False, indent=2)

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
                "response_intent": response_intent,
                "response_intent_label": _get_response_intent_display(response_intent),
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
                "llm_workflow": _build_llm_workflow_guidance(
                    response_intent, "none", query_type,
                )["llm_workflow"],
                "should_generate_guide": response_intent == "guide_generation",
                "should_generate_quote": response_intent == "quote_only",
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

    wf = _build_llm_workflow_guidance(
        response_intent, evidence["evidence_status"], query_type,
    )

    payload = {
        "original_query": original_query,
        "refined_query": refined_query,
        "query_was_refined": query_was_refined,
        "refinement_reason": refinement_reason if query_was_refined else None,
        "depth": depth,
        "purpose": purpose,
        "response_intent": response_intent,
        "response_intent_label": _get_response_intent_display(response_intent),
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
        "llm_workflow": wf["llm_workflow"],
        "should_generate_guide": wf["should_generate_guide"],
        "should_generate_quote": wf["should_generate_quote"],
    }
    if low_list:
        payload["low_quality_sources"] = low_list
    if search_errors:
        payload["search_errors"] = search_errors

    return json.dumps(payload, ensure_ascii=False, indent=2)
