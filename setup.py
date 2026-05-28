"""
Script de post-instalación para web-search-mcp.
Instala Playwright + Chromium requeridos por crawl4ai.
"""

import subprocess
import sys


def run_setup() -> None:
    print("Instalando dependencias de crawl4ai (Playwright + Chromium)...")
    try:
        subprocess.run(
            [sys.executable, "-m", "crawl4ai.setup"],
            check=True,
        )
        print("\n✅ Setup completo. Ya puedes usar web-search-mcp.")
        print("\nAgrega esto a tu configuración MCP:")
        print("""
{
  "mcpServers": {
    "web_search": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tuusuario/web-search-mcp", "web-search-mcp"]
    }
  }
}
""")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error durante el setup: {e}", file=sys.stderr)
        print("Intenta correr manualmente: python -m crawl4ai.setup", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_setup()
