"""Pydantic models for deterministic sandboxed test execution.

TestExecutionResult holds the outcome of running generated test scaffolds
inside a Docker sandbox. Pure deterministic execution — no LLM, no AI.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Overall execution statuses.
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"
STATUS_UNAVAILABLE = "unavailable"
VALID_STATUSES = {STATUS_PASSED, STATUS_FAILED, STATUS_ERROR, STATUS_TIMEOUT, STATUS_UNAVAILABLE}


class TestFunctionResult(BaseModel):
    """Structured result of a single test function within a test file.

    `duration_seconds` is only populated when pytest actually reports it;
    `None` means the duration was not available, never a fabricated zero.
    """

    test_function: str
    status: str  # STATUS_PASSED | STATUS_FAILED | STATUS_ERROR | "skipped"
    duration_seconds: Optional[float] = None


class TestFileResult(BaseModel):
    """Result of executing a single test file.

    `test_functions` holds one entry per test function parsed from the pytest
    output, when per-test parsing was possible. Older persisted artifacts
    (without per-test rows) remain valid: the field is optional and defaults
    to an empty list.
    """

    file_path: str
    status: str  # STATUS_PASSED | STATUS_FAILED | STATUS_ERROR
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    test_functions: list[TestFunctionResult] = Field(default_factory=list)


class ExecutionSummary(BaseModel):
    """Aggregate counts for an execution run."""

    total_files: int = 0
    total_test_functions: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0


class TestExecutionResult(BaseModel):
    """Full deterministic test execution result."""

    schema_version: int = 1
    project_id: str
    overall_status: str = STATUS_UNAVAILABLE  # passed|failed|error|timeout|unavailable
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    summary: ExecutionSummary = ExecutionSummary()
    file_results: list[TestFileResult] = []
    warnings: list[str] = []
