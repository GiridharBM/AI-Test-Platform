"""Pydantic models for deterministic failure diagnosis.

DiagnosisResult holds the structured outcome of analysing a completed M6
TestExecutionResult against the project's CodeMap. The deterministic core
produces findings with categories, fingerprints, linked source locations and
severity. Optional local/private AI analysis may add PotentialBug entries that
are clearly distinguished from deterministic findings. No code execution.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# Overall diagnosis statuses (kept minimal).
DIAGNOSIS_NO_FAILURES = "no_failures"
DIAGNOSIS_FAILURES_DIAGNOSED = "failures_diagnosed"
DIAGNOSIS_NO_EXECUTION = "no_execution"
VALID_DIAGNOSIS_STATUSES = {
    DIAGNOSIS_NO_FAILURES,
    DIAGNOSIS_FAILURES_DIAGNOSED,
    DIAGNOSIS_NO_EXECUTION,
}

# Deterministic failure categories.
CATEGORY_ASSERTION = "assertion"
CATEGORY_EXCEPTION = "exception"
CATEGORY_IMPORT_ERROR = "import_error"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_COLLECTION_ERROR = "collection_error"
CATEGORY_SYNTAX_ERROR = "syntax_error"
CATEGORY_UNKNOWN = "unknown"
VALID_CATEGORIES = {
    CATEGORY_ASSERTION,
    CATEGORY_EXCEPTION,
    CATEGORY_IMPORT_ERROR,
    CATEGORY_TIMEOUT,
    CATEGORY_COLLECTION_ERROR,
    CATEGORY_SYNTAX_ERROR,
    CATEGORY_UNKNOWN,
}

# Severity levels.
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
VALID_SEVERITIES = {SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW}


class SourceLocation(BaseModel):
    """A linked source location resolved from the CodeMap.

    Only populated when a reliable mapping exists; confidence reflects the
    strength of the evidence (direct traceback vs. heuristic matching).
    """

    source_file: str
    line_start: int
    line_end: int
    qualified_name: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DiagnosisFinding(BaseModel):
    """A single diagnosed failure locus."""

    finding_id: str
    test_file: str
    test_function: str = ""
    status: str  # "failed" | "error" | "timeout" | "collection_error"
    failure_signature: str
    exception_type: str = ""
    message: str = ""
    traceback: str = ""
    linked_locations: list[SourceLocation] = []
    category: str = CATEGORY_UNKNOWN
    severity: str = SEVERITY_LOW


class PotentialBug(BaseModel):
    """An optional, AI-produced potential-bug signal.

    Clearly distinguished from deterministic findings: produced only by the
    optional local/private AI layer and never a claim of a confirmed bug.
    """

    description: str
    source_file: str = ""
    line_span: list[int] = Field(default_factory=list)  # [start, end]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    model: str = ""


class DiagnosisSummary(BaseModel):
    """Aggregate statistics for a diagnosis run."""

    total_findings: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    linked_locations: int = 0
    potential_bugs: int = 0


class DiagnosisResult(BaseModel):
    """Full deterministic failure diagnosis for an ingested project."""

    schema_version: int = 1
    project_id: str
    created_at: datetime
    overall_status: str = DIAGNOSIS_NO_EXECUTION
    summary: DiagnosisSummary = DiagnosisSummary()
    findings: list[DiagnosisFinding] = []
    potential_bugs: list[PotentialBug] = []
    warnings: list[str] = []
