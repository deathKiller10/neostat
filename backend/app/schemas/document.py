from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    invoice = "invoice"
    balance_sheet = "balance_sheet"
    profit_and_loss = "profit_and_loss"
    cash_flow_statement = "cash_flow_statement"


class ProcessingStatus(str, Enum):
    pass_ = "PASS"
    failed = "FAILED"


class FileValidationResult(BaseModel):
    file_type: str
    is_supported: bool
    is_readable: bool
    page_count: int
    status: str


class ProcessingMetadata(BaseModel):
    ocr_used: bool
    ocr_engine: str | None = None
    llm_model: str | None = None
    text_source: str
    processed_at: datetime
    processing_time_ms: int


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class DocumentResult(BaseModel):
    """The full shape returned by POST /process and GET by name. extracted_data and
    validation are kept as free-form dicts here because their internal shape is
    document-type-specific (see schemas/extraction.py) -- this model only pins down
    the envelope every document type shares.
    """

    document_name: str
    document_type: DocumentType
    processing_status: str
    overall_confidence: float | None
    file_validation: FileValidationResult
    extracted_data: dict[str, Any]
    validation: dict[str, Any]
    processing_metadata: ProcessingMetadata


class DocumentListItem(BaseModel):
    id: int
    document_name: str
    document_type: DocumentType
    processing_status: str
    overall_confidence: float | None
    processed_at: datetime
    processing_time_ms: int
    file_size_bytes: int
    page_count: int | None
    error_code: str | None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    app_env: str
