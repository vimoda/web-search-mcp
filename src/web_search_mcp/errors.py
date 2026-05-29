import httpx


def _handle_http_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 403:
            return "Error 403: Access denied by the site (possible bot blocking)."
        if code == 404:
            return "Error 404: Page not found."
        if code == 429:
            return "Error 429: Rate limit reached. Wait a few seconds."
        return f"Error HTTP {code}: {e.response.reason_phrase}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Timeout connecting to the server."
    if isinstance(e, httpx.ConnectError):
        return "Error: Could not connect. Check the URL or your connection."
    return f"Unexpected error: {type(e).__name__}: {e}"
