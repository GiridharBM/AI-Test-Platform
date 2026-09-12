"""Deterministic re-test verification (Milestone 9).

Consumes the M8 ImprovementResult, M7 DiagnosisResult, and previous M6
TestExecutionResult. Re-executes the improved generated tests inside the
M6 Docker sandbox and compares the re-test against the baseline to derive
per-test verdicts (fixed / still_failing / regression / passed).

Guarantees & boundaries
------------------------
* Reuses the existing M6 Docker execution infrastructure (no second mechanism).
* Only tests actually changed by M8 (status == "improved") are selected for
  re-test verification.
* Never modifies source code, generated tests, or .meta artifacts other than
  .meta/retest.json.
* Never triggers another improvement.
* Deterministic, idempotent, no randomness, no AI.
"""

from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.models.diagnosis import (
    DiagnosisResult,
    VALID_DIAGNOSIS_STATUSES as _DIAG_STATUSES,
)
from app.models.execution import (
    STATUS_PASSED,
    STATUS_FAILED,
    STATUS_ERROR,
    STATUS_TIMEOUT,
    STATUS_UNAVAILABLE,
    TestExecutionResult,
)
from app.models.improvement import (
    CHANGE_IMPROVED,
    IMPROVE_NO_CHANGE,
    IMPROVE_BLOCKED,
    ImprovementResult,
)
from app.models.retest import (
    RETEST_FIXED,
    RETEST_STILL_FAILING,
    RETEST_REGRESSION,
    RETEST_PASSED,
    RETEST_BLOCKED,
    RETEST_UNAVAILABLE,
    RETEST_NO_OP,
    VERDICT_FIXED,
    VERDICT_STILL_FAILING,
    VERDICT_REGRESSION,
    VERDICT_PASSED,
    VERDICT_BLOCKED,
    VERDICT_UNAVAILABLE,
    ReTestComparison,
    ReTestResult,
    ReTestSelection,
    ReTestSummary,
)

# Execution statuses that mean the test was "failing" for comparison.
_FAILING_STATUSES = {STATUS_FAILED, STATUS_ERROR, STATUS_TIMEOUT}
_PASSING_STATUSES = {STATUS_PASSED}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _select_improved_tests(improvement: ImprovementResult) -> list[ReTestSelection]:
    """Extract tests where M8 produced an improved change."""
    selected: list[ReTestSelection] = []
    seen: set[tuple[str, str]] = set()
    for change in improvement.changes:
        if change.status != CHANGE_IMPROVED:
            continue
        key = (change.test_file, change.test_function)
        if key in seen:
            continue
        seen.add(key)
        selected.append(ReTestSelection(
            test_file=change.test_file,
            test_function=change.test_function,
            improvement_status=change.status,
        ))
    return selected


def _build_baseline_status_map(
    prev_execution: TestExecutionResult | None,
) -> dict[str, str]:
    """Build a file_path -> status map from the previous M6 TestExecutionResult."""
    if prev_execution is None:
        return {}
    return {fr.file_path: fr.status for fr in prev_execution.file_results}


def _build_baseline_function_map(
    diagnosis: DiagnosisResult | None,
) -> dict[tuple[str, str], str]:
    """Build (test_file, test_function) -> baseline failure status from diagnosis.

    This captures which specific functions were diagnosed as failing.
    """
    if diagnosis is None:
        return {}
    result: dict[tuple[str, str], str] = {}
    for finding in diagnosis.findings:
        key = (finding.test_file, finding.test_function)
        result[key] = finding.status
    return result


def _select_user_behavioral_tests(
    diagnosis: DiagnosisResult | None,
    copied_user_tests: list[str] | None,
) -> list[ReTestSelection]:
    """Select discovered user behavioral tests that failed at baseline (M7).

    These tests are not M8-improved (M8 only rewrites scaffold placeholders),
    so the M9 selection must include them explicitly or their still-failing
    verdicts never reach M11. The copied `user_*` names in generated_tests/ are
    what diagnosis recorded as `test_file`.
    """
    if diagnosis is None or not copied_user_tests:
        return []
    user_files = set(copied_user_tests)
    selected: list[ReTestSelection] = []
    seen: set[tuple[str, str]] = set()
    for finding in diagnosis.findings:
        if finding.test_file not in user_files:
            continue
        key = (finding.test_file, finding.test_function)
        if key in seen:
            continue
        seen.add(key)
        selected.append(ReTestSelection(
            test_file=finding.test_file,
            test_function=finding.test_function,
            improvement_status="user_behavioral",
        ))
    return selected


