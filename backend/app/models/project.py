"""Typed Pydantic models for project ingestion and profiling."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.codemap import CodeMap
from app.models.test_plan import TestPlan

OriginMode = Literal["upload", "path"]
ComplexityLevel = Literal["Small", "Medium", "Large"]
FileCategory = Literal["source", "test", "documentation", "configuration", "other"]


class ProjectFile(BaseModel):
    """A single scanned file (relative posix path within the project)."""

    path: str
    language: Optional[str] = None
    category: FileCategory
    size_bytes: int
    lines: int


class LanguageStatistics(BaseModel):
    """Per-language aggregates. Percentages are based on source-code line
    count across source + test files (not raw file count)."""

    name: str
    files: int
    source_lines: int
    percentage: float


class ProjectMetrics(BaseModel):
    total_files: int
    source_files: int
    test_files: int
    documentation_files: int
    configuration_files: int
    other_files: int
    total_lines: int
    source_lines: int
    # Syntax metrics: Python via ast; None = unavailable for this project's
    # languages (Java/JS/TS parsers are not integrated yet).
    functions: Optional[int] = None
    classes: Optional[int] = None
    methods: Optional[int] = None


class DetectedEndpoint(BaseModel):
    method: str
    path: str
    source_file: str
    line: int


class ApiInfo(BaseModel):
    endpoints_detected: int
    endpoints: list[DetectedEndpoint] = []


class ExistingTestInfo(BaseModel):
    files: int
    frameworks: list[str] = []
    example_files: list[str] = []


class DocumentationInfo(BaseModel):
    files: int
    paths: list[str] = []


class DependencyInfo(BaseModel):
    manifests: list[str] = []
    packages_detected: Optional[int] = None
    details: dict[str, str] = Field(default_factory=dict)


class ComplexityInfo(BaseModel):
    level: ComplexityLevel
    reasons: list[str] = []


class ProjectProfile(BaseModel):
    """Full deterministic profile of an ingested project."""

    schema_version: int = 1
    project_id: str
    name: str
    origin: OriginMode
    created_at: datetime
    languages: list[LanguageStatistics] = []
    metrics: ProjectMetrics
    tests: ExistingTestInfo
    documentation: DocumentationInfo
    dependencies: DependencyInfo
    api: ApiInfo
    complexity: ComplexityInfo
    warnings: list[str] = []
    # Populated only when total_files <= config.MAX_PROFILE_FILE_LIST.
    files: Optional[list[ProjectFile]] = None


class ProjectMeta(BaseModel):
    """Basic registration metadata, available before/without profiling."""

    project_id: str
    name: str
    origin: OriginMode
    source_path: Optional[str] = None  # path mode only
    file_count: Optional[int] = None   # upload mode only
    created_at: datetime
    profiled: bool = False


class ProjectDetails(ProjectMeta):
    """GET /api/projects/{id} response: metadata plus profile, codemap, and test plan."""

    profile: Optional[ProjectProfile] = None
    codemap: Optional[CodeMap] = None  # populated after discover
    test_plan: Optional[TestPlan] = None  # populated after plan


class LocalPathRequest(BaseModel):
    path: str
