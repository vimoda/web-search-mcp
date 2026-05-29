import re

_QUOTE_KEYWORDS = {
    "cotizar", "cotización", "cotizacion", "presupuesto", "precio", "costo",
    "tarifa", "quote", "pricing", "price", "cost", "estimate", "plans",
    "plan pricing", "subscription fee", "cuanto cuesta", "cuánto cuesta",
    "vale", "valor", "budget", "presupuestar", "fee", "rates",
}

_QUERY_LOWERCASE_QUOTE_MARKERS = {
    "cuanto cuesta", "cuánto cuesta", "how much", "how much does",
    "price of", "cost of", "precio de", "precio del", "precio por",
    "cotizar", "cotización", "presupuesto para",
}

_GUIDE_KEYWORDS = {
    "guía", "guia", "paso a paso", "pasoapaso", "flujo", "workflow",
    "cómo hacer", "como hacer", "how to", "implementation guide",
    "roadmap", "plan de acción", "plan de accion", "tutorial",
    "step by step", "steps", "procedure", "procedimiento",
    "walkthrough", "checklist", "guide", "best practices",
    "buenas prácticas", "buenas practicas", "deployment guide",
    "setup guide", "configuración", "configuration",
}

_QUERY_LOWERCASE_GUIDE_MARKERS = {
    "how to", "cómo hacer", "como hacer", "paso a paso", "step by step",
    "guía para", "guia para", "genera una guía", "create a guide",
    "implementation steps", "workflow for", "flujo para",
}


def _detect_response_intent(
    query: str,
    purpose: str,
    search_context: str | None = None,
) -> str:
    """Detect whether the user wants a quote, a guide, or general research.

    Returns one of:
      - "quote_only": user wants pricing / budget info, no guide needed.
      - "guide_generation": user wants step-by-step instructions or workflow.
      - "research_answer": general factual research (default).
    """
    text = f"{query} {search_context or ''}".lower()

    if purpose in ("quote", "guide"):
        return {"quote": "quote_only", "guide": "guide_generation"}[purpose]

    for marker in _QUERY_LOWERCASE_QUOTE_MARKERS:
        if marker in text:
            return "quote_only"

    for marker in _QUERY_LOWERCASE_GUIDE_MARKERS:
        if marker in text:
            return "guide_generation"

    quote_score = sum(2 for kw in _QUOTE_KEYWORDS if f" {kw} " in f" {text} ")
    guide_score = sum(2 for kw in _GUIDE_KEYWORDS if f" {kw} " in f" {text} ")

    if quote_score > 0 and quote_score >= guide_score:
        return "quote_only"
    if guide_score > 0 and guide_score >= quote_score:
        return "guide_generation"

    return "research_answer"


_INSURANCE_KEYWORDS = {
    "seguro", "asegurado", "insurance", "insured", "con seguro",
    "con cobertura", "cobertura", "cover", "protection", "protección",
}

_DECLARED_VALUE_PATTERNS = [
    r"valor\s*declarado\s*(?:de\s*)?[$]?\s*(\d[\d.,]*)",
    r"declared\s*value\s*(?:of\s*)?[$]?\s*(\d[\d.,]*)",
    r"valor\s*(?:de\s*)?[$]?\s*(\d[\d.,]*)\s*(?:d[óo]lares|pesos|eur|usd|mxn)?\s*(?:de\s*)?(?:declarado|asegurado)",
    r"[$]\s*(\d[\d.,]*)\s*(?:valor|declared|asegurado)",
    r"asegurar\s*(?:por|hasta)\s*[$]?\s*(\d[\d.,]*)",
]


def _detect_quote_requirements(query: str, search_context: str | None = None) -> dict:
    """Detect insurance and declared value requirements from the query.

    Returns:
        insurance_requested: bool — whether the user asked for insurance
        declared_value: int | None — extracted value if present
        missing_declared_value: bool — True if insurance is requested but no value given
    """
    text = f"{query} {search_context or ''}".lower()

    insurance_requested = any(kw in text for kw in _INSURANCE_KEYWORDS)

    declared_value: int | None = None
    full_text = f"{query} {' '.join(search_context.split()) if search_context else ''}"
    for pattern in _DECLARED_VALUE_PATTERNS:
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            try:
                raw = m.group(1).replace(",", "").replace(".", "")
                declared_value = int(raw)
                break
            except (ValueError, IndexError):
                continue

    missing_declared_value = insurance_requested and declared_value is None

    return {
        "insurance_requested": insurance_requested,
        "declared_value": declared_value,
        "missing_declared_value": missing_declared_value,
    }


def _get_response_intent_display(intent: str) -> str:
    labels = {
        "quote_only": "quote (pricing / budget)",
        "guide_generation": "guide / workflow",
        "research_answer": "general research",
    }
    return labels.get(intent, "general research")