def _derive_file_retest_status(
    retest_result: TestExecutionResult,
    test_file: str,
) -> str:
    """Derive the re-test status for a specific test file from the execution result.

    Matches by file_path in the re-test result's file_results. Returns the
    status if found, empty string if the file was not executed.
    """
    for fr in retest_result.file_results:
        if fr.file_path == test_file:
            return fr.status
    return ""


def _derive_verdict(
    baseline_status: str,
    retest_status: str,
    baseline_func_status: str,
) -> tuple[str, str]:
    """Derive the per-test verdict and reason from baseline vs re-test evidence.

    Returns (verdict, reason).
    """
    # If re-test didn't produce a status for this file, it wasn't executed.
    if not retest_status:
        return VERDICT_BLOCKED, "Test file not present in re-test execution results."

    # If re-test execution was unavailable, the test is unavailable.
    if retest_status == STATUS_UNAVAILABLE:
        return VERDICT_UNAVAILABLE, "Execution environment unavailable."

    # If re-test execution errored/timed out at the file level (collection error,
    # syntax error, import error in the test file itself), treat as blocked.
    if retest_status == STATUS_TIMEOUT:
        return VERDICT_BLOCKED, "Re-test execution timed out for this file."

    # --- Baseline had a known failure for this specific function ---
    if baseline_func_status in _FAILING_STATUSES:
        if retest_status in _PASSING_STATUSES:
            return VERDICT_FIXED, f"Previously {baseline_func_status}; now passes."
        elif retest_status in _FAILING_STATUSES:
            return VERDICT_STILL_FAILING, f"Previously {baseline_func_status}; still {retest_status}."
        else:
            return VERDICT_BLOCKED, f"Re-test status '{retest_status}' unclassifiable against baseline '{baseline_func_status}'."

    # --- No specific function-level diagnosis (function was not in findings) ---
    # Use file-level baseline correlation.
    if baseline_status in _FAILING_STATUSES:
        if retest_status in _PASSING_STATUSES:
            return VERDICT_FIXED, f"File previously failing; now passes."
        elif retest_status in _FAILING_STATUSES:
            return VERDICT_STILL_FAILING, f"File still {retest_status} after improvement."
        else:
            return VERDICT_BLOCKED, f"Re-test status '{retest_status}' unclassifiable against file baseline '{baseline_status}'."

    if baseline_status in _PASSING_STATUSES:
        if retest_status in _PASSING_STATUSES:
            return VERDICT_PASSED, "File was passing before; still passes."
        elif retest_status in _FAILING_STATUSES:
            return VERDICT_REGRESSION, f"Previously passing; now {retest_status}."
        else:
            return VERDICT_BLOCKED, f"Re-test status '{retest_status}' unclassifiable against baseline '{baseline_status}'."

    # --- No baseline available at all ---
    # Per spec: missing diagnosis or missing previous execution = blocked.
    # Cannot classify retest result without baseline evidence.
    return VERDICT_BLOCKED, "No baseline available; cannot classify re-test result."


