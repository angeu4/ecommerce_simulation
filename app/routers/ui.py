from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.logging_setup import get_logger

router = APIRouter(prefix="")
templates = Jinja2Templates(directory="templates")
logger = get_logger(__name__)


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    logger.info("UI: landing page served", extra={"request_id": request.state.request_id})
    return templates.TemplateResponse("landing.html", {"request": request})


@router.get("/user", response_class=HTMLResponse)
async def user_ui(request: Request):
    logger.info("UI: user page served", extra={"request_id": request.state.request_id})
    return templates.TemplateResponse("user.html", {"request": request})


@router.get("/admin", response_class=HTMLResponse)
async def admin_ui(request: Request):
    logger.info("UI: admin page served", extra={"request_id": request.state.request_id})
    return templates.TemplateResponse("admin.html", {"request": request})
