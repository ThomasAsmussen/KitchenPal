"""Telling a Google outage apart from our own mistake.

Every call in this app is an HTTPS round trip to somebody else's service, and
that service is occasionally unavailable for a few seconds. Nothing here caught
that, so a Google hiccup showed residents a Python traceback and a dead page —
four of them in one evening on 2026-08-30, all APIError 503 at connect time.

A retry is only ever applied to READS. A 5xx on a write is ambiguous: the write
may well have landed, and the answer to "did the sheet take it?" is not in the
exception. Retrying a write that already succeeded charges somebody's dinner
twice, which is far worse than showing them an error and letting them press the
button again.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

import gspread


T = TypeVar("T")

# 5xx is Google having a bad moment; 429 is us being asked to slow down. Both
# are worth waiting out. Everything else (403 no access, 404 renamed sheet) is a
# fact about our configuration that will still be true in half a second.
TRANSIENT_CODES = frozenset({429, 500, 502, 503, 504})


def status_code(exc: Exception) -> int | None:
    """The HTTP status behind a gspread error, when there is one.

    APIError.code is -1 when the body could not be parsed as JSON, which is
    exactly what a proxy's HTML error page looks like — so fall back to the
    response itself rather than trusting the -1.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code > 0:
        return code
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def is_transient(exc: Exception) -> bool:
    """Worth trying again in a moment?"""
    if isinstance(exc, gspread.exceptions.APIError):
        return status_code(exc) in TRANSIENT_CODES
    return False


def retry_reads(call: Callable[[], T], *, attempts: int = 3, delay: float = 0.4) -> T:
    """Run a READ, giving Google a couple of chances to answer.

    Never wrap a write in this. See the module docstring.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 — re-raised below unless transient
            if not is_transient(exc):
                raise
            last = exc
            if attempt < attempts - 1:
                time.sleep(delay * (2**attempt))
    assert last is not None
    raise last
