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
import requests


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


# A stalled socket is not an answer, it is the absence of one — and gspread
# ships with NO timeout at all (HTTPClient.timeout is None), so before
# SheetsService set one these could hang for as long as the network let them.
NETWORK_FAULTS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


def is_transient(exc: Exception) -> bool:
    """Worth trying again in a moment?"""
    if isinstance(exc, gspread.exceptions.APIError):
        return status_code(exc) in TRANSIENT_CODES
    # A read that timed out or never connected says nothing about the sheet, so
    # reading again is safe. A WRITE that timed out says nothing either — but
    # there the ambiguity cuts the other way and it may well have landed, which
    # is why retry_reads is never put around one. See the module docstring.
    return isinstance(exc, NETWORK_FAULTS)


# How long the whole thing may take, retries included. Attempts alone are the
# wrong budget once a timeout counts as transient: three tries at a 20-second
# timeout is a minute, and a read spends that minute holding the lock that
# st.cache_data puts around a cache miss — so it is not one person waiting, it
# is everybody who wants the same figure. A 503 comes back in milliseconds and
# still gets all three tries; a stall gets one and then gives up.
RETRY_DEADLINE_SECONDS = 25.0


def retry_reads(
    call: Callable[[], T],
    *,
    attempts: int = 3,
    delay: float = 0.4,
    deadline: float = RETRY_DEADLINE_SECONDS,
) -> T:
    """Run a READ, giving Google a couple of chances to answer.

    Never wrap a write in this. See the module docstring.
    """
    started = time.monotonic()
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 — re-raised below unless transient
            if not is_transient(exc):
                raise
            last = exc
            if attempt >= attempts - 1 or time.monotonic() - started >= deadline:
                break
            time.sleep(delay * (2**attempt))
    assert last is not None
    raise last
