from mcp.server.fastmcp import FastMCP
from .config import _SILENT, LOG_LEVEL

mcp_log_level = "CRITICAL" if _SILENT else LOG_LEVEL.upper().strip()
mcp = FastMCP("web_search_mcp", log_level=mcp_log_level)

from . import tools
from .schemas import SearchInput, LinkSearchInput, FetchInput, MultiSearchInput

mcp.tool(
    name="web_search",
    annotations={
        "title": "Web search with iterative research (recommended for external info)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)(tools.web_search)

mcp.tool(
    name="search_links",
    annotations={
        "title": "Search links and snippets only (fast results, no content fetch)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)(tools.search_links)

mcp.tool(
    name="fetch_page",
    annotations={
        "title": "Read content from a specific web page",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)(tools.fetch_page)

mcp.tool(
    name="multi_search",
    annotations={
        "title": "Multiple parallel searches (links/snippets only, no full content)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)(tools.multi_search)

from . import prompts

mcp.prompt()(prompts.web_research_assistant)
mcp.prompt()(prompts.investigate_person)
mcp.prompt()(prompts.investigate_company)
mcp.prompt()(prompts.verify_claim)
mcp.prompt()(prompts.find_sources)
mcp.prompt()(prompts.answer_from_evidence)
mcp.prompt()(prompts.quote_or_guide_router)
