"""Central configuration constants for the AI Test Platform backend.

All resource limits and detection thresholds live here so there is a single
place to tune scanner behaviour. No magic numbers in service code.

A small deployment surface may be overridden through ``ATP_*`` environment
variables (documented in the root ``.env.example``). Overrides are parsed and
validated at import time: invalid values fail loudly at startup rather than
silently degrading, and configuration values are never logged. When no
variables are set, behaviour is identical to the legacy hard-coded defaults.
"""

import os
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    """Return ``os.environ[name]`` if set to a non-empty value, else ``default``.

    An explicitly empty value is a misconfiguration and raises at import time.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip()
    if value == "":
        raise ValueError(f"Environment variable {name} must not be empty")
    return value


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Like ``_env_str`` but parse and range-check an integer override."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {value}")
    return value


# --- Workspace layout -------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = Path(_env_str("ATP_WORKSPACE_DIR", str(BACKEND_DIR / "workspace")))

# --- HTTP bind address (consumed by deployment launchers, not by the app) ---
# `uvicorn app.main:app` already defaults to 127.0.0.1:8000 when these are
# unset; they exist so deployments can override the bind address explicitly.
BACKEND_HOST = _env_str("ATP_BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = _env_int("ATP_BACKEND_PORT", 8000, minimum=1, maximum=65535)

# --- Ingestion limits -------------------------------------------------------
MAX_UPLOAD_FILES = 5_000                    # files per upload request
MAX_FILES = 20_000                          # files scanned per project
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024       # per-file content limit (2 MiB)
MAX_TOTAL_SIZE_BYTES = 200 * 1024 * 1024    # cumulative upload/scan limit
MAX_DEPTH = 20                              # directory traversal depth
UPLOAD_CHUNK_SIZE = 1024 * 1024             # streaming chunk for uploads
MAX_REL_PATH_LENGTH = 1_024                 # sanitized relative path length

# --- Profiling limits -------------------------------------------------------
MAX_PROFILE_FILE_LIST = 500                 # include file list up to this size
MAX_ENDPOINTS = 500                         # cap on detected API endpoints

# --- Directories never scanned (generated / dependency / VCS dirs) ----------
IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", "__pycache__", ".pytest_cache", ".venv",
    "venv", "env", "dist", "build", "target", ".next", "coverage",
    "htmlcov", ".idea", ".vscode",
})

# --- Language detection (by extension) --------------------------------------
SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".java": "Java",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
}

DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst"})

CONFIG_EXTENSIONS: frozenset[str] = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml",
    ".properties", ".gradle", ".kts", ".conf",
})

BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar", ".jar", ".war",
    ".exe", ".dll", ".so", ".dylib", ".class", ".pyc", ".pyo",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp3", ".mp4", ".avi",
    ".db", ".sqlite", ".sqlite3", ".parquet", ".pkl", ".pickle",
})

# --- Dependency manifests ----------------------------------------------------
DEPENDENCY_MANIFESTS: tuple[str, ...] = (
    "requirements.txt", "pyproject.toml", "Pipfile",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
)

# --- Local-path ingestion safety ---------------------------------------------
# Directory names that are rejected as any path component of a user-supplied
# local project path (exact, case-insensitive match per component).
PROTECTED_DIR_NAMES: frozenset[str] = frozenset({
    "windows", "program files", "program files (x86)", "programdata",
    "appdata", "$recycle.bin", "system volume information",
})

# --- Discovery limits --------------------------------------------------------
MAX_TESTABLE_TARGETS = 5_000                # functions/methods/classes in codemap
MAX_TEST_FUNCTIONS = 5_000                  # test functions discovered per project
MAX_MAPPING_ENTRIES = 10_000                # test-to-source mapping entries

# --- Complexity classification thresholds (documented in docs/architecture.md)
COMPLEXITY_LARGE_SOURCE_FILES = 100
COMPLEXITY_LARGE_SOURCE_LINES = 30_000
COMPLEXITY_SMALL_SOURCE_FILES = 20
COMPLEXITY_SMALL_SOURCE_LINES = 4_000

# --- Test plan risk scoring weights ------------------------------------------
RISK_WEIGHT_NO_TESTS = 0.40
RISK_WEIGHT_ARG_COUNT = 0.15
RISK_WEIGHT_ASYNC = 0.05
RISK_WEIGHT_NO_DOCSTRING = 0.05
RISK_WEIGHT_PUBLIC_METHOD = 0.10
RISK_WEIGHT_HIGH_COMPLEXITY = 0.15
RISK_WEIGHT_LOW_CONFIDENCE_MAP = 0.10

MAX_TEST_SPECS = 10_000

# --- Test scaffold generation limits -----------------------------------------
MAX_GENERATED_FILES = 1_000
MAX_GENERATED_FUNCTIONS = 10_000
MAX_SCAFFOLD_CONTENT_BYTES = 512 * 1024  # 512 KiB per generated file
MAX_EDGE_CASE_TESTS_PER_TARGET = 20

# --- Test execution limits ---------------------------------------------------
EXECUTION_TIMEOUT_SECONDS = 120           # max seconds per execution run
EXECUTION_MEMORY_LIMIT_MB = 512           # Docker --memory
EXECUTION_CPU_LIMIT = 1.0                 # Docker --cpus
EXECUTION_MAX_OUTPUT_BYTES = 1_048_576    # 1 MiB stdout/stderr capture limit
EXECUTION_IMAGE_NAME = _env_str("ATP_TESTRUNNER_IMAGE", "ai-test-platform-testrunner")
EXECUTION_DOCKERFILE = "docker/Dockerfile.testrunner"
# Docker Desktop (Windows/WSL2) can briefly report not-ready right after a
# container teardown or image build. Probe retries are bounded and the pipeline
# still fails closed (unavailable) when the daemon stays unreachable.
EXECUTION_DOCKER_PROBE_RETRIES = 2          # extra probes before declaring unavailable
EXECUTION_DOCKER_PROBE_RETRY_DELAY = 1.0    # seconds between probe retries

# --- Diagnosis limits (Milestone 7) ------------------------------------------
DIAGNOSIS_AI_ENABLED = False              # local/private AI diagnosis is opt-in
DIAGNOSIS_MAX_FINDINGS = 100              # cap on findings per diagnosis run
DIAGNOSIS_MAX_TRACEBACK_BYTES = 32_768     # truncate stored tracebacks to this

# --- Test improvement limits (Milestone 8) -----------------------------------
IMPROVE_AI_ENABLED = False                # local/private AI improvement is opt-in
IMPROVE_MAX_CHANGES = 100                 # cap on improvement changes per run
IMPROVE_MAX_TEST_FILES = 1_000            # cap on generated test files improved
IMPROVE_MAX_TEST_BYTES = 512 * 1024       # per improved file byte limit (512 KiB)

# --- Autonomous pipeline improvement loop ------------------------------------
# AUTO_IMPROVEMENT_MAX_ROUNDS: maximum Improve -> Execute -> Diagnose rounds the
#   autonomous orchestrator runs before pausing at the re-test decision gate.
#   Hard-capped at AUTO_IMPROVEMENT_MAX_ROUNDS_HARD_MAX so configuration can
#   never create an effectively unlimited loop.
AUTO_IMPROVEMENT_MAX_ROUNDS = 3
AUTO_IMPROVEMENT_MAX_ROUNDS_HARD_MAX = 10

# --- Source repair limits (Milestone 11) -------------------------------------
# REPAIR_MAX_ATTEMPTS: maximum distinct evidence-supported candidates validated
#   per repair run. The loop stops immediately on a pass and never exceeds this.
#   Bounds: hard-capped at REPAIR_MAX_ATTEMPTS_HARD_MAX by the service.
REPAIR_MAX_ATTEMPTS = 3
REPAIR_MAX_ATTEMPTS_HARD_MAX = 10

# --- Evaluation limits (Milestone 10) ----------------------------------------
# Each setting: name / purpose / safe default / bounds.
# EVALUATION_MAX_MUTANTS: cap on total mutants generated+executed per evaluation.
#   Purpose: mutation testing multiplies test execution; bound it hard.
#   Bounds: >= 0. 0 disables mutation execution (returns no-op, not run).
EVALUATION_MAX_MUTANTS = 20
# MUTATION_TIMEOUT_SECONDS: per-mutant test execution timeout in the sandbox.
#   Purpose: prevent one slow mutant from blocking the whole evaluation.
#   Bounds: > 0.
MUTATION_TIMEOUT_SECONDS = 30
# EVALUATION_TOTAL_TIMEOUT_SECONDS: overall wall-clock budget for an evaluation.
#   Purpose: resource protection for the total run across all components.
#   Bounds: > 0.
EVALUATION_TOTAL_TIMEOUT_SECONDS = 300
# COVERAGE_TIMEOUT_SECONDS: per coverage measurement execution timeout.
#   Purpose: bound coverage execution (reuses the execution-limit philosophy).
#   Bounds: > 0.
COVERAGE_TIMEOUT_SECONDS = 120
# BENCHMARK_WARMUP_RUNS: warm-up runs excluded from recorded measurements.
#   Purpose: allow the sandbox/runtime to stabilise before measurement.
#   Bounds: >= 0.
BENCHMARK_WARMUP_RUNS = 2
# BENCHMARK_MEASURED_RUNS: measured runs used for min/mean/median.
#   Purpose: keep benchmarking bounded and produce interpretable stats.
#   Bounds: >= 1.
BENCHMARK_MEASURED_RUNS = 5
# BENCHMARK_TIMEOUT_SECONDS: per benchmark run execution timeout.
#   Purpose: prevent a benchmark measuring an unbounded workload.
#   Bounds: > 0.
BENCHMARK_TIMEOUT_SECONDS = 120

# --- Pipeline stuck detection (M15 persistence & recovery) -------------------
# A pipeline left in `running` for longer than this without persisted progress
# is considered abandoned and is recovered to `unavailable` (never silently
# re-run); the existing human Resume path then re-runs the interrupted stage.
PIPELINE_STUCK_TIMEOUT_SECONDS = _env_int(
    "ATP_PIPELINE_STUCK_TIMEOUT_SECONDS", 1800, minimum=1
)
