"""Pydantic models for deterministic test scaffold generation.

TestGenerationResult holds the output of template-based test file generation
from a TestPlan. No LLM, no code execution — pure deterministic templates.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class GeneratedTestFile(BaseModel):
    """A single generated test file with its content and metadata."""

    file_path: str
    content: str
    target_count: int = 0
    priority_range: str = ""
    framework: str = "pytest"


class GenerationSummary(BaseModel):
    """Aggregate statistics for a test generation run."""

    total_files: int = 0
    total_test_functions: int = 0
    total_edge_cases: int = 0
    by_priority: dict[int, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    framework_used: str = "pytest"


class TestGenerationResult(BaseModel):
    """Full deterministic test scaffold generation result."""

    schema_version: int = 1
    project_id: str
    created_at: datetime
    files: list[GeneratedTestFile] = []
    summary: GenerationSummary = GenerationSummary()
    warnings: list[str] = []
