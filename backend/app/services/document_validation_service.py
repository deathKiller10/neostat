import io
import logging
from pathlib import Path

import fitz
from PIL import Image

from backend.app.core.config import Settings
from backend.app.core.exceptions import (
    CorruptedFileError,
    EmptyFileError,
    FileTooLargeError,
    PageLimitExceededError,
    UnsupportedFileTypeError,
)
from backend.app.schemas.document import FileValidationResult

logger = logging.getLogger("app.validation")

EXTENSION_MIME_MAP = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}

_PDF_MAGIC = b"%PDF"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def sniff_content_type(content: bytes) -> str:
    """Sniff the real content type from file bytes rather than trusting the client's
    declared Content-Type. Tries libmagic first (present on both Windows dev via
    python-magic-bin and the Docker image via libmagic1); falls back to matching
    well-known magic-byte headers if libmagic isn't importable.
    """
    try:
        import magic

        return magic.from_buffer(content, mime=True)
    except Exception:
        if content.startswith(_PDF_MAGIC):
            return "application/pdf"
        if content.startswith(_JPEG_MAGIC):
            return "image/jpeg"
        if content.startswith(_PNG_MAGIC):
            return "image/png"
        return "application/octet-stream"


def validate_upload(content: bytes, filename: str, settings: Settings) -> FileValidationResult:
    """Runs the input-control checks required before any OCR or LLM call. This is
    deliberately not document-type classification -- it only decides whether the
    bytes are a readable PDF/JPG/PNG within our size and page limits.
    """
    if len(content) == 0:
        raise EmptyFileError("The uploaded file is empty.")

    ext = Path(filename).suffix.lower()
    expected_mimes = EXTENSION_MIME_MAP.get(ext)
    detected_mime = sniff_content_type(content)

    if expected_mimes is None or detected_mime not in expected_mimes:
        raise UnsupportedFileTypeError(
            f"Only PDF / JPG / PNG documents are supported (got extension '{ext}', "
            f"detected content type '{detected_mime}')."
        )

    page_count = 1
    if detected_mime == "application/pdf":
        try:
            pdf = fitz.open(stream=content, filetype="pdf")
            page_count = pdf.page_count
            pdf.close()
        except Exception as exc:
            raise CorruptedFileError(f"The PDF could not be opened: {exc}") from exc
        if page_count == 0:
            raise CorruptedFileError("The PDF has no pages.")
        if page_count > settings.max_page_count:
            raise PageLimitExceededError(
                f"Document has {page_count} pages, the limit is {settings.max_page_count}."
            )
    else:
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
        except Exception as exc:
            raise CorruptedFileError(f"The image could not be decoded: {exc}") from exc

    if len(content) > settings.max_upload_bytes:
        raise FileTooLargeError(
            f"File is {len(content)} bytes, the limit is {settings.max_upload_bytes} bytes."
        )

    logger.info(
        "file_validation_passed",
        extra={"filename": filename, "content_type": detected_mime, "page_count": page_count},
    )

    return FileValidationResult(
        file_type=detected_mime,
        is_supported=True,
        is_readable=True,
        page_count=page_count,
        status="PASS",
    )
