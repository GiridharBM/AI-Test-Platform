"""Project ingestion and profiling API endpoints."""

from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, UploadFile

from app.core import config
from app.models.project import LocalPathRequest, ProjectDetails, ProjectMeta, ProjectProfile
from app.services import project_ingestion as ingestion
from app.services import project_profiler as profiler

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/upload", response_model=ProjectMeta)
def upload_project(
    files: Annotated[list[UploadFile], File(description="Files of the project folder.")],
    paths: Annotated[Optional[list[str]], Form()] = None,
) -> ProjectMeta:
    """Upload a project folder. The browser supplies each file's relative
    path either via the multipart filename or via a parallel `paths` form
    field (aligned by index)."""
    if paths is not None and len(paths) != len(files):
        raise ingestion.IngestionError(
            status_code=400,
            detail="`paths` field count must match file count.",
        )
    payload: list[tuple[str, bytes]] = []
    for i, f in enumerate(files):
        rel = (paths[i] if paths else None) or f.filename or ""
        content = f.file.read(config.MAX_FILE_SIZE_BYTES + 1)
        payload.append((rel, content))
    return ingestion.save_upload(payload)


@router.post("/from-path", response_model=ProjectMeta)
def add_local_project(body: LocalPathRequest) -> ProjectMeta:
    """Register an explicitly selected local directory for READ-ONLY profiling."""
    return ingestion.register_local_project(body.path)


@router.post("/{project_id}/profile", response_model=ProjectProfile)
def profile_existing_project(project_id: str) -> ProjectProfile:
    """Deterministically scan a registered project and return its profile."""
    profile = profiler.profile_project(project_id)
    ingestion.save_profile(config.WORKSPACE_DIR, profile.model_dump_json())
    return profile


@router.get("/{project_id}", response_model=ProjectDetails)
def get_project(project_id: str) -> ProjectDetails:
    """Retrieve project metadata and the generated profile, if any."""
    meta = ingestion.read_meta(config.WORKSPACE_DIR, project_id)
    raw_profile = ingestion.read_profile(config.WORKSPACE_DIR, project_id)
    profile = ProjectProfile.model_validate_json(raw_profile) if raw_profile else None
    return ProjectDetails(**meta.model_dump(), profile=profile)
