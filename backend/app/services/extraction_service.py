import io
from dataclasses import dataclass

import fitz
from PIL import Image
from pydantic import BaseModel

from backend.app.schemas.extraction import EXTRACTION_SCHEMAS
from backend.app.services.llm_provider import LLMProvider
from backend.app.services.ocr_service import OCRProvider, OcrWord

RENDER_DPI = 300
NATIVE_TEXT_LAYER_MIN_CHARS = 100


@dataclass
class PreparedPage:
    page_number: int
    image: Image.Image
    text: str
    text_source: str
    ocr_mean_confidence: float | None
    ocr_words: list[OcrWord]


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
                        ocr_words=[],
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
                        ocr_words=ocr_result.words,
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
            ocr_words=ocr_result.words,
        )
    ]


INVOICE_GUIDANCE = (
    "This is a retail invoice or receipt. Tax may already be included in the displayed "
    "total (look for wording like 'Inclusive' or 'Incl. GST') or added on top of a "
    "subtotal -- read is_tax_inclusive from what the document actually says, don't "
    "assume. Capture every line item shown, not just the first few."
)

FINANCIAL_STATEMENT_GUIDANCE = (
    "This is a page from an Indian bank's annual report, typically with amounts in INR "
    "crore ('₹ in crore', sometimes with the rupee sign rendered as a backtick) and two "
    "comparative year columns. Negative amounts are shown in brackets, e.g. "
    "'(1,546.40)' means -1546.40 -- convert brackets to a negative number yourself. "
    "Transcribe every line item visible on the page, including subtotals such as "
    "'Total', in the order they appear, and record each comparative period as a "
    "separate entry in `values` keyed by the exact period label shown in the column "
    "header (e.g. 'March 31, 2024')."
)


def _numbered_lines(text: str) -> str:
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(text.splitlines()))


def build_prompt(document_type: str, page: PreparedPage) -> str:
    guidance = INVOICE_GUIDANCE if document_type == "invoice" else FINANCIAL_STATEMENT_GUIDANCE
    return (
        f"You are extracting structured data from a {document_type.replace('_', ' ')} "
        f"document, page {page.page_number}. {guidance}\n\n"
        "Rules:\n"
        "- Transcribe every visible line item; do not limit yourself to a fixed list of fields.\n"
        "- If a value is unreadable, unclear, or not present on this page, return null for it "
        "-- never guess or invent a number.\n"
        "- Preserve label text exactly as printed, including capitalization and punctuation.\n"
        "- Return numeric fields as plain numbers with bracketed negatives already converted "
        "(e.g. '(1,546.40)' -> -1546.40), no thousands separators or currency symbols.\n"
        "- For every field you fill in, quote the exact source line it came from in `source_text`.\n\n"
        f"OCR text for this page, with line numbers for reference:\n{_numbered_lines(page.text)}\n"
    )


def extract(
    prepared_pages: list[PreparedPage], document_type: str, llm: LLMProvider
) -> tuple[dict, float]:
    """Calls the LLM once per page (schema depends on document_type) and merges the
    per-page results into the extracted_data shape the API returns, with confidence
    and grounding computed for every field.
    """
    schema = EXTRACTION_SCHEMAS[document_type]
    page_results: list[tuple[PreparedPage, BaseModel]] = []
    for page in prepared_pages:
        prompt = build_prompt(document_type, page)
        raw = llm.generate_structured(prompt, page.image, schema)
        page_results.append((page, raw))

    if document_type == "invoice":
        from backend.app.services.extraction_merge import build_invoice_extracted_data

        return build_invoice_extracted_data(page_results)

    from backend.app.services.extraction_merge import build_financial_extracted_data

    return build_financial_extracted_data(page_results)