def retest_from_artifacts(
    improvement: ImprovementResult,
    diagnosis: DiagnosisResult | None,
    prev_execution: TestExecutionResult | None,
    gen_root: Path | None = None,
    project_id: str = "",
    copied_user_tests: list[str] | None = None,
    source_root: Path | None = None,
) -> ReTestResult:
    """Core deterministic re-test logic.

    1. Select improved tests from ImprovementResult plus discovered user
       behavioral tests that failed at baseline.
    2. If nothing to re-test, return no_op/blocked.
    3. Re-execute the improved generated tests via M6 runner.
    4. Compare re-test against baseline and derive verdicts.
    """
    ws_root = gen_root if gen_root is not None else config.WORKSPACE_DIR

    user_selected = _select_user_behavioral_tests(diagnosis, copied_user_tests)

    # --- Fast-path: nothing to re-test ---
    # The NO_CHANGE/BLOCKED fast-path only holds when there is also no failing
    # user behavioral test to re-verify — a merged user test that is still
    # failing must surface as `still_failing` so M11 can target it.
    if improvement.status in (IMPROVE_NO_CHANGE, IMPROVE_BLOCKED) and not user_selected:
        reasons = []
        if improvement.status == IMPROVE_NO_CHANGE:
            reasons.append("M8 produced no changes — nothing to re-test.")
        else:
            reasons.append("M8 improvement was blocked — nothing to re-test.")
        return ReTestResult(
            project_id=project_id,
            status=RETEST_NO_OP,
            diagnosis_id=improvement.diagnosis_id,
            improvement_id="",
            selected_tests=[],
            execution_status="",
            comparisons=[],
            summary=ReTestSummary(),
            warnings=list(improvement.warnings),
            reasons=reasons,
            created_at=_now(),
        )

    # --- Select tests actually changed by M8 ---
    selected = _select_improved_tests(improvement)
    if not selected and not user_selected:
        return ReTestResult(
            project_id=project_id,
            status=RETEST_NO_OP,
            diagnosis_id=improvement.diagnosis_id,
            improvement_id="",
            selected_tests=[],
            execution_status="",
            comparisons=[],
            summary=ReTestSummary(),
            warnings=list(improvement.warnings),
            reasons=["M8 produced no changes with status 'improved' — nothing to re-test."],
            created_at=_now(),
        )

    # Combine improved + user selections without duplicating a (file, func).
    seen_keys: set[tuple[str, str]] = set()
    combined: list[ReTestSelection] = []
    for sel in [*selected, *user_selected]:
        key = (sel.test_file, sel.test_function)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        combined.append(sel)
    selected = combined

    # --- Baseline completeness gate ---
    # Per spec: missing diagnosis or missing previous execution = blocked.
    # Cannot derive meaningful verdicts without baseline evidence.
    missing_inputs: list[str] = []
    if diagnosis is None:
        missing_inputs.append("diagnosis")
    if prev_execution is None:
        missing_inputs.append("previous execution")
    if missing_inputs:
        warnings = list(improvement.warnings)
        warnings.append(
            f"Missing baseline: {', '.join(missing_inputs)}. "
            "All verdicts will be blocked."
        )
        return ReTestResult(
            project_id=project_id,
            status=RETEST_BLOCKED,
            diagnosis_id=improvement.diagnosis_id,
            improvement_id="",
            selected_tests=selected,
            execution_status="",
            comparisons=[],
            summary=ReTestSummary(selected=len(selected)),
            warnings=warnings,
            reasons=[f"Blocked: {', '.join(missing_inputs)} not available."],
            created_at=_now(),
        )

    # --- Resolve the generated_tests directory ---
    gt_root = Path(ws_root) / project_id / "generated_tests"
    if not gt_root.is_dir():
        reasons = ["generated_tests/ directory not found — cannot re-test."]
        return ReTestResult(
            project_id=project_id,
            status=RETEST_BLOCKED,
            diagnosis_id=improvement.diagnosis_id,
            improvement_id="",
            selected_tests=selected,
            execution_status="",
            comparisons=[],
            summary=ReTestSummary(selected=len(selected)),
            warnings=list(improvement.warnings),
            reasons=reasons,
            created_at=_now(),
        )

    # --- Execute the generated tests via M6 runner ---
    from app.execution.runner import execute_tests

    # Re-run the SAME suite M6 ran, so user behavioral tests that import their
    # project (e.g. `from calc import add`) resolve identically. Omitting the
    # source mount here would make those files fail at collection, erasing the
    # verdict this stage exists to produce.
    if source_root is None:
        source_root = Path(ws_root) / project_id / "source"
    retest_exec = execute_tests(gt_root, project_id, source_root=source_root)

    if retest_exec.overall_status == STATUS_UNAVAILABLE:
        return ReTestResult(
            project_id=project_id,
            status=RETEST_UNAVAILABLE,
            diagnosis_id=improvement.diagnosis_id,
            improvement_id="",
            selected_tests=selected,
            execution_status=retest_exec.overall_status,
            comparisons=[],
            summary=ReTestSummary(selected=len(selected)),
            warnings=list(improvement.warnings),
            reasons=["Docker execution environment unavailable."],
            created_at=_now(),
        )

    # --- Build baseline lookup maps ---
    baseline_file_map = _build_baseline_status_map(prev_execution)
    baseline_func_map = _build_baseline_function_map(diagnosis)

    # --- Derive per-test verdicts ---
    comparisons: list[ReTestComparison] = []
    summary = ReTestSummary(selected=len(selected))

    for sel in selected:
        retest_status = _derive_file_retest_status(retest_exec, sel.test_file)
        baseline_file_status = baseline_file_map.get(sel.test_file, "")
        baseline_func_status = baseline_func_map.get(
            (sel.test_file, sel.test_function), ""
        )

        verdict, reason = _derive_verdict(
            baseline_file_status, retest_status, baseline_func_status
        )

        comparisons.append(ReTestComparison(
            test_file=sel.test_file,
            test_function=sel.test_function,
            baseline_status=baseline_file_status or baseline_func_status,
            retest_status=retest_status,
            verdict=verdict,
            reason=reason,
        ))

        # Update summary counters.
        if verdict == VERDICT_FIXED:
            summary.fixed += 1
        elif verdict == VERDICT_STILL_FAILING:
            summary.still_failing += 1
        elif verdict == VERDICT_REGRESSION:
            summary.regression += 1
        elif verdict == VERDICT_PASSED:
            summary.passed += 1
        elif verdict == VERDICT_BLOCKED:
            summary.blocked += 1
        elif verdict == VERDICT_UNAVAILABLE:
            summary.unavailable += 1

    summary.executed = sum(
        1 for c in comparisons if c.retest_status != ""
    )

    # --- Derive overall status ---
    if summary.fixed > 0 and summary.regression == 0 and summary.still_failing == 0:
        overall = RETEST_FIXED
    elif summary.regression > 0:
        overall = RETEST_REGRESSION
    elif summary.still_failing > 0:
        overall = RETEST_STILL_FAILING
    elif summary.fixed == 0 and summary.passed > 0:
        overall = RETEST_PASSED
    elif summary.blocked > 0:
        overall = RETEST_BLOCKED
    elif summary.unavailable > 0:
        overall = RETEST_UNAVAILABLE
    else:
        overall = RETEST_PASSED

    warnings = list(improvement.warnings)
    reasons: list[str] = []
    if summary.fixed > 0:
        reasons.append(f"{summary.fixed} test(s) fixed.")
    if summary.still_failing > 0:
        reasons.append(f"{summary.still_failing} test(s) still failing.")
    if summary.regression > 0:
        reasons.append(f"{summary.regression} test(s) regressed.")
    if summary.passed > 0:
        reasons.append(f"{summary.passed} test(s) passed without prior failure.")
    if summary.blocked > 0:
        reasons.append(f"{summary.blocked} test(s) could not be compared.")

    return ReTestResult(
        project_id=project_id,
        status=overall,
        diagnosis_id=improvement.diagnosis_id,
        improvement_id="",
        selected_tests=selected,
        execution_status=retest_exec.overall_status,
        comparisons=comparisons,
        summary=summary,
        warnings=warnings,
        reasons=reasons,
        created_at=_now(),
    )


