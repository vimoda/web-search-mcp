# web-search-mcp

[🇪🇸 Versión en español](./README.es.md)

MCP server for web search without paid APIs.
Uses DuckDuckGo to get URLs and crawl4ai (Playwright) to read the full content, including pages that render with JavaScript.

Designed for LLMs: includes intent detection, auto query expansion, source quality scoring, evidence status, and recommended actions for the model.

## When should an LLM use this MCP?

### ✅ Use `web_search` when:
- The answer may require **current, external, or factual** information
- The topic is **specific, local, obscure, or little-known** (person, company, product, event, API)
- You need to **verify, compare, cite, or complement** your knowledge
- The user asks to **search, investigate, verify, or find sources**
- Your internal knowledge **may be incomplete or outdated**

### ❌ Do NOT use MCP when:
- The question is about **stable general knowledge** (math, physics, basic concepts)
- The task is **writing, translation, or simple reasoning**
- It's **basic programming or well-known algorithms**
- The user explicitly says **not to search**

## Available Tools

### `web_search` (recommended)
Primary tool for external knowledge. Performs multi-query research adapted to intent: auto-detects whether the query is about a person, company, technical topic, news, or general. Expands queries intelligently, scores sources, fetches pages with fallback, deduplicates, and returns evidence guidance.

**Parameters:**
- `query` (required): Search query
- `max_results` (optional, default: 5): Results to return (1-10)
- `fetch_content` (optional, default: true): Extract full page content
- `max_chars_per_result` (optional, default: 4000): Characters per page (500-10000)
- `depth` (optional, default: `"standard"`): `"quick"` (1 query), `"standard"` (3 queries, default), `"deep"` (6 queries)
- `purpose` (optional, default: `"answer"`): `"answer"` | `"verify"` | `"complement"` | `"current_info"` | `"sources"` | `"explore"`
- `search_context` (optional): Additional context to refine search queries

**Returns:** JSON with:
- `evidence_status`: `"strong"` | `"partial"` | `"weak"` | `"none"`
- `recommended_action`: `"answer_normally"` | `"answer_with_caveat"` | `"ask_for_more_context"`
- `answer_guidance`: `{ should_answer, confidence, caveat, suggested_framing }`
- `results[]`: each with `title`, `url`, `snippet`, `content`, `source_quality`, `score`, `ranking_reasons[]`, `content_available`
- `searches_performed[]`, `low_quality_sources[]`

### `search_links`
Quick search — links, titles, and snippets only. No page content fetching.
Use when the user explicitly asks for URLs or search results.

### `fetch_page`
Reads clean text from a specific URL with extraction fallback (crawl4ai -> httpx+bs4 -> HTML metadata).
Use when the user provides a specific URL to inspect.

### `multi_search`
Up to 5 parallel searches (links/snippets only, no full content).
Use for quick multi-topic exploration.

## MCP Prompts

These prompts are registered on the MCP server and can be attached to guide LLM behavior.

| Prompt | Arguments | Purpose |
|--------|-----------|---------|
| `web_research_assistant` | — | General system prompt: when/how to search, interpret evidence, answer with caveats, language rule |
| `investigate_person` | `name` | Research a person: professional profile, companies, roles, biography |
| `investigate_company` | `company` | Research a company: official site, founders, leadership, news, funding |
| `verify_claim` | `claim` | Fact-check a statement with source-backed verification |
| `find_sources` | `topic` | Find authoritative sources (docs, official sites, reliable media) |
| `answer_from_evidence` | — | Structure an answer using web_search JSON results (evidence_status, recommended_action, caveats) |

