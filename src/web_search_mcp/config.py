import os
import logging


MAX_TEXT_LENGTH = int(os.getenv("WEB_SEARCH_MAX_CHARS", "4000"))
SEARCH_REGION = os.getenv("WEB_SEARCH_REGION", "mx-es")
REQUEST_TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "15"))
WEB_SEARCH_DEFAULT_DEPTH = os.getenv("WEB_SEARCH_DEFAULT_DEPTH", "standard")
WEB_SEARCH_MAX_CONCURRENT_FETCHES = int(os.getenv("WEB_SEARCH_MAX_CONCURRENT_FETCHES", "3"))
WEB_SEARCH_FETCH_TIMEOUT = int(os.getenv("WEB_SEARCH_FETCH_TIMEOUT", "20"))
LOG_LEVEL = os.getenv("WEB_SEARCH_LOG_LEVEL", "")

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_SILENT = LOG_LEVEL.upper().strip() in ("OFF", "SILENT", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

DDGS_SEARCH_URL = "https://html.duckduckgo.com/html/"
