import urllib.parse
import httpx
from bs4 import BeautifulSoup
from .config import HEADERS, DDGS_SEARCH_URL, SEARCH_REGION, REQUEST_TIMEOUT
from .logging_config import log


async def _ddg_search(query: str, max_results: int) -> list[dict]:
    log.info("Searching: \"%s\" (max=%d, region=%s)", query, max_results, SEARCH_REGION)
    async with httpx.AsyncClient(headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        r = await client.post(DDGS_SEARCH_URL, data={"q": query, "kl": SEARCH_REGION})
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for result in soup.select(".result")[:max_results]:
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        if url.startswith("//duckduckgo.com/l/?uddg="):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = urllib.parse.unquote(qs.get("uddg", [url])[0])

        if url and title:
            results.append({"title": title, "url": url, "snippet": snippet})

    log.info("Results for \"%s\": %d", query, len(results))
    return results
