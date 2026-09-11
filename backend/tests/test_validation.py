import pytest

from backend.app.core.exceptions import (
    CorruptedFileError,
    EmptyFileError,
    FileTooLargeError,
    PageLimitExceededError,
    UnsupportedFileTypeError,
)
from backend.app.services.document_validation_service import validate_upload
from backend.tests.conftest import make_jpeg_bytes, make_pdf_bytes, make_png_bytes


def test_empty_file_rejected(settings):
    with pytest.raises(EmptyFileError):
        validate_upload(b"", "invoice.pdf", settings)


def test_valid_pdf_passes(settings):
    result = validate_upload(make_pdf_bytes(1), "statement.pdf", settings)
    assert result.status == "PASS"
    assert result.file_type == "application/pdf"
    assert result.page_count == 1


def test_valid_jpeg_passes(settings):
    result = validate_upload(make_jpeg_bytes(), "invoice.jpg", settings)
    assert result.status == "PASS"
    assert result.file_type == "image/jpeg"


def test_valid_png_passes(settings):
    result = validate_upload(make_png_bytes(), "invoice.png", settings)
    assert result.status == "PASS"
    assert result.file_type == "image/png"


def test_unsupported_extension_rejected(settings):
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(make_pdf_bytes(1), "statement.txt", settings)


def test_extension_content_mismatch_rejected(settings):
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(make_png_bytes(), "invoice.pdf", settings)


def test_corrupted_pdf_rejected(settings):
    with pytest.raises(CorruptedFileError):
        validate_upload(b"%PDF-1.4 not really a pdf", "statement.pdf", settings)


def test_corrupted_image_rejected(settings):
    with pytest.raises(CorruptedFileError):
        validate_upload(b"\xff\xd8\xff\x00garbage", "invoice.jpg", settings)


def test_page_limit_exceeded_rejected(settings):
    with pytest.raises(PageLimitExceededError):
        validate_upload(make_pdf_bytes(settings.max_page_count + 1), "statement.pdf", settings)


def test_file_too_large_rejected(settings):
    settings.max_upload_mb = 0
    with pytest.raises(FileTooLargeError):
        validate_upload(make_jpeg_bytes(200, 200), "invoice.jpg", settings)
