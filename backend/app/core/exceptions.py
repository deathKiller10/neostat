import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app")


class AppError(Exception):
    """Base for every error the app raises on purpose. Each subclass fixes its own
    HTTP status and error code so route handlers never have to pick one inline.
    """

    code = "INTERNAL_ERROR"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class UnsupportedFileTypeError(AppError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


class EmptyFileError(AppError):
    code = "EMPTY_FILE"
    status_code = status.HTTP_400_BAD_REQUEST


class CorruptedFileError(AppError):
    code = "CORRUPTED_FILE"
    status_code = status.HTTP_400_BAD_REQUEST


class PageLimitExceededError(AppError):
    code = "PAGE_LIMIT_EXCEEDED"
    status_code = status.HTTP_400_BAD_REQUEST


class FileTooLargeError(AppError):
    code = "FILE_TOO_LARGE"
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


class DocumentNotFoundError(AppError):
    code = "DOCUMENT_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class InvalidDocumentTypeError(AppError):
    code = "INVALID_DOCUMENT_TYPE"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class OcrFailedError(AppError):
    code = "OCR_FAILED"
    status_code = status.HTTP_502_BAD_GATEWAY


class ExtractionFailedError(AppError):
    code = "EXTRACTION_FAILED"
    status_code = status.HTTP_502_BAD_GATEWAY


class LlmTimeoutError(AppError):
    code = "LLM_TIMEOUT"
    status_code = status.HTTP_504_GATEWAY_TIMEOUT


class LlmRateLimitedError(AppError):
    code = "LLM_RATE_LIMITED"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class DatabaseError(AppError):
    code = "DATABASE_ERROR"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        logger.warning(
            "app_error",
            extra={"request_id": getattr(request.state, "request_id", None), "code": exc.code},
        )
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("INVALID_DOCUMENT_TYPE", "Request validation failed: " + str(exc.errors())),
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.error("unhandled_exception", extra={"request_id": request_id}, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                "INTERNAL_ERROR",
                f"An unexpected error occurred. Reference id: {request_id}",
            ),
        )
