import logging
from .config import LOG_LEVEL, LOG_LEVELS, _SILENT

log = logging.getLogger("web-search-mcp")
log.propagate = False
_configured_level = LOG_LEVELS.get(LOG_LEVEL.upper().strip())

if _SILENT:
    log.disabled = True
    log.setLevel(logging.CRITICAL + 1)
    for _name in ("mcp", "httpx", "httpcore"):
        _l = logging.getLogger(_name)
        _l.disabled = True
        _l.setLevel(logging.CRITICAL + 1)
        _l.propagate = False
else:
    log.disabled = False
    log.setLevel(_configured_level)
    handler = logging.StreamHandler()
    handler.setLevel(_configured_level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    log.addHandler(handler)
    for _name in ("httpx", "httpcore"):
        _l = logging.getLogger(_name)
        _l.setLevel(_configured_level)
