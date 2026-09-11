from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import documents, pages
from backend.app.core.config import get_settings
from backend.app.core.database import init_db
from backend.app.core.exceptions import register_exception_handlers
from backend.app.core.logging import RequestIdMiddleware, configure_logging

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Neostat Document Intelligence",
    description=(
        "Uploads invoices and HDFC Bank financial statements, extracts structured "
        "data via OCR + a vision LLM, runs financial validation, and persists results."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

_static_dir = Path(__file__).resolve().parents[2] / "frontend" / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(documents.router)
app.include_router(pages.router)
