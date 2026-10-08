from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppException(Exception):
    def __init__(
        self,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        code: str = "BAD_REQUEST",
        title: str = "Bad Request",
        detail: str = "An error occurred.",
        invalid_params: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail
        self.invalid_params = invalid_params or []
        super().__init__(self.detail)


class NotFoundException(AppException):
    def __init__(
        self, detail: str = "The requested resource was not found.", code: str = "NOT_FOUND"
    ) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code=code,
            title="Resource Not Found",
            detail=detail,
        )


class ConflictException(AppException):
    def __init__(
        self,
        detail: str = "The record was modified by another transaction. Please reload and try again.",
        code: str = "VERSION_CONFLICT",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            title="Conflict",
            detail=detail,
        )


class UnauthorizedException(AppException):
    def __init__(
        self, detail: str = "Authentication required.", code: str = "UNAUTHORIZED"
    ) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
            title="Unauthorized",
            detail=detail,
        )


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Permission denied.", code: str = "FORBIDDEN") -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            title="Forbidden",
            detail=detail,
        )


class BusinessRuleException(AppException):
    def __init__(
        self, code: str = "BUSINESS_RULE_VIOLATION", detail: str = "A business rule was violated."
    ) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=code,
            title="Business Rule Violation",
            detail=detail,
        )


# Friendly aliases
AppError = AppException
NotFoundError = NotFoundException
ConflictError = ConflictException
UnauthorizedError = UnauthorizedException
ForbiddenError = ForbiddenException
BusinessRuleError = BusinessRuleException


def create_problem_response(
    status_code: int,
    code: str,
    title: str,
    detail: str,
    request: Request,
    invalid_params: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "type": f"https://api.erp.local/errors/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "instance": str(request.url.path),
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        content["request_id"] = request_id
    if invalid_params:
        content["invalid_params"] = invalid_params

    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json",
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return create_problem_response(
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            request=request,
            invalid_params=exc.invalid_params,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "name": ".".join(str(loc) for loc in err["loc"] if loc != "body"),
                "reason": err["msg"],
            }
            for err in exc.errors()
        ]
        return create_problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            title="Validation Failed",
            detail="One or more fields in the request failed validation.",
            request=request,
            invalid_params=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return create_problem_response(
            status_code=exc.status_code,
            code="HTTP_ERROR",
            title="HTTP Error",
            detail=str(exc.detail),
            request=request,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger("app.errors").exception("Unhandled server exception: %s", exc)
        return create_problem_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            title="Internal Server Error",
            detail="An unexpected server error occurred.",
            request=request,
        )