Every prompt includes the language instruction: *"Answer in the same language as the user."*

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_SEARCH_MAX_CHARS` | `4000` | Max characters per page |
| `WEB_SEARCH_REGION` | `mx-es` | DuckDuckGo search region |
| `WEB_SEARCH_TIMEOUT` | `15` | HTTP timeout in seconds |
| `WEB_SEARCH_LOG_LEVEL` | (silent) | Log level: `OFF`/`SILENT` (default), `ERROR`, `INFO`, `DEBUG` |
| `WEB_SEARCH_DEFAULT_DEPTH` | `standard` | Default search depth: `quick`, `standard`, `deep` |
| `WEB_SEARCH_MAX_CONCURRENT_FETCHES` | `3` | Max simultaneous page fetches |
| `WEB_SEARCH_FETCH_TIMEOUT` | `20` | Fetch fallback timeout in seconds |

---

## Installation Options

### Option 1 — Automatic script (recommended for agents)

Installs everything with a single command, including Playwright and Chromium:

```bash
curl -fsSL https://raw.githubusercontent.com/tuusuario/web-search-mcp/main/install.sh | bash
```

The script:
1. Checks / installs `uv` if not present
2. Installs the package from GitHub
3. Runs `web-search-mcp-setup` (installs Playwright + Chromium)
4. Prints the JSON config block ready to copy

---

### Option 2 — uvx from GitHub (without cloning)

```bash
# Step 1: setup (first time only)
uvx --from git+https://github.com/tuusuario/web-search-mcp web-search-mcp-setup

# Step 2: ready to use
uvx --from git+https://github.com/tuusuario/web-search-mcp web-search-mcp
```

MCP configuration:

```json
{
  "mcpServers": {
    "web_search": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/vimoda/web-search-mcp",
        "web-search-mcp"
      ]
    }
  }
}
```

With environment variables:

```json
{
  "mcpServers": {
    "web_search": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/tuusuario/web-search-mcp",
        "web-search-mcp"
      ],
      "env": {
        "WEB_SEARCH_MAX_CHARS": "8000",
        "WEB_SEARCH_REGION": "us-en",
        "WEB_SEARCH_TIMEOUT": "20"
      }
    }
  }
}
```

Point to a specific tag or commit:

```json
"args": ["--from", "git+https://github.com/tuusuario/web-search-mcp@v1.0.0", "web-search-mcp"]
```

---

### Option 3 — uvx from PyPI (if published)

```bash
# Setup (first time only)
uvx web-search-mcp-setup

# Use
uvx web-search-mcp
```

MCP configuration:

```json
{
  "mcpServers": {
    "web_search": {
      "command": "uvx",
      "args": ["web-search-mcp"]
    }
  }
}
```

---

### Option 4 — pip / uv install local (development)

```bash
git clone https://github.com/tuusuario/web-search-mcp
cd web-search-mcp

# Install in virtual environment
uv venv && uv pip install -e .

# crawl4ai setup
web-search-mcp-setup

# Run
web-search-mcp
```

MCP configuration pointing to the local environment:

```json
{
  "mcpServers": {
    "web_search": {
      "command": "/path/to/venv/bin/web-search-mcp"
    }
  }
}
```

---

### Option 5 — pip install from GitHub (without uv)

```bash
pip install git+https://github.com/tuusuario/web-search-mcp
web-search-mcp-setup
```

MCP configuration:

```json
{
  "mcpServers": {
    "web_search": {
      "command": "web-search-mcp"
    }
  }
}
```

---

## Where to put the MCP configuration

| Client | File |
|---------|------|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code | `.claude/mcp_config.json` in the project, or global config |
| Custom agent | Wherever your MCP client expects it |

---

## Test the installation

```bash
# With MCP Inspector (interactive UI)
npx @modelcontextprotocol/inspector uvx --from git+https://github.com/tuusuario/web-search-mcp web-search-mcp

# Or if installed locally
npx @modelcontextprotocol/inspector web-search-mcp
```

---

## Publish to PyPI

```bash
uv build
uv publish --token $PYPI_TOKEN
```

Once published, Option 3 works without the GitHub URL.

---

## Project structure

```
web-search-mcp/
├── install.sh                        # Automatic installation script
├── pyproject.toml                    # Metadata and dependencies
├── README.es.md
└── src/
    └── web_search_mcp/
        ├── __init__.py
        ├── server.py                 # MCP server (tools)
        └── setup.py                  # Post-install: Playwright + Chromium
```
