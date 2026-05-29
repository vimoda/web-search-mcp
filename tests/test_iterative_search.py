"""Tests for iterative search helpers in web-search-mcp.

These test the pure helper functions used for entity discovery,
follow-up query generation, and source scoring.
"""

from __future__ import annotations

import pytest
from web_search_mcp.server import (
    _detect_query_type,
    _detect_response_intent,
    _detect_quote_requirements,
    _build_llm_workflow_guidance,
    _extract_discovered_terms,
    _build_followup_queries,
    _score_source,
    _normalize_url,
    _expand_queries,
    _get_domain,
    _is_simple_or_ambiguous_query,
    _refine_query,
)


# ── _detect_query_type ─────────────────────────────────────────────────────────

class TestDetectQueryType:
    def test_person_name_inference(self):
        assert _detect_query_type("Antar Nakid") == "person"

    def test_person_with_role(self):
        assert _detect_query_type("who is Satya Nadella") == "person"
        assert _detect_query_type("Antar Nakid CEO") == "person"

    def test_company_keywords(self):
        assert _detect_query_type("Microsoft funding") == "company"
        assert _detect_query_type("Monadic crunchbase") == "company"

    def test_technical(self):
        assert _detect_query_type("python asyncio tutorial") == "technical"
        assert _detect_query_type("fastapi documentation") == "technical"

    def test_news(self):
        assert _detect_query_type("latest AI news 2026") == "news"

    def test_general_fallback(self):
        assert _detect_query_type("how to cook pasta") == "general"

    def test_person_from_uppercase_short(self):
        assert _detect_query_type("John Smith") == "person"
        assert _detect_query_type("Maria García López") == "person"


# ── _is_simple_or_ambiguous_query ──────────────────────────────────────────────

class TestIsSimpleOrAmbiguousQuery:
    def test_single_word_is_simple(self):
        is_simple, reason = _is_simple_or_ambiguous_query("T1")
        assert is_simple
        assert "generic" in reason.lower() or "context" in reason.lower()

    def test_two_word_name_is_simple(self):
        is_simple, reason = _is_simple_or_ambiguous_query("Antar Nakid")
        assert is_simple
        assert "name" in reason.lower() or "entity" in reason.lower()

    def test_acronym_is_simple(self):
        is_simple, _ = _is_simple_or_ambiguous_query("MCP")
        assert is_simple

    def test_detailed_query_not_simple(self):
        is_simple, reason = _is_simple_or_ambiguous_query("Antar Nakid CEO Monadic LinkedIn")
        assert not is_simple
        assert reason == ""

    def test_query_with_intent_keyword_not_simple(self):
        is_simple, reason = _is_simple_or_ambiguous_query("Python documentation")
        assert not is_simple
        assert reason == ""

    def test_single_generic_word_is_simple(self):
        is_simple, _ = _is_simple_or_ambiguous_query("Monadic")
        assert is_simple


# ── _refine_query ──────────────────────────────────────────────────────────────

class TestRefineQuery:
    def test_refines_person_name(self):
        refined = _refine_query("Antar Nakid", "person", "answer")
        assert refined != "Antar Nakid"
        assert "who is" in refined.lower() or "profile" in refined.lower()

    def test_refines_company_name(self):
        refined = _refine_query("Monadic", "company", "answer")
        assert refined != "Monadic"
        assert "company" in refined.lower() or "official" in refined.lower()

    def test_refines_technical_term(self):
        refined = _refine_query("MCP", "technical", "answer")
        assert refined != "MCP"
        assert "docs" in refined.lower() or "documentation" in refined.lower()

    def test_refines_short_general(self):
        refined = _refine_query("test", "general", "answer")
        assert refined != "test"

    def test_no_refinement_for_detailed_query(self):
        refined = _refine_query("Antar Nakid CEO Monadic LinkedIn", "person", "answer")
        # Should not change since it's already detailed
        assert refined == "Antar Nakid CEO Monadic LinkedIn"


# ── _extract_discovered_terms ─────────────────────────────────────────────────

class TestExtractDiscoveredTerms:
    def test_extracts_company_from_results(self):
        results = [
            {"title": "Monadic: Transforming E-commerce", "snippet": "Monadic is a platform for digital transformation", "url": "https://example.com/monadic"},
            {"title": "Antar Nakid - CEO at Monadic", "snippet": "Antar Nakid is the CEO of Monadic", "url": "https://example.com/antar"},
            {"title": "Monadic raises funding", "snippet": "Monadic e-commerce platform", "url": "https://example.com/funding"},
        ]
        terms = _extract_discovered_terms(results, "Antar Nakid")
        assert "Monadic" in terms
        assert "CEO" in terms

    def test_does_not_return_query_words(self):
        results = [
            {"title": "Python Tutorial", "snippet": "Learn Python programming", "url": "https://python.org/doc"},
            {"title": "Python for Beginners", "snippet": "Python is great", "url": "https://example.com/python"},
        ]
        terms = _extract_discovered_terms(results, "Python")
        assert "Python" not in terms or not terms

    def test_empty_results_returns_empty(self):
        assert _extract_discovered_terms([], "test") == []

    def test_domain_derived_terms(self):
        results = [
            {"title": "Monadic page", "snippet": "some content", "url": "https://monadic.com/about"},
            {"title": "Monadic info", "snippet": "more content", "url": "https://monadic.com/team"},
        ]
        terms = _extract_discovered_terms(results, "Antar Nakid")
        assert "Monadic" in terms


