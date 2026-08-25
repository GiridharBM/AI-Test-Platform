"""Pydantic models for deterministic test plan generation.

TestPlan is the structured, prioritised specification of what tests to write
for a project. It is produced entirely by rule-based analysis of the CodeMap
and ProjectProfile — no LLM, no code execution.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class EdgeCase(BaseModel):
    """A specific edge case to exercise for a test target parameter."""

    parameter: str
    case_type: str  # "none" | "empty" | "boundary" | "negative" | "overflow" | "boolean"
    description: str


class TestSpec(BaseModel):
    """A single test specification: what to test and how to classify it."""

    target_qualified_name: str
    target_file: str
    target_type: str  # "function" | "method" | "class"
    priority: int = Field(ge=1, le=5)  # 1=critical, 5=low
    test_type: str  # "unit" | "edge_case" | "negative" | "integration_hint"
    suggested_test_name: str
    preconditions: list[str] = []
    edge_cases: list[EdgeCase] = []
    related_tested_targets: list[str] = []
    risk_score: float = Field(ge=0.0, le=1.0)


class TestPlanSummary(BaseModel):
    """Aggregate statistics for a generated test plan."""

    total_specs: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    by_type: dict[str, int] = {}
    untested_modules: list[str] = []


class TestPlan(BaseModel):
    """Full deterministic test plan for an ingested project."""

    schema_version: int = 1
    project_id: str
    created_at: datetime
    specs: list[TestSpec] = []
    summary: TestPlanSummary
    warnings: list[str] = []
