import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.documents import get_document_service
from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.schemas.extraction import InvoiceExtraction, NumField, StrField
from backend.app.services.document_service import DocumentService
from backend.app.services.ocr_service import OcrResult
from backend.tests.conftest import make_jpeg_bytes, make_pdf_bytes


class MockLLM:
    def __init__(self, response=None):
        self.response = response or InvoiceExtraction(
            invoice_number=StrField(value="INV-001"),
            total_amount=NumField(value=9.00, source_text="Total 9.00"),
        )

    def generate_structured(self, prompt, image, schema):
        return self.response


class MockOCR:
    def extract(self, image):
        return OcrResult(text="Total 9.00", mean_confidence=0.9, words=[])


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def override_get_document_service(db=None):
        db = TestingSession()
        from backend.app.core.config import Settings

        service = DocumentService(db, Settings(database_url="sqlite:///:memory:", google_api_key="test"))
        service.llm_provider = MockLLM()
        service.ocr_provider = MockOCR()
        return service

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_document_service] = override_get_document_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_invoice_happy_path(client):
    files = {"file": ("invoice.jpg", io.BytesIO(make_jpeg_bytes(100, 100)), "image/jpeg")}
    data = {"document_type": "invoice"}
    response = client.post("/api/v1/documents/process", files=files, data=data)
    assert response.status_code == 200
    body = response.json()
    assert body["document_name"] == "invoice.jpg"
    assert body["extracted_data"]["invoice_number"]["value"] == "INV-001"
    assert body["processing_status"] == "PASS"


def test_upload_unsupported_type_returns_415(client):
    files = {"file": ("invoice.txt", io.BytesIO(b"not a real file"), "text/plain")}
    data = {"document_type": "invoice"}
    response = client.post("/api/v1/documents/process", files=files, data=data)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_page_limit_exceeded_returns_400(client):
    files = {"file": ("statement.pdf", io.BytesIO(make_pdf_bytes(5)), "application/pdf")}
    data = {"document_type": "balance_sheet"}
    response = client.post("/api/v1/documents/process", files=files, data=data)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAGE_LIMIT_EXCEEDED"


def test_upload_invalid_document_type_returns_422(client):
    files = {"file": ("invoice.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg")}
    data = {"document_type": "not_a_real_type"}
    response = client.post("/api/v1/documents/process", files=files, data=data)
    assert response.status_code == 422


def test_get_by_name_returns_latest(client):
    files = {"file": ("invoice.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg")}
    data = {"document_type": "invoice"}
    client.post("/api/v1/documents/process", files=files, data=data)
    client.post("/api/v1/documents/process", files=files, data=data)

    response = client.get("/api/v1/documents/invoice.jpg")
    assert response.status_code == 200
    assert response.json()["document_name"] == "invoice.jpg"


def test_get_by_name_case_insensitive_and_no_extension(client):
    files = {"file": ("Invoice.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg")}
    data = {"document_type": "invoice"}
    client.post("/api/v1/documents/process", files=files, data=data)

    assert client.get("/api/v1/documents/invoice.jpg").status_code == 200
    assert client.get("/api/v1/documents/Invoice").status_code == 200


def test_get_by_name_not_found_returns_404(client):
    response = client.get("/api/v1/documents/does-not-exist.jpg")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_list_documents(client):
    files = {"file": ("invoice.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg")}
    data = {"document_type": "invoice"}
    client.post("/api/v1/documents/process", files=files, data=data)

    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["document_name"] == "invoice.jpg"


def test_list_documents_filters_by_type(client):
    files = {"file": ("invoice.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg")}
    client.post("/api/v1/documents/process", files=files, data={"document_type": "invoice"})

    response = client.get("/api/v1/documents", params={"document_type": "balance_sheet"})
    assert response.status_code == 200
    assert response.json()["total"] == 0
