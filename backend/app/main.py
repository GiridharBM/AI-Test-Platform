from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.projects import router as projects_router

app = FastAPI(title="AI Test Platform")

app.include_router(projects_router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-test-platform"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
