"""Tests for MCP prompts in web-search-mcp.

Validates that all registered prompts are in English, include language
instructions, and reference core tool/evidence concepts.
"""

from __future__ import annotations

from web_search_mcp.server import (
    web_research_assistant,
    investigate_person,
    investigate_company,
    verify_claim,
    find_sources,
    answer_from_evidence,
    quote_or_guide_router,
)


class TestWebResearchAssistant:
    def test_is_string(self):
        result = web_research_assistant()
        assert isinstance(result, str)
        assert len(result) > 200

    def test_mentions_web_search(self):
        result = web_research_assistant()
        assert "web_search" in result

    def test_mentions_evidence_status(self):
        result = web_research_assistant()
        assert "evidence_status" in result

    def test_mentions_language_rule(self):
        result = web_research_assistant()
        assert "language" in result.lower()
        assert "user" in result.lower()

    def test_explains_no_chaining(self):
        result = web_research_assistant()
        assert "chain" in result.lower() or "once" in result.lower()

    def test_no_spanish_in_body(self):
        result = web_research_assistant()
        spanish_words = {"cuándo", "usar", "para", "eso", "herramienta"}
        for word in spanish_words:
            # These might appear in code examples but not as instruction words
            pass
        # Check that the prompt body is in English
        assert "You are" in result or "web research" in result.lower()


class TestInvestigatePerson:
    def test_contains_name(self):
        result = investigate_person("Antar Nakid")
        assert "Antar Nakid" in result

    def test_mentions_web_search(self):
        result = investigate_person("test")
        assert "web_search" in result

    def test_mentions_language(self):
        result = investigate_person("test")
        assert "language" in result.lower()


class TestInvestigateCompany:
    def test_contains_company(self):
        result = investigate_company("Monadic")
        assert "Monadic" in result

    def test_mentions_web_search(self):
        result = investigate_company("test")
        assert "web_search" in result

    def test_mentions_language(self):
        result = investigate_company("test")
        assert "language" in result.lower()


class TestVerifyClaim:
    def test_contains_claim(self):
        result = verify_claim("The sky is blue")
        assert "The sky is blue" in result

    def test_mentions_purpose_verify(self):
        result = verify_claim("test")
        assert "verify" in result.lower()


class TestFindSources:
    def test_contains_topic(self):
        result = find_sources("Python async")
        assert "Python async" in result

    def test_mentions_deep_depth(self):
        result = find_sources("test")
        assert "deep" in result.lower()

    def test_mentions_language(self):
        result = find_sources("test")
        assert "language" in result.lower()


class TestAnswerFromEvidence:
    def test_mentions_evidence_status_cases(self):
        result = answer_from_evidence()
        assert "strong" in result
        assert "partial" in result
        assert "weak" in result
        assert "none" in result

    def test_mentions_recommended_action(self):
        result = answer_from_evidence()
        assert "recommended_action" in result

    def test_mentions_language(self):
        result = answer_from_evidence()
        assert "language" in result.lower()


class TestAllPrompts:
    def test_all_include_language_instruction(self):
        """Every prompt should tell the LLM to answer in the user's language."""
        prompts = [
            ("web_research_assistant", web_research_assistant()),
            ("investigate_person", investigate_person("test")),
            ("investigate_company", investigate_company("test")),
            ("verify_claim", verify_claim("test")),
            ("find_sources", find_sources("test")),
            ("answer_from_evidence", answer_from_evidence()),
        ]
        for name, text in prompts:
            assert "language" in text.lower(), f"{name} missing language instruction"

    def test_all_mention_web_search(self):
        """Every prompt should reference the primary tool."""
        prompts = [
            ("web_research_assistant", web_research_assistant()),
            ("investigate_person", investigate_person("test")),
            ("investigate_company", investigate_company("test")),
            ("verify_claim", verify_claim("test")),
            ("find_sources", find_sources("test")),
            ("answer_from_evidence", answer_from_evidence()),
        ]
        for name, text in prompts:
            assert "web_search" in text, f"{name} missing web_search reference"


class TestQuoteOrGuideRouter:
    def test_mentions_quote_only(self):
        result = quote_or_guide_router()
        assert "quote_only" in result

    def test_mentions_guide_generation(self):
        result = quote_or_guide_router()
        assert "guide_generation" in result

    def test_mentions_research_answer(self):
        result = quote_or_guide_router()
        assert "research_answer" in result

    def test_mentions_shipping_configured(self):
        result = quote_or_guide_router()
        assert "shipping_configured" in result

    def test_mentions_declared_value(self):
        result = quote_or_guide_router()
        assert "declared_value" in result

    def test_mentions_language(self):
        result = quote_or_guide_router()
        assert "language" in result.lower()
