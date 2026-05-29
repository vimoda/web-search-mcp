# web-search-mcp

[🇺🇸 English version](./README.md)

Servidor MCP para búsqueda web sin APIs de pago.
Usa DuckDuckGo para obtener URLs y crawl4ai (Playwright) para leer el contenido completo, incluyendo páginas que renderizan con JavaScript.

Diseñado para LLMs: incluye detección de intención, expansión automática de consultas, puntuación de calidad de fuentes, estado de evidencia y acciones recomendadas para el modelo.

## ¿Cuándo debe un LLM usar este MCP?

### ✅ Usa `web_search` cuando:
- La respuesta puede requerir información **actual, externa o factual**
- El tema es **específico, local, oscuro o poco conocido** (persona, empresa, producto, evento, API)
- Necesitas **verificar, comparar, citar o complementar** tu conocimiento
- El usuario pide **buscar, investigar, verificar o encontrar fuentes**
- Tu conocimiento interno **puede estar incompleto o desactualizado**

### ❌ NO uses el MCP cuando:
- La pregunta es sobre **conocimiento general estable** (mates, física, conceptos básicos)
- La tarea es **escribir, traducir o razonamiento simple**
- Es **programación básica o algoritmos bien conocidos**
- El usuario dice explícitamente **que no busques**

## Tools disponibles

### `web_search` (recomendada)
Herramienta principal para conocimiento externo. Realiza investigación multi-consulta adaptada a la intención: detecta automáticamente si la consulta es sobre una persona, empresa, tema técnico, noticia o general. Expande consultas inteligentemente, puntúa fuentes, extrae páginas con fallback, deduplica y retorna guía de evidencia.

**Parámetros:**
- `query` (requerido): Consulta de búsqueda
- `max_results` (opcional, default: 5): Resultados a retornar (1-10)
- `fetch_content` (opcional, default: true): Extraer contenido completo de la página
- `max_chars_per_result` (opcional, default: 4000): Caracteres por página (500-10000)
- `depth` (opcional, default: `"standard"`): `"quick"` (1 consulta), `"standard"` (3 consultas, default), `"deep"` (6 consultas)
- `purpose` (opcional, default: `"answer"`): `"answer"` | `"verify"` | `"complement"` | `"current_info"` | `"sources"` | `"explore"`
- `search_context` (opcional): Contexto adicional para refinar las búsquedas

**Retorna:** JSON con:
- `evidence_status`: `"strong"` | `"partial"` | `"weak"` | `"none"`
- `recommended_action`: `"answer_normally"` | `"answer_with_caveat"` | `"ask_for_more_context"`
- `answer_guidance`: `{ should_answer, confidence, caveat, suggested_framing }`
- `results[]`: cada uno con `title`, `url`, `snippet`, `content`, `source_quality`, `score`, `ranking_reasons[]`, `content_available`
- `searches_performed[]`, `low_quality_sources[]`

### `search_links`
Búsqueda rápida — solo links, títulos y snippets. Sin fetch de contenido.
Usar cuando el usuario pide expresamente URLs o resultados de búsqueda.

### `fetch_page`
Lee texto limpio de una URL específica con fallback de extracción (crawl4ai -> httpx+bs4 -> HTML metadata).
Usar cuando el usuario da una URL concreta para inspeccionar.

### `multi_search`
Hasta 5 búsquedas en paralelo (solo links/snippets, sin contenido completo).
Para exploración rápida multi-tema.

## MCP Prompts

Estos prompts están registrados en el servidor MCP para guiar el comportamiento del LLM.

| Prompt | Argumentos | Propósito |
|--------|-----------|-----------|
| `web_research_assistant` | — | Prompt general: cuándo/cómo buscar, interpretar evidencia, responder con caveats, regla de idioma |
| `investigate_person` | `name` | Investigar persona: perfil profesional, empresas, cargos, biografía |
| `investigate_company` | `company` | Investigar empresa: sitio oficial, fundadores, liderazgo, noticias, financiación |
| `verify_claim` | `claim` | Verificar afirmación con fuentes |
| `find_sources` | `topic` | Encontrar fuentes autoritativas (docs, sitios oficiales, medios confiables) |
| `answer_from_evidence` | — | Estructurar respuesta usando el JSON de web_search (evidence_status, recommended_action, caveats) |

Todos los prompts incluyen la instrucción de idioma: *"Answer in the same language as the user."*

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `WEB_SEARCH_MAX_CHARS` | `4000` | Máximo de caracteres por página |
| `WEB_SEARCH_REGION` | `mx-es` | Región de búsqueda DuckDuckGo |
| `WEB_SEARCH_TIMEOUT` | `15` | Timeout HTTP en segundos |
| `WEB_SEARCH_LOG_LEVEL` | (silencioso) | Nivel de log: `OFF`/`SILENT` (default), `ERROR`, `INFO`, `DEBUG` |
| `WEB_SEARCH_DEFAULT_DEPTH` | `standard` | Profundidad por defecto: `quick`, `standard`, `deep` |
| `WEB_SEARCH_MAX_CONCURRENT_FETCHES` | `3` | Fetch simultáneos máximos |
| `WEB_SEARCH_FETCH_TIMEOUT` | `20` | Timeout de fallback de fetch en segundos |

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