# ── _build_followup_queries ───────────────────────────────────────────────────

class TestBuildFollowupQueries:
    def test_quick_depth_returns_none(self):
        assert _build_followup_queries("Antar Nakid", "person", ["Monadic", "T1"], "quick") == []

    def test_standard_person_returns_two(self):
        queries = _build_followup_queries("Antar Nakid", "person", ["Monadic", "T1", "CEO"], "standard")
        assert len(queries) == 2
        assert "Antar Nakid Monadic" in queries
        assert "Antar Nakid T1" in queries

    def test_deep_person_returns_more(self):
        queries = _build_followup_queries("Antar Nakid", "person", ["Monadic", "T1", "CEO", "Imagen"], "deep")
        assert len(queries) <= 5
        assert len(queries) >= 3

    def test_empty_discovered_returns_empty(self):
        assert _build_followup_queries("test", "general", [], "standard") == []

    def test_does_not_duplicate_queries(self):
        queries = _build_followup_queries("Antar Nakid", "person", ["Monadic", "Monadic"], "standard")
        assert len(queries) == 1
        assert queries[0] == "Antar Nakid Monadic"


# ── _score_source ─────────────────────────────────────────────────────────────

class TestScoreSource:
    def test_social_media_penalty(self):
        result = _score_source("test", "https://instagram.com/test", "some snippet")
        assert result["quality"] == "low"
        assert result["score"] == 0.1

    def test_high_quality_domain(self):
        result = _score_source("test", "https://wikipedia.org/Test", "some snippet content here")
        assert result["score"] >= 0.75

    def test_query_match_boost(self):
        result = _score_source("Antar Nakid", "https://example.com/page", "Antar Nakid CEO profile")
        assert result["score"] >= 0.55

    def test_discovered_entity_boost(self):
        result = _score_source(
            "Antar Nakid",
            "https://monadic.com/about",
            "Antar Nakid leads Monadic T1 an e-commerce company Monadic CEO",
            title="Antar Nakid CEO Monadic T1",
            discovered_terms=["Monadic", "CEO", "T1"],
        )
        assert result["score"] >= 0.6
        reasons = " ".join(result["ranking_reasons"])
        assert "3" in reasons or "discovered" in reasons

    def test_multiple_entities_extra_boost(self):
        result = _score_source(
            "Antar Nakid",
            "https://example.com/article",
            "Antar Nakid CEO of Monadic previously founded T1 company",
            title="Antar Nakid Monadic CEO T1",
            discovered_terms=["Monadic", "T1", "CEO"],
        )
        assert result["score"] >= 0.75
        reasons = " ".join(result["ranking_reasons"])
        assert "3" in reasons

    def test_content_extracted_boost(self):
        result = _score_source(
            "test", "https://example.com/page", "a valid snippet with enough text for score",
            content="A" * 500,
        )
        assert result["score"] >= 0.7

    def test_empty_content_no_boost(self):
        result = _score_source(
            "test", "https://example.com/page", "valid snippet here",
            content="",
        )
        assert result["score"] <= 0.6


# ── _normalize_url ────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_removes_www(self):
        assert "example.com" in _normalize_url("https://www.example.com/page")

    def test_removes_tracking(self):
        a = _normalize_url("https://example.com/page?utm_source=test&id=123")
        b = _normalize_url("https://example.com/page?id=123")
        assert a == b

    def test_trailing_slash_normalized(self):
        a = _normalize_url("https://example.com/page/")
        b = _normalize_url("https://example.com/page")
        assert a == b

    def test_different_urls_distinct(self):
        a = _normalize_url("https://example.com/page1")
        b = _normalize_url("https://example.com/page2")
        assert a != b


# ── _expand_queries ───────────────────────────────────────────────────────────

class TestExpandQueries:
    def test_person_standard_expands(self):
        queries = _expand_queries("Antar Nakid", "standard", "answer", "person")
        assert len(queries) == 3
        assert queries[0] == "Antar Nakid"

    def test_quick_returns_single(self):
        queries = _expand_queries("Antar Nakid", "quick", "answer", "person")
        assert len(queries) == 1

    def test_deep_returns_six(self):
        queries = _expand_queries("Antar Nakid", "deep", "answer", "person")
        assert len(queries) == 6

    def test_purpose_extra_expansions(self):
        queries = _expand_queries("Antar Nakid", "deep", "verify", "person")
        assert len(queries) == 6

    def test_technical_expansion(self):
        queries = _expand_queries("python asyncio", "standard", "answer", "technical")
        assert len(queries) == 3


# ── _get_domain ───────────────────────────────────────────────────────────────

