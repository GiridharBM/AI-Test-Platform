"""Project ingestion, profiling, test discovery, and test plan API endpoints."""

from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core import config
from app.models.pipeline import PipelineState
from app.models.project import LocalPathRequest, ProjectDetails, ProjectMeta, ProjectProfile
from app.models.results import ResultsDigest
from app.services import project_export
from app.services import project_ingestion as ingestion
from app.services import project_profiler as profiler
from app.services import project_discovery as discovery
from app.services import pipeline as pipeline_service

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
    meta = ingestion.save_upload(payload)
    # Upload success automatically starts the sequential pipeline (Profile ->
    # Discover -> Plan -> Generate -> Execute -> Diagnose -> Improve loop). The
    # pipeline is best-effort: it must never break the upload response, and any
    # failure is recorded in the pipeline state for resume.
    try:
        pipeline_service.start_pipeline(meta.project_id)
    except Exception:
        pass
    return meta


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
    source_root = ingestion.source_root(config.WORKSPACE_DIR, project_id)
    exec_result = execute_tests(generated_dir, project_id, source_root=source_root)
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


@router.post("/{project_id}/improve")
def improve_project(project_id: str):
    """Improve failing generated tests deterministically from a diagnosis.

    Requires a diagnosis result (run /diagnose first). Replaces safe
    NotImplementedError scaffold placeholders with import-and-invoke bodies
    whose inputs come only from the TestPlan's explicit edge-case evidence —
    never fabricating inputs or assertions and only writing to the
    generated-tests workspace (source/.meta are untouched).
    """
    ingestion.read_meta(config.WORKSPACE_DIR, project_id)

    if ingestion.read_diagnosis(config.WORKSPACE_DIR, project_id) is None:
        raise HTTPException(
            status_code=422,
            detail="No diagnosis result. Run /diagnose first.",
        )

    from app.services.improvement import improve_project as run_improvement

    result = run_improvement(project_id)
    ingestion.save_improvement(config.WORKSPACE_DIR, result.model_dump_json())
    return result


@router.post("/{project_id}/retest")
def retest_project(project_id: str):
    """Re-test M8-improved generated tests in the M6 Docker sandbox.

    Verifies whether the M8 improvement changes fixed the diagnosed failures.
    Requires an improvement result (run /improve first).

    Orchestrator-aware: when the project has pipeline state this is the
    ``awaiting_retest_decision`` gate action. It runs the identical re-test
    business logic via the pipeline (enforcing the gate and advancing the
    state machine, e.g. ``still_failing`` -> ``awaiting_repair_decision``)
    and returns the resulting PipelineState. Without pipeline state the
    legacy standalone M9 behaviour is unchanged.
    """
    ingestion.read_meta(config.WORKSPACE_DIR, project_id)

    if ingestion.read_pipeline(config.WORKSPACE_DIR, project_id) is not None:
        from app.services import pipeline as pipeline_service

        try:
            return pipeline_service.decide_retest(project_id)
        except pipeline_service.PipelineGateError as exc:
            raise _pipeline_gate_error(exc)

    if ingestion.read_improvement(config.WORKSPACE_DIR, project_id) is None:
        raise HTTPException(
            status_code=422,
            detail="No improvement result. Run /improve first.",
        )

    from app.services.retest import retest_project as run_retest

    result = run_retest(project_id)
    return result


@router.post("/{project_id}/evaluate")
def evaluate_project(project_id: str):
    """Evaluate the testing pipeline: coverage, mutation, and benchmark.

    Runs three independent evaluation components over the project's source and
    generated tests inside the M6 Docker sandbox and returns a single
    EvaluationResult. Missing artifacts or unavailable components report
    explicit blocked/unavailable component statuses rather than failing the
    whole evaluation.
    """
    from app.evaluation.orchestrator import evaluate_project as run_evaluation

    return run_evaluation(project_id)


