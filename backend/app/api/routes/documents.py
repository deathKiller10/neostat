import logging

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_db
from backend.app.core.exceptions import DocumentNotFoundError, EmptyFileError
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentResult,
    DocumentType,
    HealthResponse,
)
from backend.app.services.document_service import DocumentService

logger = logging.getLogger("app.routes")

router = APIRouter(prefix="/api/v1", tags=["documents"])


def get_document_service(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> DocumentService:
    return DocumentService(db, settings)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns 200 with a simple status body. Used by Render's health check.",
)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", app_env=settings.app_env)


@router.post(
    "/documents/process",
    response_model=DocumentResult,
    summary="Upload and process a document",
    description=(
        "Validates, OCRs/reads, extracts, and financially validates a PDF/JPG/PNG "
        "document synchronously, then persists and returns the full result."
    ),
)
async def process_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResult:
    content = await file.read()
    if not content:
        raise EmptyFileError("The uploaded file is empty.")

    result = service.process_upload(content, file.filename or "upload", document_type.value)
    return DocumentResult.model_validate(result)


@router.get(
    "/documents/{document_name}",
    response_model=DocumentResult,
    summary="Get the latest result for a document by name",
    description="Case-insensitive; falls back to matching the name without its file extension.",
)
async def get_document(document_name: str, db: Session = Depends(get_db)) -> DocumentResult:
    repository = DocumentRepository(db)
    document = repository.get_latest_by_name(document_name)
    if document is None:
        raise DocumentNotFoundError(f"No processed document found matching '{document_name}'.")
    return DocumentResult.model_validate(document.result_json)


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List processed documents",
    description="Powers the dashboard table. Supports pagination and filtering by document_type.",
)
async def list_documents(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    document_type: DocumentType | None = Query(None),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    repository = DocumentRepository(db)
    items, total = repository.list(
        limit=limit, offset=offset, document_type=document_type.value if document_type else None
    )
    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)
