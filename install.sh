#!/bin/bash
# install.sh — Instalación desatendida de web-search-mcp
# Uso: curl -fsSL https://raw.githubusercontent.com/tuusuario/web-search-mcp/main/install.sh | bash
set -e

REPO="git+https://github.com/tuusuario/web-search-mcp"
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # sin color

echo -e "${CYAN}[1/3] Verificando dependencias...${NC}"

if ! command -v uv &>/dev/null; then
  echo "uv no encontrado. Instalando..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
fi

echo -e "${CYAN}[2/3] Instalando web-search-mcp desde GitHub...${NC}"
uvx --from "$REPO" web-search-mcp-setup

echo -e "${CYAN}[3/3] Verificando instalación...${NC}"
uvx --from "$REPO" web-search-mcp --help 2>/dev/null || true

echo ""
echo -e "${GREEN}✅ Instalación completa.${NC}"
echo ""
echo "Agrega esto a tu configuración MCP (claude_desktop_config.json o equivalente):"
echo ""
cat <<'JSON'
{
  "mcpServers": {
    "web_search": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/tuusuario/web-search-mcp",
        "web-search-mcp"
      ]
    }
  }
}
JSON
echo ""
echo "Variables de entorno opcionales:"
echo "  WEB_SEARCH_MAX_CHARS  — Máximo de chars por página (default: 4000)"
echo "  WEB_SEARCH_REGION     — Región de búsqueda DDG (default: mx-es)"
echo "  WEB_SEARCH_TIMEOUT    — Timeout en segundos (default: 15)"