@router.post("/{project_id}/repair")
def repair_project(project_id: str):
    """Generate and validate bounded source repair candidates (M11).

    Consumes the M7 diagnosis, M3 CodeMap, M4 TestPlan and M9 re-test result.
    Validates each evidence-supported candidate ONLY inside an isolated repair
    workspace using the existing M6 Docker runner, stopping at the first pass
    (or after REPAIR_MAX_ATTEMPTS). NEVER modifies the original source here;
    a passing candidate is returned as `validated_pending_approval` awaiting
    explicit human approval via /approve.

    Orchestrator-aware: when the project has pipeline state this is the
    ``awaiting_repair_decision`` gate action. It runs the identical bounded
    repair business logic via the pipeline (enforcing the gate and advancing
    the state machine; a validated candidate stops at
    ``awaiting_repair_approval`` for explicit approval) and returns the
    resulting PipelineState. Without pipeline state the legacy standalone
    M11 behaviour is unchanged.
    """
    ingestion.read_meta(config.WORKSPACE_DIR, project_id)

    if ingestion.read_pipeline(config.WORKSPACE_DIR, project_id) is not None:
        from app.services import pipeline as pipeline_service

        try:
            return pipeline_service.decide_repair(project_id)
        except pipeline_service.PipelineGateError as exc:
            raise _pipeline_gate_error(exc)

    if ingestion.read_retest(config.WORKSPACE_DIR, project_id) is None:
        raise HTTPException(
            status_code=422,
            detail="No re-test result. Run /retest first.",
        )

    from app.services.repair import repair_project as run_repair

    return run_repair(project_id)


@router.post("/{project_id}/repair/approve")
def repair_approve(project_id: str):
    """Explicit human approval: apply the validated candidate to original source.

    Applies ONLY the exact candidate that passed sandbox validation, after
    verifying candidate state, source existence/containment, and that the
    original source still matches the candidate's expected `before` content.
    Runs final validation against the applied source. Refuses to overwrite
    newer user changes.

    Orchestrator-aware: when the project has pipeline state this is the
    ``awaiting_repair_approval`` human action. It runs the identical
    approval business logic via the pipeline (enforcing the gate and advancing
    the state machine) and returns the resulting PipelineState. Without
    pipeline state the legacy standalone M11 behaviour is unchanged.
    """
    ingestion.read_meta(config.WORKSPACE_DIR, project_id)

    if ingestion.read_pipeline(config.WORKSPACE_DIR, project_id) is not None:
        from app.services import pipeline as pipeline_service

        try:
            return pipeline_service.decide_approve(project_id)
        except pipeline_service.PipelineGateError as exc:
            raise _pipeline_gate_error(exc)

    if ingestion.read_repair(config.WORKSPACE_DIR, project_id) is None:
        raise HTTPException(
            status_code=422,
            detail="No repair result. Run /repair first.",
        )

    from app.services.repair import approve_repair as run_approve

    return run_approve(project_id)


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


# ---------------------------------------------------------------------------
# Autonomous pipeline endpoints
# ---------------------------------------------------------------------------


