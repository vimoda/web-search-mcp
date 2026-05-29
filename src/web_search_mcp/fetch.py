import asyncio
import re
import httpx
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from .config import HEADERS, MAX_TEXT_LENGTH, WEB_SEARCH_MAX_CONCURRENT_FETCHES, WEB_SEARCH_FETCH_TIMEOUT
from .logging_config import log

_fetch_semaphore = asyncio.Semaphore(WEB_SEARCH_MAX_CONCURRENT_FETCHES)


async def _fetch_page(url: str, max_chars: int = MAX_TEXT_LENGTH) -> str:
    log.info("Fetching: %s", url)
    config = CrawlerRunConfig(
        word_count_threshold=10,
        exclude_external_links=True,
        remove_overlay_elements=True,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)

    if not result.success:
        raise RuntimeError(result.error_message or "crawl4ai could not fetch the page")

    text = result.markdown or result.cleaned_html or ""
    return text[:max_chars]


async def _fetch_page_with_fallback(url: str, max_chars: int = MAX_TEXT_LENGTH) -> dict:
    method = "none"
    content = ""
    error = None

    try:
        async with _fetch_semaphore:
            content = await _fetch_page(url, max_chars)
        if content and len(content.strip()) > 100:
            return {"content": content, "method": "crawl4ai", "error": None}
        method = "crawl4ai (partial)"
    except Exception as e:
        error = str(e)
        method = "crawl4ai (failed)"

    try:
        async with _fetch_semaphore:
            async with httpx.AsyncClient(
                headers={**HEADERS, "Accept": "text/html"},
                timeout=WEB_SEARCH_FETCH_TIMEOUT,
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        if text and len(text) > 100:
            return {"content": text[:max_chars], "method": "httpx+bs4", "error": None}

        method = "httpx+bs4 (partial)"
    except Exception as e2:
        if not error:
            error = str(e2)
        method = "httpx+bs4 (failed)"

    try:
        soup = BeautifulSoup(r.text, "html.parser") if 'soup' in dir() else BeautifulSoup("", "html.parser")
        if not soup.get_text(strip=True):
            async with httpx.AsyncClient(timeout=WEB_SEARCH_FETCH_TIMEOUT, follow_redirects=True) as client:
                r = await client.get(url, headers=HEADERS)
                soup = BeautifulSoup(r.text, "html.parser")

        meta_parts = []
        title = soup.find("title")
        if title:
            meta_parts.append(title.get_text(strip=True))
        for name in ("description", "og:description", "og:title"):
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                meta_parts.append(tag["content"].strip())

        content = " — ".join(meta_parts) if meta_parts else ""
        if content:
            return {"content": content[:max_chars], "method": "html metadata", "error": None}
    except Exception:
        pass

    return {"content": "", "method": method, "error": error or "no content extracted"}
