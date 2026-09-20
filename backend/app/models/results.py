"""Pydantic models for the read-only project results digest (Milestone 13).

ResultsDigest is a derived, developer-friendly summary of a project's testing
outcome. It is NEVER a new persistence format: it is computed on demand from
the persisted .meta artifacts and contains only bounded, project-relative,
evidence-bearing fields — no source content, no test source content, no full
tracebacks, no host/sandbox filesystem paths, no secrets.

Stages/artifacts that do not exist are reported as `null` (or an explicit
status where one is available) rather than fabricating success or failure.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Overall digest verdicts (derived from execution / diagnosis / pipeline).
DIGEST_VERDICT_PASSED = "passed"
DIGEST_VERDICT_FAILED = "failed"
DIGEST_VERDICT_NO_EXECUTION = "no_execution"
DIGEST_VERDICT_BLOCKED = "blocked"
DIGEST_VERDICT_UNAVAILABLE = "unavailable"
DIGEST_VERDICT_REPAIR_PENDING = "repair_pending"
DIGEST_VERDICT_REJECTED = "rejected"


class DigestTestCounts(BaseModel):
    """Aggregate test counters from the execution summary."""

    total_files: int = 0
    total_test_functions: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0


class DigestFailingTest(BaseModel):
    """A diagnosed failing test with its evidence-bearing summary fields.

    Only carries normalized, project-relative locations and short exception
    type + message. Full tracebacks and source content are never included.
    """

    test_file: str = ""
    test_function: str = ""
    status: str = ""
    category: str = ""
    severity: str = ""
    exception_type: str = ""
    message: str = ""
    source_file: str = ""
    source_line_start: Optional[int] = None
    source_line_end: Optional[int] = None
    source_qualified_name: str = ""


class DigestSourceLocation(BaseModel):
    """A normalized project-relative source location for a failing test."""

    source_file: str = ""
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    qualified_name: str = ""


class DigestRepairState(BaseModel):
    """State of the M11 source-repair evidence (present only when repair ran)."""

    status: str = ""
    approval_state: str = ""
    application_state: str = ""
    final_validation_status: str = ""
    final_validation_reason: str = ""
    selected_operation: str = ""
    selected_file_path: str = ""
    selected_source_location: str = ""
    selected_rationale: str = ""
    confirmed_repair: bool = False  # True only when applied + final validation passed
    reasons: list[str] = Field(default_factory=list)


class DigestEvaluationState(BaseModel):
    """Coverage / mutation / benchmark highlights (present only when evaluation ran)."""

    status: str = ""  # EvaluationResult.status
    coverage_status: str = ""
    line_coverage_percentage: Optional[float] = None
    mutation_status: str = ""
    mutation_score: Optional[float] = None
    benchmark_status: str = ""
    benchmark_median_seconds: Optional[float] = None


class ResultsDigest(BaseModel):
    """The derived read-only results summary for one project."""

    schema_version: int = 1
    project_id: str
    created_at: datetime

    # Overall verdict derived from execution + diagnosis + repair evidence.
    overall_verdict: str = DIGEST_VERDICT_NO_EXECUTION
    reason: str = ""

    # Pipeline presence (null when no pipeline state exists yet).
    pipeline_status: Optional[str] = None
    pipeline_current_stage: Optional[str] = None

    # Execution artifact (null only when there is no execution).
    execution_status: Optional[str] = None
    execution_duration_seconds: Optional[float] = None
    test_counts: Optional[DigestTestCounts] = None

    # Diagnosis artifact (null when none exists).
    diagnosis_status: Optional[str] = None
    failing_tests: list[DigestFailingTest] = Field(default_factory=list)

    # Improvement evidence (null when none exists).
    improvement_status: Optional[str] = None
    improvement_changes: Optional[int] = None
    improvement_files_modified: Optional[int] = None

    # Re-test evidence (null when none exists).
    retest_status: Optional[str] = None

    # Repair evidence (null when repair has not run).
    repair: Optional[DigestRepairState] = None

    # Evaluation evidence (null when evaluation has not run).
    evaluation: Optional[DigestEvaluationState] = None

    # Names of .meta artifacts that exist but are unreadable (corrupt). Their
    # derived sections render as null/unavailable — never as passed.
    corrupt_artifacts: list[str] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)