def retest_project(
    project_id: str,
    workspace: Path | None = None,
) -> ReTestResult:
    """Orchestrate deterministic re-test from persisted .meta artifacts.

    Raises FileNotFoundError if required artifacts are missing.
    """
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    ingestion.read_meta(ws, project_id)

    # --- Read improvement (mandatory for re-test) ---
    raw_improve = ingestion.read_improvement(ws, project_id)
    if raw_improve is None:
        raise FileNotFoundError("No improvement result. Run /improve first.")
    improvement = ImprovementResult.model_validate_json(raw_improve)

    # --- Read diagnosis (for baseline correlation) ---
    diagnosis = None
    raw_diag = ingestion.read_diagnosis(ws, project_id)
    if raw_diag is not None:
        diagnosis = DiagnosisResult.model_validate_json(raw_diag)

    # --- Read previous execution (for baseline correlation) ---
    prev_execution = None
    raw_exec = ingestion.read_execution(ws, project_id)
    if raw_exec is not None:
        prev_execution = TestExecutionResult.model_validate_json(raw_exec)

    # --- Read merged user test names (copied into the executed suite at M5) ---
    copied_user_tests = None
    raw_gen = ingestion.read_test_generation(ws, project_id)
    if raw_gen is not None:
        from app.models.test_generation import TestGenerationResult

        copied_user_tests = (
            TestGenerationResult.model_validate_json(raw_gen).merged_user_files or []
        )

    result = retest_from_artifacts(
        improvement, diagnosis, prev_execution,
        gen_root=ws, project_id=project_id,
        copied_user_tests=copied_user_tests,
        source_root=Path(ws) / project_id / "source",
    )

    ingestion.save_retest(ws, result.model_dump_json())
    return result
