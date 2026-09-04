"""Central configuration constants for the AI Test Platform backend.

All resource limits and detection thresholds live here so there is a single
place to tune scanner behaviour. No magic numbers in service code.
"""

from pathlib import Path

# --- Workspace layout -------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = BACKEND_DIR / "workspace"

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
EXECUTION_IMAGE_NAME = "ai-test-platform-testrunner"
EXECUTION_DOCKERFILE = "docker/Dockerfile.testrunner"

# --- Diagnosis limits (Milestone 7) ------------------------------------------
DIAGNOSIS_AI_ENABLED = False              # local/private AI diagnosis is opt-in
DIAGNOSIS_MAX_FINDINGS = 100              # cap on findings per diagnosis run
DIAGNOSIS_MAX_TRACEBACK_BYTES = 32_768     # truncate stored tracebacks to this

# --- Test improvement limits (Milestone 8) -----------------------------------
IMPROVE_AI_ENABLED = False                # local/private AI improvement is opt-in
IMPROVE_MAX_CHANGES = 100                 # cap on improvement changes per run
IMPROVE_MAX_TEST_FILES = 1_000            # cap on generated test files improved
IMPROVE_MAX_TEST_BYTES = 512 * 1024       # per improved file byte limit (512 KiB)
