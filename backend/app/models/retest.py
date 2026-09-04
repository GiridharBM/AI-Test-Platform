"""Pydantic models for deterministic re-test verification (Milestone 9).

ReTestResult holds the structured outcome of re-testing M8-improved generated
tests inside the M6 Docker sandbox and comparing the re-test against the
previous M6 execution baseline. Pure deterministic comparison — no LLM, no AI.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# Overall re-test statuses.
RETEST_FIXED = "fixed"
RETEST_STILL_FAILING = "still_failing"
RETEST_REGRESSION = "regression"
RETEST_PASSED = "passed"
RETEST_BLOCKED = "blocked"
RETEST_UNAVAILABLE = "unavailable"
RETEST_NO_OP = "no_op"
VALID_RETEST_STATUSES = {
    RETEST_FIXED,
    RETEST_STILL_FAILING,
    RETEST_REGRESSION,
    RETEST_PASSED,
    RETEST_BLOCKED,
    RETEST_UNAVAILABLE,
    RETEST_NO_OP,
}

# Per-test verdicts.
VERDICT_FIXED = "fixed"
VERDICT_STILL_FAILING = "still_failing"
VERDICT_REGRESSION = "regression"
VERDICT_PASSED = "passed"
VERDICT_BLOCKED = "blocked"
VERDICT_UNAVAILABLE = "unavailable"
VALID_VERDICTS = {
    VERDICT_FIXED,
    VERDICT_STILL_FAILING,
    VERDICT_REGRESSION,
    VERDICT_PASSED,
    VERDICT_BLOCKED,
    VERDICT_UNAVAILABLE,
}


class ReTestSelection(BaseModel):
    """A selected test identified from the M8 improvement changes."""

    test_file: str
    test_function: str = ""
    improvement_status: str = ""  # from ImprovementChange.status


class ReTestComparison(BaseModel):
    """Per-test comparison between baseline M6 execution and re-test result.

    `baseline_status` is the status of this test in the previous M6
    TestExecutionResult (when correlated). `retest_status` is the status in
    the re-test. `verdict` is the derived comparison outcome.
    """

    test_file: str
    test_function: str = ""
    baseline_status: str = ""  # from M6 TestFileResult.status (empty if unavailable)
    retest_status: str = ""  # from re-test execution
    verdict: str = VERDICT_BLOCKED
    reason: str = ""


class ReTestSummary(BaseModel):
    """Aggregate counts for a re-test run."""

    selected: int = 0
    executed: int = 0
    fixed: int = 0
    still_failing: int = 0
    regression: int = 0
    passed: int = 0
    blocked: int = 0
    unavailable: int = 0


class ReTestResult(BaseModel):
    """Full deterministic re-test result for an ingested project.

    Answers: "Did the M8 improvement change the previous diagnosed outcome?"
    """

    schema_version: int = 1
    project_id: str
    status: str = RETEST_NO_OP
    diagnosis_id: str = ""  # deterministic id of the consumed DiagnosisResult
    improvement_id: str = ""  # deterministic id derived from ImprovementResult
    selected_tests: list[ReTestSelection] = []
    execution_status: str = ""  # from M6 runner overall_status
    comparisons: list[ReTestComparison] = []
    summary: ReTestSummary = ReTestSummary()
    warnings: list[str] = []
    reasons: list[str] = []
    created_at: datetime
