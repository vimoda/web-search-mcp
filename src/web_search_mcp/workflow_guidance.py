def _build_llm_workflow_guidance(
    response_intent: str,
    evidence_status: str,
    query_type: str,
) -> dict:
    """Build LLM-facing instructions on HOW to respond after search completes.

    Returns a dict with:
      - response_intent: original intent
      - should_generate_guide: bool
      - should_generate_quote: bool
      - llm_workflow: structured instructions for the LLM
    """
    should_generate_guide = response_intent == "guide_generation"
    should_generate_quote = response_intent == "quote_only"
    is_research = response_intent == "research_answer"

    if response_intent == "quote_only":
        workflow = _quote_workflow(evidence_status)
    elif response_intent == "guide_generation":
        workflow = _guide_workflow(evidence_status, query_type)
    else:
        workflow = _research_workflow(evidence_status)

    return {
        "response_intent": response_intent,
        "should_generate_guide": should_generate_guide,
        "should_generate_quote": should_generate_quote,
        "llm_workflow": workflow,
    }


def _quote_workflow(evidence_status: str) -> str:
    base = (
        "USER INTENT: The user wants pricing / budget / cost information. "
        "Do NOT generate a long guide, tutorial, or implementation steps. "
        "Focus strictly on:\n"
        "1. Prices, plans, subscription tiers, or cost estimates found.\n"
        "2. Currency, billing period (monthly/yearly/one-time).\n"
        "3. Provider/vendor name and what is included.\n"
        "4. If exact prices are not found, provide a range or estimate based on available sources.\n"
        "5. Minimum requirements or prerequisites (if any) that affect pricing.\n"
        "\n"
        "### SHIPPING REQUIREMENTS (always include)\n"
        "- Indicate `shipping_configured` as one of: true / false / unknown.\n"
        "  Base this on what the source says about shipping availability.\n"
        "- If the quote includes shipping, specify: origin, destination, carrier, and estimated delivery time if available.\n"
        "\n"
        "### DECLARED VALUE (for insurance)\n"
        "- Include `declared_value` if the user mentioned it or if insurance is requested.\n"
        "- If the user asked for insurance but did NOT provide a declared value: "
        "you MUST NOT generate a quote. Instead, tell the user that a declared value "
        "is required before quoting and ask them to provide it."
    )
    if evidence_status in ("weak", "none"):
        base += (
            "\n\nIMPORTANT: Sources are limited or unavailable. "
            "Be honest about what could not be verified. "
            "Suggest the user check official sites for current pricing."
        )
    return base


def _guide_workflow(evidence_status: str, query_type: str) -> str:
    base = (
        "USER INTENT: The user wants a guide / workflow / step-by-step instructions. "
        "Structure your response as follows:\n"
        "1. **Prerequisites** — what the user needs before starting.\n"
        "2. **Step-by-step instructions** — numbered steps with clear actions.\n"
        "3. **Decision points** — if there are branching paths, explain when to choose each.\n"
        "4. **Risks / common pitfalls** — what can go wrong and how to avoid it.\n"
        "5. **Next steps** — what to do after completing the guide.\n"
        "\n"
        "Base each step on the information found in the search results. "
        "Do not fabricate steps that are not supported by the sources."
    )
    if query_type == "technical":
        base += (
            "\n\nInclude code snippets, CLI commands, or configuration examples "
            "when available in the sources."
        )
    if evidence_status in ("weak", "none"):
        base += (
            "\n\nNOTE: Available sources are limited. Clearly mark which parts "
            "are based on found information vs general knowledge."
        )
    return base


def _research_workflow(evidence_status: str) -> str:
    base = (
        "USER INTENT: General research. "
        "Synthesize the information found and answer the user's question directly."
    )
    if evidence_status == "strong":
        base += " Evidence is strong — answer with confidence and cite sources."
    elif evidence_status == "partial":
        base += (
            " Evidence is partial — answer with 'Based on available sources' "
            "and note limitations."
        )
    else:
        base += (
            " Evidence is weak or unavailable — do not fabricate. "
            "Explain what could not be found and suggest next steps."
        )
    return base
