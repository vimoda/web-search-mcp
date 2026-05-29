def _compute_evidence_status(
    results: list[dict],
    low_quality: list[dict],
    total_queries: int,
) -> dict:
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
