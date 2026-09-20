import logging
from pathlib import Path

from fastapi import FastAPI, Response

from app.api.projects import router as projects_router
from app.core.logging import configure_logging
from app.models.readiness import ReadinessReport
from app.services.readiness import check_readiness

configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="AI Test Platform")

app.include_router(projects_router)

logger.info("app.started", extra={
    "fields": {"event": "app_started", "service": "ai-test-platform"},
})

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-test-platform"}


@app.get("/ready")
def ready(response: Response) -> ReadinessReport:
    report = ReadinessReport(**check_readiness())
    if report.status != "ready":
        response.status_code = 503
    return report


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
