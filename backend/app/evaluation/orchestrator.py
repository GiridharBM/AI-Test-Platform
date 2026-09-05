"""Evaluation orchestrator (Milestone 10).

Runs the three independent evaluation components — coverage, mutation, and
benchmark — using the established pipeline artifacts, and packs them into a
single EvaluationResult. Follows the approved M9 -> M10 behavior, keeps each
component's availability independent so one unavailable component never
corrupts the others, and never fabricates results.
"""

from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.evaluation import benchmark, coverage, mutation
from app.models.evaluation import (
    EVAL_BLOCKED,
    EVAL_COMPLETED,
    EVAL_ERROR,
    EVAL_NOT_RUN,
    EVAL_UNAVAILABLE,
    CoverageResult,
    EvaluationResult,
    MutationResult,
    BenchmarkResult,
)
from app.models.retest import (
    RETEST_BLOCKED,
    RETEST_NO_OP,
    RETEST_UNAVAILABLE,
    ReTestResult,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _worst_status(*statuses: str) -> str:
    """Worst component status drives the overall evaluation status so a
    missing optional component never silently becomes success, while also
    not failing the whole evaluation merely because one optional component is
    unavailable."""
    priority = [EVAL_ERROR, EVAL_BLOCKED, EVAL_UNAVAILABLE, EVAL_NOT_RUN, EVAL_COMPLETED]
    for wanted in priority:
        if wanted in statuses:
            return wanted
    return EVAL_COMPLETED


def _summary_text(
    coverage_c: CoverageResult,
    mutation_c: MutationResult,
    benchmark_c: BenchmarkResult,
) -> str:
    parts = [f"coverage:{coverage_c.status}", f"mutation:{mutation_c.status}", f"benchmark:{benchmark_c.status}"]
    if coverage_c.status == EVAL_COMPLETED:
        parts.append(f"line {coverage_c.line_percentage}%")
    if mutation_c.status == EVAL_COMPLETED and mutation_c.mutation_score is not None:
        parts.append(f"mutation score {mutation_c.mutation_score}%")
    if benchmark_c.status == EVAL_COMPLETED and benchmark_c.median_seconds is not None:
        parts.append(f"median {benchmark_c.median_seconds}s")
    return "; ".join(parts)


def evaluate_from_artifacts(
    project_id: str,
    source_root: Path,
    test_dir: Path,
    retest: ReTestResult | None = None,
) -> EvaluationResult:
    """Run all three components and produce a deterministic EvaluationResult.

    The M9 ReTestResult is the primary downstream evaluation context; its
    availability is preserved per the approved M9 -> M10 behavior.
    """
    warnings: list[str] = []
    reasons: list[str] = []

    if retest is not None:
        if retest.status == RETEST_BLOCKED:
            warnings.append("M9 re-test was blocked; evaluation proceeds on available artifacts.")
        elif retest.status == RETEST_NO_OP:
            warnings.append("M9 re-test was a no-op; evaluation proceeds on available artifacts.")
        elif retest.status == RETEST_UNAVAILABLE:
            warnings.append("M9 re-test was unavailable; execution-dependent measurement may be unavailable.")

    coverage_r = coverage.run_coverage(source_root, test_dir, project_id)
    mutation_r = mutation.run_mutation(source_root, test_dir, project_id)
    benchmark_r = benchmark.run_benchmark(source_root, test_dir, project_id)

    warnings += coverage_r.warnings + mutation_r.warnings + benchmark_r.warnings
    reasons += coverage_r.reasons + mutation_r.reasons + benchmark_r.reasons

    retest_id = ""
    if retest is not None:
        # ReTestResult has no id field of its own; its deterministic diagnosis
        # id anchors the chain. Do not fabricate a random id.
        retest_id = retest.diagnosis_id or ""

    overall = _worst_status(coverage_r.status, mutation_r.status, benchmark_r.status)
    status_reason = {
        EVAL_COMPLETED: "All evaluation components completed.",
        EVAL_NOT_RUN: "Some evaluation components did not run.",
        EVAL_UNAVAILABLE: "Some evaluation components were unavailable.",
        EVAL_BLOCKED: "Some evaluation components were blocked.",
        EVAL_ERROR: "Some evaluation components errored.",
    }[overall]
    reasons.append(status_reason)

    return EvaluationResult(
        project_id=project_id,
        status=overall,
        retest_id=retest_id,
        coverage=coverage_r,
        mutation=mutation_r,
        benchmark=benchmark_r,
        summary=_summary_text(coverage_r, mutation_r, benchmark_r),
        warnings=warnings,
        reasons=reasons,
        created_at=_now(),
    )


def evaluate_project(project_id: str, workspace: Path | None = None) -> EvaluationResult:
    """Orchestrate evaluation from persisted pipeline artifacts."""
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    ingestion.read_meta(ws, project_id)

    source_root = ingestion.source_dir(ws, project_id)
    test_dir = Path(ws) / project_id / "generated_tests"

    retest = None
    raw_retest = ingestion.read_retest(ws, project_id)
    if raw_retest is not None:
        retest = ReTestResult.model_validate_json(raw_retest)

    result = evaluate_from_artifacts(project_id, source_root, test_dir, retest)
    ingestion.save_evaluation(ws, result.model_dump_json())
    return result
