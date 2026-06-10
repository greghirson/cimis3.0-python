"""Exceptions raised by the CIMIS client."""

from __future__ import annotations

from typing import Optional


class CimisError(Exception):
    """Base class for all errors raised by this library."""


class CimisApiError(CimisError):
    """The API returned an error response.

    Attributes:
        http_status: HTTP status code of the response.
        error_code: CIMIS error code (e.g. "ERR1012") if one could be
            extracted from the response body, else None.
        message: Human-readable description from the response body.
    """

    def __init__(
        self,
        message: str,
        http_status: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.error_code = error_code

    def __str__(self) -> str:
        parts = []
        if self.http_status is not None:
            parts.append(f"HTTP {self.http_status}")
        if self.error_code:
            parts.append(self.error_code)
        prefix = " ".join(parts)
        return f"[{prefix}] {self.message}" if prefix else self.message


class CimisAuthError(CimisApiError):
    """Missing app key, or the API rejected the app key (ERR1006, HTTP 401/403)."""


class CimisBadRequestError(CimisApiError):
    """HTTP 400 — invalid parameters (bad dates, units, targets, volume limits...)."""


class CimisNotFoundError(CimisApiError):
    """HTTP 404 — unknown station, unsupported zip code, coordinate outside CA..."""


class CimisDataVolumeError(CimisBadRequestError):
    """ERR2112 — the request exceeds the API's maximum record limit.

    Split the request into smaller date ranges or fewer targets.
    """
