from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])

_templates_dir = Path(__file__).resolve().parents[3].parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/", summary="Upload page")
async def index_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {})
