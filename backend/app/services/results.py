"""Read-only results digest derivation (Milestone 13).

Builds a bounded ResultsDigest from the persisted .meta artifacts. Never
mutates anything, never reads source/test file contents, and never exposes
full tracebacks, host/sandbox paths, environment variables, or secrets.

Path hygiene mirrors the existing diagnosis semantics: only normalized
project-relative locations already present in .meta artifacts are surfaced.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core import config
from app.services import project_ingestion as ingestion
from app.models.results import (
    DIGEST_VERDICT_FAILED,
    DIGEST_VERDICT_NO_EXECUTION,
    DIGEST_VERDICT_PASSED,
    DIGEST_VERDICT_REJECTED,
    DIGEST_VERDICT_REPAIR_PENDING,
    DIGEST_VERDICT_UNAVAILABLE,
    DigestEvaluationState,
    DigestFailingTest,
    DigestRepairState,
    DigestTestCounts,
    ResultsDigest,
)
from app.models.execution import (
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_TIMEOUT,
    STATUS_UNAVAILABLE,
)
from app.models.repair import (
    APPLICATION_APPLIED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    FINAL_VALIDATION_NOT_RUN,
    FINAL_VALIDATION_PASSED,
    FINAL_VALIDATION_UNAVAILABLE,
)
from app.models.retest import (
    RETEST_FIXED,
    RETEST_PASSED,
    RETEST_REGRESSION,
    RETEST_STILL_FAILING,
)

_EXECUTION_FAILURE_STATUSES = {STATUS_FAILED, STATUS_ERROR, STATUS_TIMEOUT}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_results_digest(
    project_id: str,
    workspace: Optional[Path] = None,
) -> ResultsDigest:
    """Derive the read-only results digest for a project.

    Raises FileNotFoundError (→ 404 at the API layer) for unknown projects.
    """
    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    ingestion.read_meta(ws, project_id)  # 404 for unknown/traversal ids

    execution, exec_corrupt = _read_execution(ws, project_id)
    diagnosis, diag_corrupt = _read_diagnosis(ws, project_id)
    improvement, improve_corrupt = _read_improvement(ws, project_id)
    retest, retest_corrupt = _read_retest(ws, project_id)
    repair, repair_corrupt = _read_repair(ws, project_id)
    evaluation, eval_corrupt = _read_evaluation(ws, project_id)
    pipeline, pipeline_corrupt = _read_pipeline(ws, project_id)

    corrupt: list[str] = []
    for name, flag in (
        ("execution", exec_corrupt), ("diagnosis", diag_corrupt),
        ("improvement", improve_corrupt), ("retest", retest_corrupt),
        ("repair", repair_corrupt), ("evaluation", eval_corrupt),
        ("pipeline", pipeline_corrupt),
    ):
        if flag:
            corrupt.append(name)

    digest = ResultsDigest(
        project_id=project_id,
        created_at=_now(),
        pipeline_status=pipeline.overall_status if pipeline else None,
        pipeline_current_stage=pipeline.current_stage if pipeline else None,
        corrupt_artifacts=corrupt,
    )
    if corrupt:
        digest.warnings.append(
            f"Unreadable artifacts (corrupt), reported as unavailable: {', '.join(corrupt)}."
        )

    _apply_execution(digest, execution)
    _apply_diagnosis(digest, diagnosis, execution)
    _apply_improvement(digest, improvement)
    _apply_retest(digest, retest)
    _apply_repair(digest, repair)
    _apply_evaluation(digest, evaluation)
    _derive_verdict(digest, execution, retest, repair, corrupt)

    # Bounded: cap the failing-tests list deterministically.
    max_findings = 100
    if len(digest.failing_tests) > max_findings:
        digest.failing_tests = digest.failing_tests[:max_findings]
        digest.warnings.append(
            f"Failing-test list truncated to {max_findings} entries."
        )

    return digest


def _read_execution(ws, project_id):
    raw = ingestion.read_execution(ws, project_id)
    if raw is None:
        return None, False
    from app.models.execution import TestExecutionResult
    try:
        return TestExecutionResult.model_validate_json(raw), False
    except Exception:
        return None, True


def _read_diagnosis(ws, project_id):
    raw = ingestion.read_diagnosis(ws, project_id)
    if raw is None:
        return None, False
    from app.models.diagnosis import DiagnosisResult
    try:
        return DiagnosisResult.model_validate_json(raw), False
    except Exception:
        return None, True


def _read_improvement(ws, project_id):
    raw = ingestion.read_improvement(ws, project_id)
    if raw is None:
        return None, False
    from app.models.improvement import ImprovementResult
    try:
        return ImprovementResult.model_validate_json(raw), False
    except Exception:
        return None, True


def _read_retest(ws, project_id):
    raw = ingestion.read_retest(ws, project_id)
    if raw is None:
        return None, False
    from app.models.retest import ReTestResult
    try:
        return ReTestResult.model_validate_json(raw), False
    except Exception:
        return None, True


def _read_repair(ws, project_id):
    raw = ingestion.read_repair(ws, project_id)
    if raw is None:
        return None, False
    from app.models.repair import RepairResult
    try:
        return RepairResult.model_validate_json(raw), False
    except Exception:
        return None, True


def _read_evaluation(ws, project_id):
    raw = ingestion.read_evaluation(ws, project_id)
    if raw is None:
        return None, False
    from app.models.evaluation import EvaluationResult
    try:
        return EvaluationResult.model_validate_json(raw), False
    except Exception:
        return None, True


def _read_pipeline(ws, project_id):
    raw = ingestion.read_pipeline(ws, project_id)
    if raw is None:
        return None, False
    from app.models.pipeline import PipelineState
    try:
        return PipelineState.model_validate_json(raw), False
    except Exception:
        return None, True


def _apply_execution(digest: ResultsDigest, execution) -> None:
    if execution is None:
        return
    digest.execution_status = execution.overall_status
    digest.execution_duration_seconds = execution.duration_seconds
    digest.test_counts = DigestTestCounts(
        total_files=execution.summary.total_files,
        total_test_functions=execution.summary.total_test_functions,
        passed=execution.summary.passed,
        failed=execution.summary.failed,
        errors=execution.summary.errors,
        skipped=execution.summary.skipped,
    )
    if not execution.file_results:
        digest.warnings.extend(execution.warnings)


def _apply_diagnosis(digest: ResultsDigest, diagnosis, execution) -> None:
    if diagnosis is None:
        # Fall back to structured per-test rows when no diagnosis exists.
        if execution is not None:
            for file_result in execution.file_results:
                for test_result in file_result.test_functions:
                    if test_result.status in (STATUS_FAILED, STATUS_ERROR):
                        digest.failing_tests.append(DigestFailingTest(
                            test_file=file_result.file_path,
                            test_function=test_result.test_function,
                            status=test_result.status,
                        ))
        return
    digest.diagnosis_status = diagnosis.overall_status
    for finding in diagnosis.findings:
        location = finding.linked_locations[0] if finding.linked_locations else None
        digest.failing_tests.append(DigestFailingTest(
            test_file=finding.test_file,
            test_function=finding.test_function,
            status=finding.status,
            category=finding.category,
            severity=finding.severity,
            exception_type=finding.exception_type,
            message=finding.message,
            source_file=location.source_file if location else "",
            source_line_start=location.line_start if location else None,
            source_line_end=location.line_end if location else None,
            source_qualified_name=location.qualified_name if location else "",
        ))
    digest.warnings.extend(diagnosis.warnings)


def _apply_improvement(digest: ResultsDigest, improvement) -> None:
    if improvement is None:
        return
    digest.improvement_status = improvement.status
    digest.improvement_changes = len(improvement.changes)
    digest.improvement_files_modified = improvement.files_modified


def _apply_retest(digest: ResultsDigest, retest) -> None:
    if retest is None:
        return
    digest.retest_status = retest.status


def _apply_repair(digest: ResultsDigest, repair) -> None:
    if repair is None:
        return
    fv = repair.final_validation
    selected = repair.selected_candidate
    confirmed = (
        repair.application_state == "applied"
        and fv is not None
        and fv.status == "passed"
    )
    digest.repair = DigestRepairState(
        status=repair.status,
        approval_state=repair.approval_state,
        application_state=repair.application_state,
        final_validation_status=fv.status if fv else "",
        final_validation_reason=fv.reason if fv else "",
        selected_operation=selected.operation if selected else "",
        selected_file_path=selected.file_path if selected else "",
        selected_source_location=selected.source_location if selected else "",
        selected_rationale=selected.rationale if selected else "",
        confirmed_repair=confirmed,
        reasons=list(repair.reasons),
    )
    digest.warnings.extend(repair.warnings)


def _apply_evaluation(digest: ResultsDigest, evaluation) -> None:
    if evaluation is None:
        return
    digest.evaluation = DigestEvaluationState(
        status=evaluation.status,
        coverage_status=evaluation.coverage.status,
        line_coverage_percentage=evaluation.coverage.line_percentage,
        mutation_status=evaluation.mutation.status,
        mutation_score=evaluation.mutation.mutation_score,
        benchmark_status=evaluation.benchmark.status,
        benchmark_median_seconds=evaluation.benchmark.median_seconds,
    )


def _derive_verdict(digest: ResultsDigest, execution, retest, repair, corrupt) -> None:
    """Derive the overall verdict from evidence actually present.

    The verdict never fabricates success: a missing execution is
    `no_execution`, an unavailable runtime is `unavailable`, a repair
    awaiting approval is `repair_pending` — never `passed`. A corrupt
    (unreadable) execution artifact is `unavailable`, never `passed`.
    """
    if "execution" in corrupt:
        digest.overall_verdict = DIGEST_VERDICT_UNAVAILABLE
        digest.reason = (
            "Test execution artifact is unreadable (corrupt); outcome "
            "cannot be determined."
        )
        return

    if execution is None or execution.overall_status is None:
        digest.overall_verdict = DIGEST_VERDICT_NO_EXECUTION
        digest.reason = "No test execution has run yet."
        return

    status = execution.overall_status

    if status == STATUS_UNAVAILABLE:
        digest.overall_verdict = DIGEST_VERDICT_UNAVAILABLE
        digest.reason = "Test execution is unavailable (runtime not available)."
        return

    # A repair decision overlaps the execution state: surface the human gate.
    if repair is not None:
        if repair.approval_state == APPROVAL_PENDING and repair.selected_candidate is not None:
            digest.overall_verdict = DIGEST_VERDICT_REPAIR_PENDING
            digest.reason = "A validated source repair awaits explicit approval."
            return
        if repair.approval_state == APPROVAL_REJECTED:
            digest.overall_verdict = DIGEST_VERDICT_REJECTED
            digest.reason = "The proposed source repair was rejected and not applied."
            return
        if (
            repair.application_state == APPLICATION_APPLIED
            and repair.final_validation is not None
            and repair.final_validation.status == FINAL_VALIDATION_PASSED
        ):
            digest.overall_verdict = DIGEST_VERDICT_PASSED
            digest.reason = (
                "Source repair applied and final validation passed."
            )
            return
        if repair.application_state == APPLICATION_APPLIED:
            fv_status = (
                repair.final_validation.status
                if repair.final_validation is not None
                else FINAL_VALIDATION_NOT_RUN
            )
            if fv_status in (FINAL_VALIDATION_UNAVAILABLE, FINAL_VALIDATION_NOT_RUN):
                # Align with the pipeline: unavailable final validation is not
                # failure. Missing evidence must never fabricate success either,
                # so both map to `unavailable`, never `passed`.
                digest.overall_verdict = DIGEST_VERDICT_UNAVAILABLE
                digest.reason = (
                    "Source repair applied but final validation is unavailable "
                    "or was not recorded."
                )
                return
            digest.overall_verdict = DIGEST_VERDICT_FAILED
            digest.reason = "Source repair applied but final validation failed."
            return

    if status in _EXECUTION_FAILURE_STATUSES:
        # A successful re-test of the improved tests overrides the previous
        # execution failure.
        if retest is not None and retest.status in (RETEST_FIXED, RETEST_PASSED):
            digest.overall_verdict = DIGEST_VERDICT_PASSED
            digest.reason = "Improved tests pass in re-test."
            return
        digest.overall_verdict = DIGEST_VERDICT_FAILED
        digest.reason = f"Test execution {status}."
        return

    if status == STATUS_PASSED and retest is not None and retest.status in (
        RETEST_REGRESSION,
        RETEST_STILL_FAILING,
    ):
        digest.overall_verdict = DIGEST_VERDICT_FAILED
        digest.reason = f"Re-test reports {retest.status}."
        return

    digest.overall_verdict = DIGEST_VERDICT_PASSED
    digest.reason = "Test execution passed."