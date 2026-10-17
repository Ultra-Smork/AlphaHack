"""Define the single application error type.

Every layer raises AppError for expected failures. Transport layers map it to
an HTTP status and a stable machine code via responses. Wrapping a sentinel
keeps the original status/code:

    raise apperr.wrap(apperr.ERR_NOT_FOUND, cause)
"""

from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """An expected application error carrying an HTTP status and a stable
    machine-readable code. The wrapped cause (if any) is never sent to clients.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        cause: BaseException | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.cause = cause
        detail = f"{code}: {cause}" if cause is not None else f"{code}: {message}"
        super().__init__(detail)


def new(status: int, code: str, message: str) -> AppError:
    """Build a fresh error."""
    return AppError(status, code, message)


def wrap(sentinel: AppError, cause: BaseException) -> AppError:
    """Attach a cause to a sentinel. The cause is logged, not returned."""
    return AppError(sentinel.status, sentinel.code, sentinel.message, cause=cause)


# Sentinel errors. Add domain errors here as the app grows.
ERR_BAD_REQUEST = new(HTTPStatus.BAD_REQUEST, "bad_request", "invalid request")
ERR_UNAUTHORIZED = new(HTTPStatus.UNAUTHORIZED, "unauthorized", "authentication required")
ERR_FORBIDDEN = new(HTTPStatus.FORBIDDEN, "forbidden", "not allowed")
ERR_NOT_FOUND = new(HTTPStatus.NOT_FOUND, "not_found", "resource not found")
ERR_CONFLICT = new(HTTPStatus.CONFLICT, "conflict", "resource conflict")
ERR_INTERNAL = new(HTTPStatus.INTERNAL_SERVER_ERROR, "internal", "internal error")


def from_error(err: BaseException) -> AppError:
    """Map any error to an AppError, defaulting to ERR_INTERNAL for unknown types."""
    if isinstance(err, AppError):
        return err
    return wrap(ERR_INTERNAL, err)
