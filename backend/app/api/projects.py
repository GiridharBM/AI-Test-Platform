"""Project ingestion, profiling, test discovery, and test plan API endpoints."""

from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core import config
from app.models.project import LocalPathRequest, ProjectDetails, ProjectMeta, ProjectProfile
from app.services import project_ingestion as ingestion
from app.services import project_profiler as profiler
from app.services import project_discovery as discovery

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


@router.post("/{project_id}/discover")
def discover_project(project_id: str):
    """Run deterministic test discovery and return the CodeMap."""
    from app.models.codemap import CodeMap
    codemap = discovery.discover_project(project_id)
    ingestion.save_codemap(config.WORKSPACE_DIR, codemap.model_dump_json())
    return codemap


@router.post("/{project_id}/plan")
def plan_project(project_id: str):
    """Generate a deterministic, prioritised test plan for a project.

    Requires a codemap (run discover first). Builds a lightweight call graph
    from the project's Python source files, scores risk for each testable
    target, and produces a prioritised list of test specifications.
    """
    from app.models.codemap import CodeMap
    from app.models.project import ProjectProfile as Profile
    from app.services.call_graph import build_call_graph
    from app.services.test_planner import generate_test_plan

    raw_codemap = ingestion.read_codemap(config.WORKSPACE_DIR, project_id)
    if not raw_codemap:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="CodeMap not found. Run /discover first.")
    codemap = CodeMap.model_validate_json(raw_codemap)

    raw_profile = ingestion.read_profile(config.WORKSPACE_DIR, project_id)
    if not raw_profile:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Profile not found. Run /profile first.")
    profile = Profile.model_validate_json(raw_profile)

    # Build call graph from source files
    meta = ingestion.read_meta(config.WORKSPACE_DIR, project_id)
    root = Path(meta.source_path) if meta.origin == "path" else ingestion.source_dir(config.WORKSPACE_DIR, project_id)
    source_files = _read_python_files(root)
    call_graph = build_call_graph(source_files)

    plan = generate_test_plan(codemap, profile, call_graph)
    ingestion.save_test_plan(config.WORKSPACE_DIR, plan.model_dump_json())
    return plan


@router.post("/{project_id}/generate")
def generate_project(project_id: str):
    """Generate deterministic test scaffolds from the test plan.

    Requires a test plan (run /plan first). Produces syntactically valid
    Python test files with NotImplementedError placeholders.
    """
    from app.models.codemap import CodeMap
    from app.models.project import ProjectProfile as Profile
    from app.models.test_plan import TestPlan
    from app.services.test_generator import generate_test_scaffolds, write_generated_files

    raw_plan = ingestion.read_test_plan(config.WORKSPACE_DIR, project_id)
    if not raw_plan:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Test plan not found. Run /plan first.")
    plan = TestPlan.model_validate_json(raw_plan)

    raw_codemap = ingestion.read_codemap(config.WORKSPACE_DIR, project_id)
    if not raw_codemap:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="CodeMap not found. Run /discover first.")
    codemap = CodeMap.model_validate_json(raw_codemap)

    raw_profile = ingestion.read_profile(config.WORKSPACE_DIR, project_id)
    if not raw_profile:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Profile not found. Run /profile first.")
    profile = Profile.model_validate_json(raw_profile)

    result = generate_test_scaffolds(plan, codemap, profile)
    write_generated_files(result, config.WORKSPACE_DIR)
    ingestion.save_test_generation(config.WORKSPACE_DIR, result.model_dump_json())
    return result


@router.post("/{project_id}/execute")
def execute_project(project_id: str):
    """Execute generated test scaffolds in a Docker sandbox.

    Requires generated tests (run /generate first). Runs pytest inside
    an isolated container with no network access and bounded resources.
    """
    meta = ingestion.read_meta(config.WORKSPACE_DIR, project_id)

    raw_gen = ingestion.read_test_generation(config.WORKSPACE_DIR, project_id)
    if not raw_gen:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No generated tests. Run /generate first.")

    from app.execution.runner import execute_tests
    generated_dir = Path(config.WORKSPACE_DIR) / project_id / "generated_tests"
    exec_result = execute_tests(generated_dir, project_id)
    ingestion.save_execution(config.WORKSPACE_DIR, exec_result.model_dump_json())
    return exec_result


@router.post("/{project_id}/diagnose")
def diagnose_project(project_id: str):
    """Run deterministic failure diagnosis on a completed execution.

    Requires an execution result (run /execute first). Produces a structured
    DiagnosisResult: what failed, category, fingerprint, linked source
    locations, severity, and optionally (when DIAGNOSIS_AI_ENABLED) a
    local/private AI potential-bug analysis.
    """
    # project exists? (read_meta raises 404 if not)
    ingestion.read_meta(config.WORKSPACE_DIR, project_id)

    if ingestion.read_execution(config.WORKSPACE_DIR, project_id) is None:
        raise HTTPException(
            status_code=422,
            detail="No execution result. Run /execute first.",
        )

    from app.agents.diagnose import diagnose_project as run_diagnosis

    result = run_diagnosis(project_id)
    ingestion.save_diagnosis(config.WORKSPACE_DIR, result.model_dump_json())
    return result


def _read_python_files(root: Path) -> list[tuple[str, str]]:
    """Read all Python files under root, returning (relative_posix_path, content)."""
    from app.core import config as cfg
    files: list[tuple[str, str]] = []
    if not root.is_dir():
        return files
    for path in sorted(root.rglob("*.py")):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        parts = rel.split("/")
        if any(p in cfg.IGNORED_DIRS for p in parts):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            files.append((rel, content))
        except OSError:
            pass
    return files


@router.get("/{project_id}", response_model=ProjectDetails)
def get_project(project_id: str) -> ProjectDetails:
    """Retrieve project metadata, profile, code map, test plan, generated tests, and execution results."""
    meta = ingestion.read_meta(config.WORKSPACE_DIR, project_id)
    raw_profile = ingestion.read_profile(config.WORKSPACE_DIR, project_id)
    profile = ProjectProfile.model_validate_json(raw_profile) if raw_profile else None
    raw_codemap = ingestion.read_codemap(config.WORKSPACE_DIR, project_id)
    codemap = None
    if raw_codemap:
        from app.models.codemap import CodeMap
        codemap = CodeMap.model_validate_json(raw_codemap)
    raw_plan = ingestion.read_test_plan(config.WORKSPACE_DIR, project_id)
    test_plan = None
    if raw_plan:
        from app.models.test_plan import TestPlan
        test_plan = TestPlan.model_validate_json(raw_plan)
    raw_gen = ingestion.read_test_generation(config.WORKSPACE_DIR, project_id)
    test_generation = None
    if raw_gen:
        from app.models.test_generation import TestGenerationResult
        test_generation = TestGenerationResult.model_validate_json(raw_gen)
    raw_exec = ingestion.read_execution(config.WORKSPACE_DIR, project_id)
    execution = None
    if raw_exec:
        from app.models.execution import TestExecutionResult
        execution = TestExecutionResult.model_validate_json(raw_exec)
    raw_diag = ingestion.read_diagnosis(config.WORKSPACE_DIR, project_id)
    diagnosis = None
    if raw_diag:
        from app.models.diagnosis import DiagnosisResult
        diagnosis = DiagnosisResult.model_validate_json(raw_diag)
    return ProjectDetails(
        **meta.model_dump(), profile=profile, codemap=codemap,
        test_plan=test_plan, test_generation=test_generation,
        execution=execution, diagnosis=diagnosis,
    )
