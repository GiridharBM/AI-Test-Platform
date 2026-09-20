"""Strict sequential gated pipeline orchestrator.

Composes the existing M1-M11 milestone services into a deterministic
state machine. Every stage only runs after its persisted semantic
success predicate passes; HTTP status is never used as the source of
truth. Stage-success predicates:

- upload       : project persisted via ingestion (meta.json exists)
- profile      : ProjectProfile produced
- discover     : CodeMap produced
- plan         : TestPlan produced
- generate     : TestGenerationResult produced + files written
- execute      : TestExecutionResult.overall_status in {passed, failed}
                 (error / timeout / unavailable are NOT usable and STOP)
- diagnose     : DiagnosisResult produced; routing reads its overall_status
- improve      : ImprovementResult with status improved|partial→loop on;
                 no_change|blocked→loop exhausted (gate)
- retest       : ReTestResult with status fixed|passed|still_failing|
                 regression|no_op (blocked/unavailable/failed→STOP)
- repair       : RepairResult.status == validated_pending_approval only
- approve      : approve_repair applies the exact validated candidate then
                 runs final validation (passed→complete)
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.execution.runner import execute_tests
from app.models.codemap import CodeMap
from app.models.diagnosis import DIAGNOSIS_FAILURES_DIAGNOSED, DIAGNOSIS_NO_FAILURES
from app.models.execution import STATUS_FAILED, STATUS_PASSED, STATUS_UNAVAILABLE
from app.models.improvement import (
    IMPROVE_BLOCKED,
    IMPROVE_IMPROVED,
    IMPROVE_NO_CHANGE,
    IMPROVE_PARTIAL,
)
from app.models.pipeline import (
    GATE_APPROVAL,
    GATE_APPROVAL_ACTIONS,
    GATE_REPAIR,
    GATE_REPAIR_ACTIONS,
    GATE_RETEST,
    GATE_RETEST_ACTIONS,
    PIPELINE_BLOCKED,
    PIPELINE_COMPLETED,
    PIPELINE_FAILED,
    PIPELINE_REJECTED,
    PIPELINE_RUNNING,
    PIPELINE_UNAVAILABLE,
    PIPELINE_WAITING_APPROVAL,
    PIPELINE_WAITING_USER,
    PipelineState,
    StageRecord,
    STAGE_APPROVED,
    STAGE_BLOCKED,
    STAGE_EXHAUSTED,
    STAGE_FAILED,
    STAGE_REJECTED,
    STAGE_SKIPPED,
    STAGE_SUCCESS,
    STAGE_UNAVAILABLE,
)
from app.models.project import ProjectProfile
from app.models.repair import (
    FINAL_VALIDATION_FAILED,
    FINAL_VALIDATION_PASSED,
    FINAL_VALIDATION_UNAVAILABLE,
    REPAIR_APPLIED,
    REPAIR_APPROVED,
    REPAIR_BLOCKED,
    REPAIR_FAILED,
    REPAIR_REJECTED,
    REPAIR_UNAVAILABLE,
    REPAIR_VALIDATED_PENDING_APPROVAL,
)
from app.models.retest import (
    RETEST_BLOCKED,
    RETEST_FIXED,
    RETEST_NO_OP,
    RETEST_PASSED,
    RETEST_REGRESSION,
    RETEST_STILL_FAILING,
    RETEST_UNAVAILABLE,
)
from app.models.test_plan import TestPlan
from app.services import project_discovery as discovery
from app.services import project_ingestion as ingestion
from app.services import project_profiler as profiler
from app.services.call_graph import build_call_graph
from app.services.test_generator import generate_test_scaffolds, write_generated_files
from app.services.test_planner import generate_test_plan


class PipelineGateError(Exception):
    """Raised when a user decision action is not permitted by the gate."""


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _persist(ws: Path, state: PipelineState) -> None:
    state.updated_at = _now()
    ingestion.save_pipeline(ws, state.model_dump_json())


def _load(ws: Path, project_id: str) -> PipelineState | None:
    raw = ingestion.read_pipeline(ws, project_id)
    if raw is None:
        return None
    return PipelineState.model_validate_json(raw)


def _require(ws: Path, project_id: str) -> PipelineState:
    state = _load(ws, project_id)
    if state is None:
        ingestion.read_meta(ws, project_id)  # raises 404 for unknown project
        raise PipelineGateError("No pipeline has been started for this project. Start it first.")
    return state


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _artifact(ws: Path, project_id: str, name: str) -> dict | None:
    return _read_json(ingestion.project_dir(ws, project_id) / ".meta" / f"{name}.json")


def _created(obj) -> str:
    created = getattr(obj, "created_at", None)
    if created is None:
        return ""
    return created.isoformat() if hasattr(created, "isoformat") else str(created)


# ---------------------------------------------------------------------------
# Concurrency guard (one pipeline mutation at a time per project)
# ---------------------------------------------------------------------------

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _project_lock(project_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(project_id, threading.Lock())


# ---------------------------------------------------------------------------
# Stage execution (each returns (status, result_id, reason, warnings))
# ---------------------------------------------------------------------------

def _exec_profile(ws: Path, project_id: str):
    result = profiler.profile_project(project_id, ws)
    ingestion.save_profile(ws, result.model_dump_json())
    return (STAGE_SUCCESS, _created(result), "", list(result.warnings))


def _exec_discover(ws: Path, project_id: str):
    result = discovery.discover_project(project_id, ws)
    ingestion.save_codemap(ws, result.model_dump_json())
    return (STAGE_SUCCESS, _created(result), "", list(result.warnings))


def _source_root(ws: Path, project_id: str) -> Path:
    return ingestion.source_root(ws, project_id)


def _read_python_files(root: Path) -> list[tuple[str, str]]:
    """Read all Python files under root: (relative_posix_path, content)."""
    files: list[tuple[str, str]] = []
    if not root.is_dir():
        return files
    for path in sorted(root.rglob("*.py")):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        parts = rel.split("/")
        if any(p in config.IGNORED_DIRS for p in parts):
            continue
        try:
            files.append((rel, path.read_text(encoding="utf-8-sig", errors="replace")))
        except OSError:
            pass
    return files


def _resolve_contained_source(root: Path, rel: str) -> Path | None:
    """Resolve `rel` inside `root` only when it is a real, contained regular
    file (symlinks resolving outside are refused). None on traversal/escape."""
    if not rel or not rel.strip() or "\x00" in rel:
        return None
    cleaned = rel.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts) or any(len(p) > 255 for p in parts):
        return None
    if len(cleaned) > 1 and cleaned[1] == ":":
        return None
    try:
        root_real = os.path.realpath(str(root))
        target = os.path.realpath(str(root / Path(*parts)))
    except (OSError, ValueError):
        return None
    if not Path(target).is_relative_to(Path(root_real)):
        return None
    candidate = Path(target)
    return candidate if candidate.is_file() else None


def _user_merge_dest(gen_dir: Path, rel: str, content: str, planned: set[str]) -> str:
    """Pick a collision-safe `user_<basename>` name for a copied test file.

    Never overwrites generated files (they never start with `user_`). A name
    already on disk is kept when its content matches the source (idempotent
    re-merge); differing content gets a numeric suffix so nothing is clobbered.
    """
    base = rel.replace("\\", "/").rsplit("/", 1)[-1]
    if not base.endswith(".py"):
        base += ".py"
    primary = f"user_{base}"
    if primary not in planned:
        dest = gen_dir / primary
        if dest.exists():
            if _read_as_text(dest) == content:
                return primary
            i = 2
            while (gen_dir / f"user_{i}_{base}").exists() or f"user_{i}_{base}" in planned:
                i += 1
            return f"user_{i}_{base}"
        return primary
    i = 2
    while f"user_{i}_{base}" in planned or (gen_dir / f"user_{i}_{base}").exists():
        i += 1
    return f"user_{i}_{base}"


def _read_as_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""


def _ensure_pytest_collection(gen_dir: Path) -> None:
    """Make the sandbox pytest collect merged `user_*` files.

    pytest's default python_files only matches `test_*.py` / `*_test.py`, so a
    merged `user_test_calc.py` would silently never run. A pytest.ini scoped to
    generated_tests/ (the /tests mount, resolution CWD) extends collection to
    `user_*.py` without touching the shared sandbox command contract.
    """
    cfg = gen_dir / "pytest.ini"
    cfg.write_text(
        "[pytest]\npython_files = test_*.py *_test.py user_*.py\n",
        encoding="utf-8",
    )


def _merge_user_tests(
    gen_dir: Path, source_root: Path, test_rel_paths: list[str],
) -> list[str]:
    """Copy discovered user test files into generated_tests/ under `user_*` names.

    Preserves original content exactly (utf-8-sig decode -> utf-8 write),
    refuses traversal/symlink escapes, and treats an already-copied identical
    file as idempotent. Returns the copied (generated_tests-relative) names.
    """
    copied: list[str] = []
    planned: set[str] = set()
    for rel in sorted(set(test_rel_paths)):
        src = _resolve_contained_source(source_root, rel)
        if src is None:
            continue
        content = _read_as_text(src)
        if not content:
            continue
        name = _user_merge_dest(gen_dir, rel, content, planned)
        planned.add(name)
        dest = gen_dir / name
        if not dest.exists():
            dest.write_text(content, encoding="utf-8")
        copied.append(name)
    return sorted(set(copied))


def _exec_plan(ws: Path, project_id: str):
    raw_cm = ingestion.read_codemap(ws, project_id)
    if raw_cm is None:
        raise FileNotFoundError("No CodeMap result. Discover must succeed first.")
    codemap = CodeMap.model_validate_json(raw_cm)
    raw_pr = ingestion.read_profile(ws, project_id)
    if raw_pr is None:
        raise FileNotFoundError("No profile result. Profile must succeed first.")
    profile = ProjectProfile.model_validate_json(raw_pr)
    call_graph = build_call_graph(_read_python_files(_source_root(ws, project_id)))
    plan = generate_test_plan(codemap, profile, call_graph)
    ingestion.save_test_plan(ws, plan.model_dump_json())
    return (STAGE_SUCCESS, _created(plan), "", list(plan.warnings))


def _exec_generate(ws: Path, project_id: str):
    raw_plan = ingestion.read_test_plan(ws, project_id)
    if raw_plan is None:
        raise FileNotFoundError("No test plan result. Plan must succeed first.")
    plan = TestPlan.model_validate_json(raw_plan)
    raw_cm = ingestion.read_codemap(ws, project_id)
    if raw_cm is None:
        raise FileNotFoundError("No CodeMap result. Discover must succeed first.")
    codemap = CodeMap.model_validate_json(raw_cm)
    raw_pr = ingestion.read_profile(ws, project_id)
    if raw_pr is None:
        raise FileNotFoundError("No profile result. Profile must succeed first.")
    profile = ProjectProfile.model_validate_json(raw_pr)
    result = generate_test_scaffolds(plan, codemap, profile)
    write_generated_files(result, ws)
    # Merge the user's OWN discovered test files into the executed suite so
    # their behavioral assertions actually run (and can reach M9/M11). The
    # merge happens before persistence so the artifact records what executed.
    result.merged_user_files = _merge_user_tests(
        ingestion.project_dir(ws, project_id) / "generated_tests",
        _source_root(ws, project_id),
        [tf.file_path for tf in codemap.test_functions],
    )
    _ensure_pytest_collection(ingestion.project_dir(ws, project_id) / "generated_tests")
    ingestion.save_test_generation(ws, result.model_dump_json())
    warnings = list(result.warnings)
    if not result.files:
        # Empty generation is NOT semantic success for the autonomous pipeline:
        # zero test files would make the subsequent execution vacuous. Fail
        # closed here (record reason carries the detail) instead of silently
        # continuing to `execute -> passed -> no_failures`.
        return (
            STAGE_FAILED,
            _created(result),
            "Test generation produced no executable test files (empty test plan); "
            "pipeline stops rather than silently succeeding on zero tests.",
            warnings,
        )
    return (STAGE_SUCCESS, _created(result), "", warnings)


def _exec_execute(ws: Path, project_id: str):
    gen_dir = ingestion.project_dir(ws, project_id) / "generated_tests"
    result = execute_tests(gen_dir, project_id, source_root=_source_root(ws, project_id))
    if result.overall_status in (STATUS_PASSED, STATUS_FAILED):
        status = STAGE_SUCCESS
    elif result.overall_status == STATUS_UNAVAILABLE:
        status = STAGE_UNAVAILABLE
    else:
        status = STAGE_FAILED  # error / timeout
    if (
        result.overall_status in (STATUS_PASSED, STATUS_FAILED)
        and not result.file_results
        and result.summary.total_test_functions == 0
    ):
        # Vacuous success guard: an execution that ran ZERO tests (e.g. no
        # generated tests collected -> pytest exit 5 mapped to `passed`) must
        # not be treated as a meaningful execution for pipeline progression.
        status = STAGE_FAILED
        _reason = "Execution ran 0 tests (no generated tests collected); not a usable execution."
    else:
        _reason = f"execution overall_status={result.overall_status}"
    ingestion.save_execution(ws, result.model_dump_json())
    return (
        status,
        _created(result),
        _reason,
        list(result.warnings),
    )


def _exec_diagnose(ws: Path, project_id: str):
    from app.agents.diagnose import diagnose_project as run_diagnosis

    result = run_diagnosis(project_id, ws)
    ingestion.save_diagnosis(ws, result.model_dump_json())
    return (
        STAGE_SUCCESS,
        _created(result),
        f"diagnosis overall_status={result.overall_status}",
        list(result.warnings),
    )


def _exec_improve(ws: Path, project_id: str):
    from app.services.improvement import improve_project as run_improve

    result = run_improve(project_id, ws)
    ingestion.save_improvement(ws, result.model_dump_json())
    if result.status in (IMPROVE_NO_CHANGE, IMPROVE_BLOCKED):
        # M8's `blocked` means no evidence-supported change could be applied:
        # every attempted finding was refused (insufficient evidence, non-
        # actionable scaffold, unsafe-to-touch path) and ZERO files changed.
        # That is bounded improvement-loop exhaustion — nothing was modified,
        # so there is nothing unsafe to stop over — and the pipeline routes it
        # to the human re-test gate, exactly like `no_change` (M11's retest
        # already treats both identically as a no-op).
        status = STAGE_EXHAUSTED
    elif result.status in (IMPROVE_IMPROVED, IMPROVE_PARTIAL):
        status = STAGE_SUCCESS
    else:
        status = STAGE_FAILED  # invalid/unexpected improvement status — fail closed
    return (status, _created(result), f"improvement status={result.status}", list(result.warnings))


def _exec_retest(ws: Path, project_id: str):
    from app.services.retest import retest_project as run_retest

    result = run_retest(project_id, ws)  # self-persists via save_retest
    if result.status in (
        RETEST_FIXED, RETEST_PASSED, RETEST_STILL_FAILING, RETEST_REGRESSION, RETEST_NO_OP,
    ):
        status = STAGE_SUCCESS
    elif result.status == RETEST_BLOCKED:
        status = STAGE_BLOCKED
    elif result.status == RETEST_UNAVAILABLE:
        status = STAGE_UNAVAILABLE
    else:
        status = STAGE_FAILED
    return (status, _created(result), f"retest status={result.status}", list(result.reasons))


def _exec_repair(ws: Path, project_id: str):
    from app.services.repair import repair_project as run_repair

    result = run_repair(project_id, ws)  # self-persists via save_repair
    if result.status == REPAIR_VALIDATED_PENDING_APPROVAL:
        status = STAGE_SUCCESS
    elif result.status == REPAIR_BLOCKED or result.status == REPAIR_REJECTED:
        status = STAGE_BLOCKED
    elif result.status == REPAIR_UNAVAILABLE:
        status = STAGE_UNAVAILABLE
    elif result.status == REPAIR_FAILED:
        status = STAGE_FAILED
    else:
        status = STAGE_FAILED
    return (status, _created(result), f"repair status={result.status}", list(result.reasons))


def _exec_approve(ws: Path, project_id: str):
    from app.services.repair import approve_repair as run_approve

    result = run_approve(project_id, ws)  # self-persists via save_repair
    if result.status in (REPAIR_APPLIED, REPAIR_APPROVED):
        status = STAGE_APPROVED
    elif result.status == REPAIR_REJECTED:
        status = STAGE_REJECTED
    elif result.status == REPAIR_BLOCKED:
        status = STAGE_BLOCKED
    elif result.status == REPAIR_UNAVAILABLE:
        status = STAGE_UNAVAILABLE
    else:
        status = STAGE_FAILED
    fv = result.final_validation.status if result.final_validation else ""
    return (status, _created(result), f"approval status={result.status}, final_validation={fv}", list(result.reasons))


_EXEC: dict[str, object] = {
    "profile": _exec_profile,
    "discover": _exec_discover,
    "plan": _exec_plan,
    "generate": _exec_generate,
    "execute": _exec_execute,
    "diagnose": _exec_diagnose,
    "improve": _exec_improve,
    "retest": _exec_retest,
    "repair": _exec_repair,
    "approve": _exec_approve,
}

_IN_PROGRESS_NAME = {
    "profile": "profiling", "discover": "discovering", "plan": "planning",
    "generate": "generating", "execute": "executing", "diagnose": "diagnosing",
    "improve": "improving", "retest": "retesting", "repair": "repairing",
    "approve": "applying_repair",
}

_COMPLETED_NAME = {
    "profile": "profiled", "discover": "discovered", "plan": "planned",
    "generate": "generated", "execute": "executed", "diagnose": "diagnosed",
    "improve": "improved", "retest": "retested", "repair": "repaired",
    "approve": "applied",
}


def _run_stage(state: PipelineState, stage: str, ws: Path) -> None:
    """Execute one stage, append its history record, and persist."""
    start = _now()
    state.current_stage = _IN_PROGRESS_NAME.get(stage, stage)
    state.overall_status = PIPELINE_RUNNING
    state.user_decision_required = False
    state.available_actions = []
    _persist(ws, state)
    try:
        fn = _EXEC[stage]
        status, result_id, reason, warnings = fn(ws, state.project_id)
    except Exception as exc:  # deterministic, explicit failure — pipeline stops
        status, result_id, reason, warnings = STAGE_FAILED, "", str(exc), []
    record = StageRecord(
        stage=stage, status=status, start_time=start, end_time=_now(),
        result_id=result_id, reason=reason, warnings=warnings,
    )
    state.stage_history.append(record)
    state.current_stage = _COMPLETED_NAME.get(stage, stage)
    if status in (STAGE_SUCCESS, STAGE_EXHAUSTED, STAGE_SKIPPED, STAGE_APPROVED):
        state.completed_stages.append(stage)
    if stage == "improve":
        state.current_improvement_round = sum(
            1 for h in state.stage_history if h.stage == "improve"
        )
    _persist(ws, state)


# ---------------------------------------------------------------------------
# Gate / terminal transitions
# ---------------------------------------------------------------------------

def _enter_gate(state: PipelineState, gate: str, actions, reason: str) -> None:
    state.current_stage = gate
    state.overall_status = (
        PIPELINE_WAITING_APPROVAL if gate == GATE_APPROVAL else PIPELINE_WAITING_USER
    )
    state.user_decision_required = True
    state.available_actions = list(actions)
    state.reason = reason


def _complete(state: PipelineState, reason: str) -> None:
    state.current_stage = "completed"
    state.overall_status = PIPELINE_COMPLETED
    state.user_decision_required = False
    state.available_actions = []
    state.reason = reason


def _stop(state: PipelineState, overall: str, reason: str) -> None:
    state.current_stage = overall
    state.overall_status = overall
    state.user_decision_required = False
    state.available_actions = []
    state.reason = reason


# ---------------------------------------------------------------------------
# Next-action routing (strict gating)
# ---------------------------------------------------------------------------

def _next_action(state: PipelineState, ws: Path):
    tail = state.stage_history[-1] if state.stage_history else None
    if tail is None:
        return ("stage", "profile")

    stage, status = tail.stage, tail.status

    if stage == "upload":
        if status == STAGE_SUCCESS:
            return ("stage", "profile")
        return ("stop", PIPELINE_FAILED, "Upload did not succeed; pipeline not started.")

    if stage in ("profile", "discover", "plan", "generate"):
        if status == STAGE_SUCCESS:
            nxt = {
                "profile": "discover",
                "discover": "plan",
                "plan": "generate",
                "generate": "execute",
            }[stage]
            return ("stage", nxt)
        return _stop_from_status(state, stage, status)

    if stage == "execute":
        if status == STAGE_SUCCESS:
            return ("stage", "diagnose")
        return _stop_from_status(state, stage, status)

    if stage == "diagnose":
        if status != STAGE_SUCCESS:
            return _stop_from_status(state, stage, status)
        diag = _artifact(ws, state.project_id, "diagnosis")
        overall = diag.get("overall_status") if diag else ""
        if overall == DIAGNOSIS_NO_FAILURES:
            # A re-test decision gate is meaningful only after an improvement
            # actually produced changes and was re-executed. On the very first
            # diagnosis there is no improvement result to re-test, so reaching
            # the gate here would be vacuous (zero tests -> passed ->
            # no_failures removed by the generate/execute guards as well).
            if any(h.stage == "improve" for h in state.stage_history):
                return (
                    "gate", GATE_RETEST,
                    "Improved tests pass; awaiting re-test decision.",
                )
            return (
                "complete",
                "No failing tests remain; nothing to improve or re-test; pipeline complete.",
            )
        if overall == DIAGNOSIS_FAILURES_DIAGNOSED:
            rounds = state.current_improvement_round
            if rounds < state.maximum_improvement_rounds:
                return ("stage", "improve")
            return (
                "gate", GATE_RETEST,
                f"Improvement loop exhausted after {rounds} round(s) "
                f"(max {state.maximum_improvement_rounds}); awaiting re-test decision.",
            )
        return ("stop", PIPELINE_BLOCKED, f"Diagnosis overall_status={overall!r} is not usable.")

    if stage == "improve":
        if status == STAGE_EXHAUSTED:
            return (
                "gate", GATE_RETEST,
                f"Improvement made no change after {state.current_improvement_round} round(s); "
                "improvement loop exhausted.",
            )
        if status == STAGE_SUCCESS:
            return ("stage", "execute")
        if status == STAGE_BLOCKED:
            return ("stop", PIPELINE_BLOCKED, "Improvement blocked: no evidence-supported changes available.")
        return _stop_from_status(state, stage, status)

    if stage == "retest":
        if status == STAGE_SUCCESS:
            rt = _artifact(ws, state.project_id, "retest")
            rst = rt.get("status") if rt else ""
            if rst in (RETEST_FIXED, RETEST_PASSED):
                return ("complete", f"Re-test {rst}: improved tests now pass; pipeline complete.")
            if rst in (RETEST_STILL_FAILING, RETEST_REGRESSION):
                return ("gate", GATE_REPAIR, f"Re-test {rst}; awaiting source-repair decision.")
            if rst == RETEST_NO_OP:
                return ("gate", GATE_REPAIR, "Re-test was a no-op; awaiting source-repair decision.")
            return ("stop", PIPELINE_BLOCKED, f"Re-test produced unusable status: {rst!r}.")
        if status == STAGE_SKIPPED:
            return ("gate", GATE_REPAIR, "Re-test skipped by user; awaiting source-repair decision.")
        return _stop_from_status(state, stage, status)

    if stage == "repair":
        if status == STAGE_SUCCESS:
            return ("gate", GATE_APPROVAL, "Validated repair candidate awaiting approval.")
        if status == STAGE_SKIPPED:
            return ("complete", "Source repair skipped by user; pipeline complete.")
        return _stop_from_status(state, stage, status)

    if stage == "approve":
        if status == STAGE_APPROVED:
            rp = _artifact(ws, state.project_id, "repair")
            fv = (rp or {}).get("final_validation", {})
            fv_status = fv.get("status") if isinstance(fv, dict) else ""
            if fv_status == FINAL_VALIDATION_PASSED:
                return ("complete", "Repair applied and final validation passed; pipeline complete.")
            if fv_status == FINAL_VALIDATION_FAILED:
                return ("stop", PIPELINE_FAILED, "Repair applied but final validation failed.")
            if fv_status == FINAL_VALIDATION_UNAVAILABLE:
                return ("stop", PIPELINE_UNAVAILABLE, "Repair applied but final validation is unavailable.")
            return ("complete", "Repair applied; final validation outcome not recorded.")
        if status == STAGE_REJECTED:
            return ("stop", PIPELINE_REJECTED, "Repair approval rejected by user; source unchanged.")
        return _stop_from_status(state, stage, status)

    return ("stop", PIPELINE_FAILED, f"Unreachable stage in history: {stage!r}/{status!r}.")


def _stop_from_status(state: PipelineState, stage: str, status: str):
    if status == STAGE_UNAVAILABLE:
        return ("stop", PIPELINE_UNAVAILABLE, f"{stage} is unavailable.")
    if status == STAGE_BLOCKED:
        return ("stop", PIPELINE_BLOCKED, f"{stage} is blocked.")
    return ("stop", PIPELINE_FAILED, f"{stage} failed.")


def _advance(state: PipelineState, ws: Path) -> None:
    """Run automatic stages until a gate or terminal state is reached."""
    while True:
        nxt = _next_action(state, ws)
        if nxt[0] == "stage":
            _run_stage(state, nxt[1], ws)
            continue
        if nxt[0] == "gate":
            _enter_gate(state, nxt[1], {
                GATE_RETEST: GATE_RETEST_ACTIONS,
                GATE_REPAIR: GATE_REPAIR_ACTIONS,
                GATE_APPROVAL: GATE_APPROVAL_ACTIONS,
            }[nxt[1]], nxt[2])
            return
        if nxt[0] == "complete":
            _complete(state, nxt[1])
            return
        _stop(state, nxt[1], nxt[2])  # "stop"
        return


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def start_pipeline(project_id: str, workspace: Path | None = None) -> PipelineState:
    """Create (if absent) and advance the pipeline. Idempotent."""
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    ingestion.read_meta(ws, project_id)  # raises 404 for unknown project
    with _project_lock(project_id):
        existing = _load(ws, project_id)
        if existing is not None:
            return existing
        state = PipelineState(
            project_id=project_id,
            pipeline_id=str(uuid.uuid4()),
            current_stage="uploaded",
            maximum_improvement_rounds=min(
                config.AUTO_IMPROVEMENT_MAX_ROUNDS,
                config.AUTO_IMPROVEMENT_MAX_ROUNDS_HARD_MAX,
            ),
        )
        state.stage_history.append(StageRecord(
            stage="upload", status=STAGE_SUCCESS, start_time=_now(), end_time=_now(),
            reason="Upload succeeded; pipeline started.",
        ))
        state.completed_stages.append("upload")
        _persist(ws, state)
        _advance(state, ws)
        _persist(ws, state)
        return state


def get_pipeline(project_id: str, workspace: Path | None = None) -> PipelineState:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    return _require(ws, project_id)


def resume_pipeline(project_id: str, workspace: Path | None = None) -> PipelineState:
    """Retry the last failed/unavailable stage, then continue the chain.

    Not resumable at a human gate or from a terminal state (returns state
    unchanged).
    """
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    with _project_lock(project_id):
        state = _require(ws, project_id)
        if state.overall_status in (
            PIPELINE_WAITING_USER, PIPELINE_WAITING_APPROVAL,
            PIPELINE_COMPLETED, PIPELINE_REJECTED,
        ):
            return state
        tail = state.stage_history[-1] if state.stage_history else None
        if tail is not None and tail.status in (STAGE_FAILED, STAGE_UNAVAILABLE):
            _run_stage(state, tail.stage, ws)
        _advance(state, ws)
        _persist(ws, state)
        return state


def _require_gate(state: PipelineState, gate: str) -> None:
    if state.current_stage != gate or state.overall_status not in (
        PIPELINE_WAITING_USER, PIPELINE_WAITING_APPROVAL,
    ):
        raise PipelineGateError(
            f"Action requires current_stage={gate}, but the pipeline is at "
            f"{state.current_stage!r} ({state.overall_status!r})."
        )


def decide_retest(project_id: str, workspace: Path | None = None) -> PipelineState:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    with _project_lock(project_id):
        state = _require(ws, project_id)
        _require_gate(state, GATE_RETEST)
        _run_stage(state, "retest", ws)
        _advance(state, ws)
        _persist(ws, state)
        return state


def decide_skip_retest(project_id: str, workspace: Path | None = None) -> PipelineState:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    with _project_lock(project_id):
        state = _require(ws, project_id)
        _require_gate(state, GATE_RETEST)
        state.stage_history.append(StageRecord(
            stage="retest", status=STAGE_SKIPPED,
            start_time=_now(), end_time=_now(), reason="Re-test skipped by user.",
        ))
        state.completed_stages.append("retest")
        _advance(state, ws)
        _persist(ws, state)
        return state


def decide_repair(project_id: str, workspace: Path | None = None) -> PipelineState:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    with _project_lock(project_id):
        state = _require(ws, project_id)
        _require_gate(state, GATE_REPAIR)
        _run_stage(state, "repair", ws)
        _advance(state, ws)
        _persist(ws, state)
        return state


def decide_skip_repair(project_id: str, workspace: Path | None = None) -> PipelineState:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    with _project_lock(project_id):
        state = _require(ws, project_id)
        _require_gate(state, GATE_REPAIR)
        state.stage_history.append(StageRecord(
            stage="repair", status=STAGE_SKIPPED,
            start_time=_now(), end_time=_now(), reason="Source repair skipped by user.",
        ))
        state.completed_stages.append("repair")
        _advance(state, ws)
        _persist(ws, state)
        return state


def decide_approve(project_id: str, workspace: Path | None = None) -> PipelineState:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    with _project_lock(project_id):
        state = _require(ws, project_id)
        _require_gate(state, GATE_APPROVAL)
        _run_stage(state, "approve", ws)
        _advance(state, ws)
        _persist(ws, state)
        return state


def decide_reject(project_id: str, workspace: Path | None = None) -> PipelineState:
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    with _project_lock(project_id):
        state = _require(ws, project_id)
        _require_gate(state, GATE_APPROVAL)
        state.stage_history.append(StageRecord(
            stage="approve", status=STAGE_REJECTED,
            start_time=_now(), end_time=_now(),
            reason="Repair approval rejected by user; source unchanged.",
        ))
        state.completed_stages.append("approve")
        _advance(state, ws)
        _persist(ws, state)
        return state