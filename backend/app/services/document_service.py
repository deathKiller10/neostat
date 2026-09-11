import logging
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.services import extraction_merge, financial_checks
from backend.app.services.confidence import VALIDATION_FAIL_PENALTY
from backend.app.services.document_validation_service import validate_upload
from backend.app.services.extraction_service import extract, prepare_pages
from backend.app.services.llm_provider import get_llm_provider
from backend.app.services.ocr_service import get_ocr_provider

logger = logging.getLogger("app.document_service")

MANDATORY_INVOICE_FIELDS = ("total_amount", "invoice_number")


def _meets_minimum_fields(extracted_data: dict, document_type: str) -> bool:
    """Distinguishes a genuinely unprocessable document (nothing usable came back)
    from one that processed fine but failed a financial check -- the two are kept
    separate in the API response (processing_status vs validation.overall_status).
    """
    if document_type == "invoice":
        return any(extracted_data.get(name, {}).get("value") is not None for name in MANDATORY_INVOICE_FIELDS)
    line_items = extracted_data.get("line_items", [])
    return any(
        field.get("value") is not None for item in line_items for field in item.get("values", {}).values()
    )


def _apply_validation_penalty(extracted_data: dict, validation: dict) -> None:
    failing_operand_names = set()
    for check in validation["checks"]:
        if check["status"] == "FAIL":
            failing_operand_names.update(check["operands"].keys())

    for name in failing_operand_names:
        field = extracted_data.get(name)
        if isinstance(field, dict) and field.get("value") is not None and "confidence" in field:
            field["confidence"] = round(field["confidence"] * VALIDATION_FAIL_PENALTY, 4)


class DocumentService:
    """Orchestrates the pipeline end to end: validate -> prepare pages -> extract ->
    validate financials -> persist. Routes call this and nothing else; it's the only
    place that touches every stage.
    """

    def __init__(self, db: Session, settings: Settings):
        self.settings = settings
        self.repository = DocumentRepository(db)
        self.ocr_provider = get_ocr_provider(settings.ocr_provider)
        self.llm_provider = get_llm_provider(settings.llm_provider, settings.google_api_key, settings.llm_model)

    def process_upload(self, content: bytes, filename: str, document_type: str) -> dict:
        start = time.monotonic()

        file_validation = validate_upload(content, filename, self.settings)
        logger.info(
            "file_validation_result",
            extra={"document_filename": filename, "status": file_validation.status, "page_count": file_validation.page_count},
        )

        pages = prepare_pages(content, file_validation.file_type, self.ocr_provider)
        logger.info(
            "pages_prepared",
            extra={"document_filename": filename, "page_count": len(pages), "sources": [p.text_source for p in pages]},
        )

        extracted_data, overall_confidence = extract(pages, document_type, self.llm_provider)
        logger.info("extraction_completed", extra={"document_filename": filename, "overall_confidence": overall_confidence})

        validation = financial_checks.validate(
            extracted_data, document_type, self.settings.validation_abs_tol, self.settings.validation_rel_tol
        )
        _apply_validation_penalty(extracted_data, validation)
        overall_confidence = extraction_merge.recompute_overall_confidence(extracted_data, document_type)
        logger.info(
            "financial_validation_completed",
            extra={"document_filename": filename, "overall_status": validation["overall_status"], "issue_count": len(validation["issues"])},
        )

        processing_status = "PASS" if _meets_minimum_fields(extracted_data, document_type) else "FAILED"
        processing_time_ms = int((time.monotonic() - start) * 1000)

        result = {
            "document_name": filename,
            "document_type": document_type,
            "processing_status": processing_status,
            "overall_confidence": overall_confidence,
            "file_validation": file_validation.model_dump(),
            "extracted_data": extracted_data,
            "validation": validation,
            "processing_metadata": {
                "ocr_used": any(p.text_source == "rendered_ocr" for p in pages),
                "ocr_engine": self.settings.ocr_provider if any(p.text_source == "rendered_ocr" for p in pages) else None,
                "llm_model": self.settings.llm_model,
                "text_source": pages[0].text_source if pages else "unknown",
                "processed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "processing_time_ms": processing_time_ms,
            },
        }

        self.repository.create(
            document_name=filename,
            document_type=document_type,
            processing_status=processing_status,
            overall_confidence=overall_confidence,
            result_json=result,
            processing_time_ms=processing_time_ms,
            file_size_bytes=len(content),
            page_count=file_validation.page_count,
            error_code=None,
        )
        logger.info("document_persisted", extra={"document_filename": filename, "processing_status": processing_status})

        return result
