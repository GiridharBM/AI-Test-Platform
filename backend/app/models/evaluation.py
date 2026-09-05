"""Pydantic models for pipeline evaluation (Milestone 10).

EvaluationResult is the structured envelope holding the three independent
evaluation components: dynamic coverage analysis, bounded mutation testing,
and bounded CPU/GPU benchmarking. Pure deterministic computation where the
input is static; benchmark timings are inherently variable and are reported
honestly as measurements, never as logical identity.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Per-component / overall statuses distinguish why something didn't produce a
# value so a missing optional component never silently becomes success.
EVAL_COMPLETED = "completed"
EVAL_UNAVAILABLE = "unavailable"
EVAL_BLOCKED = "blocked"
EVAL_ERROR = "error"
EVAL_NOT_RUN = "not_run"
VALID_EVAL_STATUSES = {
    EVAL_COMPLETED,
    EVAL_UNAVAILABLE,
    EVAL_BLOCKED,
    EVAL_ERROR,
    EVAL_NOT_RUN,
}

# Per-mutant classification.
MUTANT_KILLED = "killed"
MUTANT_SURVIVED = "survived"
MUTANT_TIMEOUT = "timeout"
MUTANT_ERROR = "error"
VALID_MUTANT_STATUSES = {
    MUTANT_KILLED,
    MUTANT_SURVIVED,
    MUTANT_TIMEOUT,
    MUTANT_ERROR,
}

_DEFAULT_COVERAGE_STATUS = EVAL_NOT_RUN


class CoverageFile(BaseModel):
    """Per-file dynamic coverage measurement."""

    file_path: str
    executable_lines: int = 0
    covered_lines: int = 0
    missing_lines: list[int] = []
    percentage: float = 0.0
    branch_total: int = 0
    branch_covered: int = 0


class CoverageResult(BaseModel):
    """Dynamic Python execution coverage measurement (M10, not M3 static map)."""

    status: str = _DEFAULT_COVERAGE_STATUS
    method: str = "dynamic-python-line"
    line_total: int = 0
    line_covered: int = 0
    line_percentage: float = 0.0
    # Branch data is present only when the tooling could measure it; otherwise
    # it stays 0 and branch_percentage is None (never fabricated).
    branch_total: int = 0
    branch_covered: int = 0
    branch_percentage: Optional[float] = None
    files: list[CoverageFile] = []
    warnings: list[str] = []
    reasons: list[str] = []


class Mutant(BaseModel):
    """A single controlled source mutation and its test outcome."""

    id: str
    file_path: str
    line: int
    operator: str
    description: str
    status: str = MUTANT_ERROR
    reason: str = ""


class MutationResult(BaseModel):
    """Bounded mutation testing results over the project's Python source."""

    status: str = EVAL_NOT_RUN
    total_mutants: int = 0
    killed: int = 0
    survived: int = 0
    timeout: int = 0
    error: int = 0
    # Score denominator = valid executable mutants = killed + survived.
    # Timeout/error mutants are excluded because they did not yield a decisive
    # pass/fail outcome, as documented in score_denominator.
    valid_mutants: int = 0
    mutation_score: Optional[float] = None
    score_denominator: str = "killed + survived (valid executable mutants)"
    mutants: list[Mutant] = []
    warnings: list[str] = []
    reasons: list[str] = []


class BenchmarkResult(BaseModel):
    """Bounded CPU / GPU benchmark of the sandboxed test-execution workload.

    Benchmark numbers are inherently variable measurements; they are never
    used as logical IDs and are not claimed to be reproducible exact values.
    """

    status: str = EVAL_NOT_RUN
    component: str = "test-execution"
    run_count: int = 0
    warm_up_count: int = 0
    measured_runs: list[float] = []
    min_seconds: Optional[float] = None
    mean_seconds: Optional[float] = None
    median_seconds: Optional[float] = None
    cpu_available: bool = False
    gpu_available: bool = False
    gpu_status: str = EVAL_UNAVAILABLE
    warnings: list[str] = []
    reasons: list[str] = []


class EvaluationResult(BaseModel):
    """Full evaluation envelope for an ingested project."""

    schema_version: int = 1
    project_id: str
    status: str = EVAL_NOT_RUN
    retest_id: str = ""  # id of the consumed M9 ReTestResult, if any
    coverage: CoverageResult = CoverageResult()
    mutation: MutationResult = MutationResult()
    benchmark: BenchmarkResult = BenchmarkResult()
    summary: str = ""
    warnings: list[str] = []
    reasons: list[str] = []
    created_at: datetime