class TestGetDomain:
    def test_strips_www(self):
        assert _get_domain("https://www.example.com/page") == "example.com"

    def test_keeps_subdomain(self):
        assert _get_domain("https://blog.example.com/page") == "blog.example.com"

    def test_no_path(self):
        assert _get_domain("https://example.com") == "example.com"


# ── _detect_response_intent ────────────────────────────────────────────────────

class TestDetectResponseIntent:
    def test_general_query_returns_research(self):
        assert _detect_response_intent("who is Antar Nakid", "answer") == "research_answer"

    def test_quote_keyword_detected(self):
        assert _detect_response_intent("cotizar envío", "answer") == "quote_only"

    def test_guide_keyword_detected(self):
        assert _detect_response_intent("genera una guía para implementar MCP", "answer") == "guide_generation"

    def test_purpose_quote_forces_quote(self):
        assert _detect_response_intent("web hosting", "quote") == "quote_only"

    def test_purpose_guide_forces_guide(self):
        assert _detect_response_intent("web hosting", "guide") == "guide_generation"

    def test_pricing_detected(self):
        assert _detect_response_intent("cuanto cuesta aws hosting", "answer") == "quote_only"

    def test_how_to_detected(self):
        assert _detect_response_intent("how to deploy a website", "answer") == "guide_generation"

    def test_quote_short_word_detected(self):
        assert _detect_response_intent("precio de servidores", "answer") == "quote_only"

    def test_search_context_helps(self):
        assert _detect_response_intent("MCP", "answer", "how to implement") == "guide_generation"


# ── _detect_quote_requirements ──────────────────────────────────────────────────

class TestDetectQuoteRequirements:
    def test_no_insurance_no_declared_value(self):
        result = _detect_quote_requirements("cotizar envío a CDMX")
        assert result["insurance_requested"] is False
        assert result["declared_value"] is None
        assert result["missing_declared_value"] is False

    def test_insurance_without_declared_value_blocks_quote(self):
        result = _detect_quote_requirements("cotizar envío con seguro a CDMX")
        assert result["insurance_requested"] is True
        assert result["declared_value"] is None
        assert result["missing_declared_value"] is True

    def test_insurance_with_declared_value_allows_quote(self):
        result = _detect_quote_requirements("cotizar envío con seguro valor declarado 5000 a CDMX")
        assert result["insurance_requested"] is True
        assert result["declared_value"] == 5000
        assert result["missing_declared_value"] is False

    def test_insurance_with_declared_value_usd(self):
        result = _detect_quote_requirements("quote with insurance declared value $10000")
        assert result["insurance_requested"] is True
        assert result["declared_value"] == 10000
        assert result["missing_declared_value"] is False

    def test_search_context_declared_value(self):
        result = _detect_quote_requirements("cotizar envío con seguro", "valor declarado 20000")
        assert result["insurance_requested"] is True
        assert result["declared_value"] == 20000
        assert result["missing_declared_value"] is False

    def test_no_insurance_no_block(self):
        result = _detect_quote_requirements("cotizar envío estándar")
        assert result["insurance_requested"] is False
        assert result["declared_value"] is None
        assert result["missing_declared_value"] is False


# ── _build_llm_workflow_guidance ──────────────────────────────────────────────

class TestBuildWorkflowGuidance:
    def test_quote_workflow_mentions_insurance_options(self):
        result = _build_llm_workflow_guidance("quote_only", "strong", "general")
        workflow = result["llm_workflow"]
        assert "without insurance" in workflow.lower()
        assert "with insurance" in workflow.lower()

    def test_quote_workflow_mentions_declared_value(self):
        result = _build_llm_workflow_guidance("quote_only", "strong", "general")
        workflow = result["llm_workflow"]
        assert "declared_value" in workflow.lower()

    def test_quote_workflow_rejects_missing_declared_value(self):
        result = _build_llm_workflow_guidance("quote_only", "strong", "general")
        workflow = result["llm_workflow"]
        assert "must not generate" in workflow.lower() or "must not" in workflow.lower()

    def test_quote_workflow_weak_evidence(self):
        result = _build_llm_workflow_guidance("quote_only", "weak", "general")
        workflow = result["llm_workflow"]
        assert "limited or unavailable" in workflow.lower()
        assert "official sites" in workflow.lower()

    def test_guide_workflow_no_insurance_language(self):
        result = _build_llm_workflow_guidance("guide_generation", "strong", "technical")
        workflow = result["llm_workflow"]
        assert "USER INTENT" in workflow
        assert "step-by-step" in workflow.lower()

    def test_research_workflow_no_insurance_language(self):
        result = _build_llm_workflow_guidance("research_answer", "strong", "general")
        workflow = result["llm_workflow"]
        assert "USER INTENT" in workflow
        assert "answer with confidence" in workflow.lower()

    def test_quote_workflow_struct(self):
        result = _build_llm_workflow_guidance("quote_only", "none", "general")
        assert result["response_intent"] == "quote_only"
        assert result["should_generate_quote"] is True
        assert result["should_generate_guide"] is False
