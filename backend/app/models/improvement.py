"""Pydantic models for deterministic test improvement / regeneration (Milestone 8).

ImprovementResult holds the structured outcome of improving failing generated
tests (M5 scaffolds) based on a completed M7 DiagnosisResult plus the project's
TestPlan and CodeMap. The deterministic improver replaces safe scaffold
placeholders (e.g. NotImplementedError bodies) with evidence-based invocation
logic. It never fabricates behavioral assertions, never suppresses failures,
and only writes to the generated-tests workspace. Original source is never
modified. No code execution.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# Improve statuses (kept minimal to what the deterministic core can emit).
IMPROVE_IMPROVED = "improved"
IMPROVE_PARTIAL = "partial"
IMPROVE_NO_CHANGE = "no_change"
IMPROVE_BLOCKED = "blocked"
VALID_IMPROVE_STATUSES = {
    IMPROVE_IMPROVED,
    IMPROVE_PARTIAL,
    IMPROVE_NO_CHANGE,
    IMPROVE_BLOCKED,
}

# Per-finding/change statuses.
CHANGE_IMPROVED = "improved"
CHANGE_BLOCKED = "blocked"
CHANGE_NO_CHANGE = "no_change"
VALID_CHANGE_STATUSES = {
    CHANGE_IMPROVED,
    CHANGE_BLOCKED,
    CHANGE_NO_CHANGE,
}


class ImprovementChange(BaseModel):
    """A change associated with a single diagnosed finding.

    `before`/`after` carry the full original and improved generated-test file
    content when the file changed (deterministic file-level snapshot). For
    `blocked`/`no_change` findings they are empty.
    """

    finding_id: str
    test_file: str
    test_function: str = ""
    status: str = CHANGE_NO_CHANGE  # improved | blocked | no_change
    reason: str = ""
    before: str = ""  # original generated-test file content (when changed)
    after: str = ""  # improved generated-test file content (when changed)


class ImprovementResult(BaseModel):
    """Full deterministic test-improvement result for an ingested project."""

    schema_version: int = 1
    project_id: str
    diagnosis_id: str = ""  # deterministic id of the consumed DiagnosisResult
    created_at: datetime
    status: str = IMPROVE_NO_CHANGE
    changes: list[ImprovementChange] = []
    files_modified: int = 0
    warnings: list[str] = []
