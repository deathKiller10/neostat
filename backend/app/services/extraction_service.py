import io
from dataclasses import dataclass

import fitz
from PIL import Image

from backend.app.services.ocr_service import OCRProvider

RENDER_DPI = 300
NATIVE_TEXT_LAYER_MIN_CHARS = 100


@dataclass
class PreparedPage:
    page_number: int
    image: Image.Image
    text: str
    text_source: str
    ocr_mean_confidence: float | None


def prepare_pages(content: bytes, mime_type: str, ocr_provider: OCRProvider) -> list[PreparedPage]:
    """Turns raw file bytes into per-page (image, text) pairs the LLM extraction step
    consumes. A PDF page is only OCR'd when it has no usable text layer -- most of the
    HDFC statement pages are vector-drawn with no text layer at all, so this is the
    common path for that document type, while a real text layer (more accurate) is
    used whenever present.
    """
    if mime_type == "application/pdf":
        return _prepare_pdf_pages(content, ocr_provider)
    return _prepare_image_page(content, ocr_provider)


def _prepare_pdf_pages(content: bytes, ocr_provider: OCRProvider) -> list[PreparedPage]:
    pdf = fitz.open(stream=content, filetype="pdf")
    pages = []
    try:
        for index in range(pdf.page_count):
            page = pdf[index]
            pix = page.get_pixmap(dpi=RENDER_DPI)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            native_text = page.get_text().strip()
            if len(native_text) > NATIVE_TEXT_LAYER_MIN_CHARS:
                pages.append(
                    PreparedPage(
                        page_number=index + 1,
                        image=image,
                        text=native_text,
                        text_source="native_text",
                        ocr_mean_confidence=None,
                    )
                )
            else:
                ocr_result = ocr_provider.extract(image)
                pages.append(
                    PreparedPage(
                        page_number=index + 1,
                        image=image,
                        text=ocr_result.text,
                        text_source="rendered_ocr",
                        ocr_mean_confidence=ocr_result.mean_confidence,
                    )
                )
    finally:
        pdf.close()
    return pages


def _prepare_image_page(content: bytes, ocr_provider: OCRProvider) -> list[PreparedPage]:
    image = Image.open(io.BytesIO(content)).convert("RGB")
    ocr_result = ocr_provider.extract(image)
    return [
        PreparedPage(
            page_number=1,
            image=image,
            text=ocr_result.text,
            text_source="rendered_ocr",
            ocr_mean_confidence=ocr_result.mean_confidence,
        )
    ]
