import io

import pytest
from PIL import Image

from backend.app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite:///:memory:", google_api_key="test-key")


def make_pdf_bytes(page_count: int = 1) -> bytes:
    import fitz

    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), "Sample text")
    data = doc.tobytes()
    doc.close()
    return data


def make_png_bytes(width: int = 20, height: int = 20) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="white").save(buf, format="PNG")
    return buf.getvalue()


def make_jpeg_bytes(width: int = 20, height: int = 20) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="white").save(buf, format="JPEG")
    return buf.getvalue()
