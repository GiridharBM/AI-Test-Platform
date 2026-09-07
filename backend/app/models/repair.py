"""Pydantic models for bounded source-code repair (Milestone 11).

RepairResult holds the structured outcome of generating and validating
evidence-supported source-code repair candidates against a diagnosed M9
re-test failure, then requiring explicit human approval before the validated
candidate is applied to the original source and the final validation runs.

The autonomous repair loop NEVER modifies the original source; candidate
validation happens exclusively inside an isolated repair workspace using the
existing M6 Docker runner. Only the explicit approval endpoint may apply the
validated candidate to the original source.

No code execution, no LLM, no AI, no network access.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Result-level repair statuses (a run terminates at exactly one of these).
REPAIR_CANDIDATE_GENERATED = "candidate_generated"
REPAIR_VALIDATING = "validating"
REPAIR_VALIDATED_PENDING_APPROVAL = "validated_pending_approval"
REPAIR_APPROVED = "approved"
REPAIR_APPLIED = "applied"
REPAIR_REJECTED = "rejected"
REPAIR_BLOCKED = "blocked"
REPAIR_UNAVAILABLE = "unavailable"
REPAIR_FAILED = "failed"
VALID_REPAIR_RESULT_STATUSES = {
    REPAIR_CANDIDATE_GENERATED,
    REPAIR_VALIDATING,
    REPAIR_VALIDATED_PENDING_APPROVAL,
    REPAIR_APPROVED,
    REPAIR_APPLIED,
    REPAIR_REJECTED,
    REPAIR_BLOCKED,
    REPAIR_UNAVAILABLE,
    REPAIR_FAILED,
}

# Per-attempt validation outcomes.
VALIDATION_PASSED = "passed"
VALIDATION_FAILED = "failed"
VALIDATION_UNAVAILABLE = "unavailable"
VALID_ATTEMPT_STATUSES = {
    VALIDATION_PASSED,
    VALIDATION_FAILED,
    VALIDATION_UNAVAILABLE,
}

# Approval states.
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
VALID_APPROVAL_STATES = {APPROVAL_PENDING, APPROVAL_APPROVED, APPROVAL_REJECTED}

# Application states.
APPLICATION_NOT_APPLIED = "not_applied"
APPLICATION_APPLIED = "applied"
VALID_APPLICATION_STATES = {APPLICATION_NOT_APPLIED, APPLICATION_APPLIED}

# Final-validation outcomes.
FINAL_VALIDATION_PASSED = "passed"
FINAL_VALIDATION_FAILED = "failed"
FINAL_VALIDATION_UNAVAILABLE = "unavailable"
FINAL_VALIDATION_NOT_RUN = "not_run"


class RepairCandidate(BaseModel):
    """A single structured, evidence-supported source-code repair candidate.

    `file_path` is project-relative (`demo_project/calculator.py`).
    `source_location` is the 1-based line range within that file that the
    candidate replaces. `before`/`after` are the exact source lines at that
    range. `operation` is a short, bounded description of the repair kind.
    """

    candidate_id: str
    file_path: str
    source_location: str = ""  # "L<start>-<end>" (single line for binop bodies)
    operation: str = ""
    before: str = ""  # exact original source line(s)
    after: str = ""  # exact repaired source line(s)
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    attempt_number: int = 0


class RepairAttempt(BaseModel):
    """A single persisted validation attempt for a candidate."""

    attempt_number: int = Field(ge=1)
    candidate_id: str
    file_path: str
    source_location: str = ""
    operation: str = ""
    before: str = ""
    after: str = ""
    rationale: str = ""
    validation_status: str = VALIDATION_FAILED
    execution_result: Optional[dict] = None  # serialized TestExecutionResult
    failure_reason: str = ""
    created_at: datetime


class FinalValidation(BaseModel):
    """Recorded outcome of post-application validation against original source."""

    status: str = FINAL_VALIDATION_NOT_RUN
    execution_result: Optional[dict] = None  # serialized TestExecutionResult
    reason: str = ""


class RepairResult(BaseModel):
    """Full bounded source-repair result for an ingested project."""

    schema_version: int = 1
    project_id: str
    status: str = REPAIR_BLOCKED
    retest_diagnosis_id: str = ""  # anchor id from the consumed M9 result
    attempts: list[RepairAttempt] = []
    selected_candidate: Optional[RepairCandidate] = None
    approval_state: str = APPROVAL_PENDING
    application_state: str = APPLICATION_NOT_APPLIED
    final_validation: FinalValidation = FinalValidation()
    warnings: list[str] = []
    reasons: list[str] = []
    created_at: datetime