"""Pydantic models for the code map and test discovery system.

CodeMap is the structured, per-file representation of a project's source
and test code, produced by deterministic ast-based analysis (no LLM,
no code execution). It connects source modules to their functions and
classes, discovers test functions, and maps tests to source targets.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SourceFunction(BaseModel):
    """A single top-level function or class method extracted via ast."""

    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    args: list[str] = []
    decorators: list[str] = []
    has_docstring: bool = False
    is_async: bool = False


class SourceClass(BaseModel):
    """A class with its methods."""

    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    bases: list[str] = []
    decorators: list[str] = []
    has_docstring: bool = False
    methods: list[SourceFunction] = []


class SourceModule(BaseModel):
    """Per-file breakdown of functions, classes, and imports."""

    path: str
    language: str
    functions: list[SourceFunction] = []
    classes: list[SourceClass] = []
    imports: list[str] = []


class TestFunction(BaseModel):
    """A single test function discovered in a test file."""

    name: str
    file_path: str
    line_start: int
    line_end: int
    decorators: list[str] = []
    has_docstring: bool = False
    assertion_count: int = 0


class TestMapping(BaseModel):
    """Heuristic mapping from a test function to a source target."""

    test_function: str
    test_file: str
    source_target: str
    source_file: str
    confidence: float = Field(ge=0.0, le=1.0)
    method: str  # "name_similarity" | "import_analysis" | "none"


class TestableTarget(BaseModel):
    """A function, method, class, or endpoint that can be tested."""

    qualified_name: str
    file_path: str
    target_type: str  # "function" | "method" | "class" | "endpoint"
    has_tests: bool = False
    test_count: int = 0
    test_files: list[str] = []
    mapped_tests: list[str] = []


class CoverageSummary(BaseModel):
    """Aggregate test coverage information for the project."""

    total_targets: int
    targets_with_tests: int
    targets_without_tests: int
    coverage_percentage: float
    untested_functions: list[str] = []
    untested_endpoints: list[str] = []


class CodeMap(BaseModel):
    """Full deterministic code map of an ingested project."""

    schema_version: int = 1
    project_id: str
    created_at: datetime
    source_modules: list[SourceModule] = []
    test_functions: list[TestFunction] = []
    test_mappings: list[TestMapping] = []
    testable_targets: list[TestableTarget] = []
    coverage_summary: CoverageSummary = CoverageSummary(
        total_targets=0,
        targets_with_tests=0,
        targets_without_tests=0,
        coverage_percentage=0.0,
    )
    warnings: list[str] = []
