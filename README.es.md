# web-search-mcp

[🇺🇸 English version](./README.md)

Servidor MCP para búsqueda web sin APIs de pago.
Usa DuckDuckGo para obtener URLs y crawl4ai (Playwright) para leer el contenido completo, incluyendo páginas que renderizan con JavaScript.

## Tools disponibles

### `web_search` (recomendada)
Herramienta de investigación completa. Busca múltiples queries relacionadas, evalúa calidad de fuentes, penaliza redes sociales y contenido vacío, hace fetch selectivo y retorna resultados estructurados con metadatos de calidad.

**Parámetros:**
- `query` (requerido): Consulta de búsqueda
- `max_results` (opcional, default: 5): Resultados a retornar (1-10)
- `fetch_content` (opcional, default: true): Traer contenido completo
- `max_chars_per_result` (opcional, default: 4000): Carácteres por página (500-10000)
- `depth` (opcional, default: `"standard"`): Profundidad de investigación
  - `"quick"`: 1 búsqueda, resultados directos
  - `"standard"`: 3 búsquedas relacionadas, filtrado de calidad
  - `"deep"`: 6 búsquedas relacionadas, cobertura exhaustiva

**Retorna:** JSON con `results[]` (cada uno con `source_quality`, `content_available`), `searches_performed[]`, `low_quality_sources[]`

### `search_links`
Búsqueda rápida — solo links, títulos y snippets. Usar cuando el usuario pide expresamente URLs.

### `fetch_page`
Lee texto limpio de una URL específica (soporta JS). Usar cuando el usuario da una URL concreta.

### `multi_search`
Hasta 5 búsquedas en paralelo (solo links/snippets). Para exploración multi-tema.

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `WEB_SEARCH_MAX_CHARS` | `4000` | Máximo de caracteres por página |
| `WEB_SEARCH_REGION` | `mx-es` | Región de búsqueda DuckDuckGo |
| `WEB_SEARCH_TIMEOUT` | `15` | Timeout HTTP en segundos |
| `WEB_SEARCH_LOG_LEVEL` | (silencioso) | Nivel de log: `OFF`/`SILENT` (default), `ERROR`, `INFO`, `DEBUG`. Asignar para ver acciones en stderr |

---

## Opciones de instalación

### Opción 1 — Script automático (recomendado para agentes)

Instala todo con un solo comando, incluyendo Playwright y Chromium:

```bash
curl -fsSL https://raw.githubusercontent.com/tuusuario/web-search-mcp/main/install.sh | bash
```

El script:
1. Verifica / instala `uv` si no está presente
2. Instala el paquete desde GitHub
3. Corre `web-search-mcp-setup` (instala Playwright + Chromium)
4. Imprime el bloque JSON de configuración listo para copiar

---

### Opción 2 — uvx desde GitHub (sin clonar)

```bash
# Paso 1: setup (solo la primera vez)
uvx --from git+https://github.com/tuusuario/web-search-mcp web-search-mcp-setup

# Paso 2: ya puedes usarlo
uvx --from git+https://github.com/tuusuario/web-search-mcp web-search-mcp
```

Configuración MCP:

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

Con variables de entorno:

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

Apuntar a un tag o commit específico:

```json
"args": ["--from", "git+https://github.com/tuusuario/web-search-mcp@v1.0.0", "web-search-mcp"]
```

---

### Opción 3 — uvx desde PyPI (si está publicado)

```bash
# Setup (solo la primera vez)
uvx web-search-mcp-setup

# Usar
uvx web-search-mcp
```

Configuración MCP:

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

### Opción 4 — pip / uv install local (desarrollo)

```bash
git clone https://github.com/tuusuario/web-search-mcp
cd web-search-mcp

# Instalar en entorno virtual
uv venv && uv pip install -e .

# Setup de crawl4ai
web-search-mcp-setup

# Ejecutar
web-search-mcp
```

Configuración MCP apuntando al entorno local:

```json
{
  "mcpServers": {
    "web_search": {
      "command": "/ruta/al/venv/bin/web-search-mcp"
    }
  }
}
```

---

### Opción 5 — pip install desde GitHub (sin uv)

```bash
pip install git+https://github.com/tuusuario/web-search-mcp
web-search-mcp-setup
```

Configuración MCP:

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

## Dónde va la configuración MCP

| Cliente | Archivo |
|---------|---------|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code | `.claude/mcp_config.json` en el proyecto, o config global |
| Agente custom | Donde tu cliente MCP lo espere |

---

## Probar la instalación

```bash
# Con MCP Inspector (UI interactiva)
npx @modelcontextprotocol/inspector uvx --from git+https://github.com/tuusuario/web-search-mcp web-search-mcp

# O si instalaste localmente
npx @modelcontextprotocol/inspector web-search-mcp
```

---

## Publicar en PyPI

```bash
uv build
uv publish --token $PYPI_TOKEN
```

Una vez publicado, la Opción 3 funciona sin necesidad de la URL de GitHub.

---

## Estructura del proyecto

```
web-search-mcp/
├── install.sh                        # Script de instalación automática
├── pyproject.toml                    # Metadata y dependencias
├── README.md
└── src/
    └── web_search_mcp/
        ├── __init__.py
        ├── server.py                 # MCP server (tools)
        └── setup.py                  # Post-install: Playwright + Chromium
```