def _pipeline_gate_error(exc: pipeline_service.PipelineGateError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.post("/{project_id}/pipeline/start", response_model=PipelineState)
def pipeline_start(project_id: str):
    """Start (or return the existing) sequential pipeline for a project.

    AUTOMATIC stages (no user action needed): Profile, Discover, Plan,
    Generate, Execute, Diagnose, and the bounded Improve->Execute->Diagnose
    loop.

    The pipeline advances only when each stage's persisted semantic success
    predicate passes; a failed/blocked/unavailable stage stops it. Uploading a
    project already auto-starts this pipeline, so calling start is normally
    unnecessary. Repeated starts are idempotent and return the current state.
    """
    try:
        return pipeline_service.start_pipeline(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.get("/{project_id}/pipeline", response_model=PipelineState)
def pipeline_get(project_id: str):
    """Return the current persisted pipeline state for a project."""
    ingestion.read_meta(config.WORKSPACE_DIR, project_id)
    raw = ingestion.read_pipeline(config.WORKSPACE_DIR, project_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="No pipeline state for this project.")
    return PipelineState.model_validate_json(raw)


@router.post("/{project_id}/pipeline/resume", response_model=PipelineState)
def pipeline_resume(project_id: str):
    """Resume the pipeline after a failed/unavailable stage.

    Retries the failed/unavailable stage (e.g. Execute after Docker returns),
    then continues the automatic chain. Safe no-op at human gates or terminal
    states: those are never auto-crossed.
    """
    try:
        return pipeline_service.resume_pipeline(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.post("/{project_id}/pipeline/retest", response_model=PipelineState)
def pipeline_retest(project_id: str):
    """Explicit USER DECISION: run the M9 re-test of improved tests.

    Only permitted at `awaiting_retest_decision`. If the re-test proves the
    improvements (fixed/passed) the pipeline completes; otherwise it proceeds
    to the source-repair decision gate.
    """
    try:
        return pipeline_service.decide_retest(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.post("/{project_id}/pipeline/skip-retest", response_model=PipelineState)
def pipeline_skip_retest(project_id: str):
    """Explicit USER DECISION: skip the M9 re-test and proceed to source-repair decision."""
    try:
        return pipeline_service.decide_skip_retest(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.post("/{project_id}/pipeline/repair", response_model=PipelineState)
def pipeline_repair(project_id: str):
    """Explicit USER DECISION: run bounded M11 source repair (M11).

    Only permitted at `awaiting_repair_decision`. Original source is never
    modified; a validated candidate stops at `awaiting_repair_approval`.
    """
    try:
        return pipeline_service.decide_repair(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.post("/{project_id}/pipeline/skip-repair", response_model=PipelineState)
def pipeline_skip_repair(project_id: str):
    """Explicit USER DECISION: skip source repair; the pipeline completes."""
    try:
        return pipeline_service.decide_skip_repair(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.post("/{project_id}/pipeline/approve", response_model=PipelineState)
def pipeline_approve(project_id: str):
    """Explicit USER APPROVAL: apply the exact validated M11 candidate.

    Only permitted at `awaiting_repair_approval`. Runs final validation after
    applying; source is never modified without this approval.
    """
    try:
        return pipeline_service.decide_approve(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.post("/{project_id}/pipeline/reject", response_model=PipelineState)
def pipeline_reject(project_id: str):
    """Explicit USER REJECTION of the M11 candidate.

    Source remains unchanged; the pipeline records `approval rejected` and
    stops. No alternative repair is applied automatically.
    """
    try:
        return pipeline_service.decide_reject(project_id)
    except pipeline_service.PipelineGateError as exc:
        raise _pipeline_gate_error(exc)


@router.get("/{project_id}/export")
def export_project(project_id: str):
    """Download a completed upload-origin project as a ZIP (M12).

    The archive contains the authoritative workspace source tree plus a
    PROJECT_EXPORT.json manifest. Read-only: never mutates source, .meta,
    pipeline, or repair state. Gated to ``overall_status == 'completed'``;
    unknown/traversal ids are 404, path-origin projects are 400, and any
    non-completed pipeline is 409.
    """
    zip_path, filename = project_export.build_project_zip(project_id)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(project_export.cleanup_export_zip, zip_path),
    )


@router.get("/{project_id}/results", response_model=ResultsDigest)
def get_project_results(project_id: str) -> ResultsDigest:
    """Return a read-only results digest for a project (M13).

    Derives a bounded, developer-friendly summary of the testing outcome from
    the persisted .meta artifacts. Never mutates state, never exposes source or
    test contents, full tracebacks, host/sandbox paths, environment variables,
    or secrets. Unknown projects are 404; missing/partial artifacts render as
    explicit null/unavailable sections rather than fabricated states.
    """
    from app.services.results import build_results_digest

    return build_results_digest(project_id)


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
    raw_improve = ingestion.read_improvement(config.WORKSPACE_DIR, project_id)
    improvement = None
    if raw_improve:
        from app.models.improvement import ImprovementResult
        improvement = ImprovementResult.model_validate_json(raw_improve)
    raw_retest = ingestion.read_retest(config.WORKSPACE_DIR, project_id)
    retest = None
    if raw_retest:
        from app.models.retest import ReTestResult
        retest = ReTestResult.model_validate_json(raw_retest)
    raw_eval = ingestion.read_evaluation(config.WORKSPACE_DIR, project_id)
    evaluation = None
    if raw_eval:
        from app.models.evaluation import EvaluationResult
        evaluation = EvaluationResult.model_validate_json(raw_eval)
    raw_repair = ingestion.read_repair(config.WORKSPACE_DIR, project_id)
    repair = None
    if raw_repair:
        from app.models.repair import RepairResult
        repair = RepairResult.model_validate_json(raw_repair)
    return ProjectDetails(
        **meta.model_dump(), profile=profile, codemap=codemap,
        test_plan=test_plan, test_generation=test_generation,
        execution=execution, diagnosis=diagnosis,
        improvement=improvement, retest=retest, evaluation=evaluation,
        repair=repair,
    )
