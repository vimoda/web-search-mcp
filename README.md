# web-search-mcp

[🇪🇸 Versión en español](./README.es.md)

MCP server for web search without paid APIs.
Uses DuckDuckGo to get URLs and crawl4ai (Playwright) to read the full content, including pages that render with JavaScript.

## Available Tools

| Tool | Description | Use when |
|------|-------------|----------|
| `web_search` | **(Recommended)** Searches, reads pages, extracts text, returns sources | User needs an answer, explanation, summary, or current facts |
| `search_links` | Searches and returns only links, titles, and snippets | User explicitly wants URLs or quick search results |
| `fetch_page` | Reads clean text from a specific URL (supports JS) | User provides a specific URL to inspect |
| `multi_search` | Up to 5 parallel searches (links/snippets only) | User asks to investigate multiple topics at once |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_SEARCH_MAX_CHARS` | `4000` | Max characters per page |
| `WEB_SEARCH_REGION` | `mx-es` | DuckDuckGo search region |
| `WEB_SEARCH_TIMEOUT` | `15` | HTTP timeout in seconds |
| `WEB_SEARCH_LOG_LEVEL` | (silent) | Log level: `OFF`/`SILENT` (default), `ERROR`, `INFO`, `DEBUG`. Set to show action logs on stderr |

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
