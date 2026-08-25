"""Deterministic project profiling.

This module performs NO LLM calls and NEVER executes, imports or installs
project code. It only reads files to compute statistics.

Documented metrics:
- Language percentages are based on source-code line count across
  source + test files (not raw file count).
- total_lines counts physical lines in all non-binary scanned files;
  source_lines counts lines in source + test files only.
- functions/classes/methods are computed via Python's ast module for .py
  files. For Java/JavaScript/TypeScript they are reported as None
  (unavailable) until a proper parser (e.g. Tree-sitter) is integrated.
"""

import ast
import fnmatch
import json
import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.models.project import (
    ApiInfo,
    ComplexityInfo,
    DependencyInfo,
    DetectedEndpoint,
    DocumentationInfo,
    ExistingTestInfo,
    LanguageStatistics,
    ProjectFile,
    ProjectMetrics,
    ProjectProfile,
)

# --- Classification helpers ---------------------------------------------------

_TEST_DIR_PARTS = {"tests", "test", "__tests__", "spec"}

_PY_TEST_RE = re.compile(r"(?:^test_.*\.py$|.*_test\.py$)")
_JAVA_TEST_RE = re.compile(r".*(?:Test|Tests|IT)\.java$")
_JS_TEST_RE = re.compile(r".*\.(?:test|spec)\.(?:js|jsx|mjs|cjs|ts|tsx)$")

_UNITTEST_IMPORT_RE = re.compile(r"^\s*(?:import unittest\b|from unittest\b)", re.MULTILINE)

_PY_API_RE = re.compile(
    r"^\s*@[\w\.]+\.(get|post|put|delete|patch|head|options)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_JAVA_API_RE = re.compile(
    r"@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(([^)]*)\)"
)
_JAVA_PATH_RE = re.compile(r"""['\"]([^'\"]+)['\"]""")
_JS_API_RE = re.compile(
    r"""\b(?:app|router|server|api)\s*\.\s*
        (get|post|put|delete|patch|all)\s*\(\s*['\"`]([^'\"`]+)['\"`]""",
    re.VERBOSE,
)

_GRADLE_DEP_RE = re.compile(
    r"^\s*(?:implementation|api|compile|compileOnly|runtimeOnly|"
    r"testImplementation|androidTestImplementation)\b"
)


class _ScanState:
    def __init__(self) -> None:
        self.files: list[ProjectFile] = []
        self.total_lines = 0
        self.source_lines = 0
        self.lang_files: dict[str, int] = {}
        self.lang_lines: dict[str, int] = {}
        self.py_functions = 0
        self.py_classes = 0
        self.py_methods = 0
        self.has_python = False
        self.warnings: list[str] = []
        self.file_count = 0
        self.total_bytes = 0
        self.depth_exceeded = False
        self.file_cap_reached = False
        self.size_cap_reached = False


def _load_gitignore_patterns(root: Path) -> list[tuple[str, bool]]:
    """Parse a practical subset of the project's root .gitignore.

    Supported: comments, blank lines, literal names, trailing '/' directory
    patterns, '*' globs via fnmatch, leading '/' anchored patterns.
    Unsupported (ignored): negations ('!...'), '**' semantics, per-directory
    nested .gitignore files. Matching is conservative (may over-ignore).
    """
    gi = root / ".gitignore"
    patterns: list[tuple[str, bool]] = []
    if not gi.is_file():
        return patterns
    try:
        text = gi.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return patterns
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        is_dir = line.endswith("/")
        line = line.rstrip("/")
        anchored = line.startswith("/")
        if anchored:
            line = line.lstrip("/")
        patterns.append((line, is_dir))
    return patterns


def _gitignore_match(pattern: str, is_dir_pattern: bool, rel_posix: str, is_dir: bool) -> bool:
    name = rel_posix.rsplit("/", 1)[-1]
    if is_dir_pattern and not is_dir:
        # A dir pattern also ignores files inside that dir:
        if any(part == pattern.rstrip("/") for part in rel_posix.split("/")):
            return True
        return False
    if "/" in pattern:
        if fnmatch.fnmatch(rel_posix, pattern) or rel_posix.startswith(pattern + "/"):
            return True
        return False
    if fnmatch.fnmatch(name, pattern):
        return True
    if "*" not in pattern and "?" not in pattern:
        # Literal names match files OR directories anywhere in the tree.
        if any(part == pattern for part in rel_posix.split("/")):
            return True
    return False


def _classify(rel_posix: str, name: str, ext: str) -> str:
    parts = rel_posix.split("/")
    parent_parts = parts[:-1]

    if ext == ".py" and _PY_TEST_RE.match(name):
        return "test"
    if ext == ".java" and _JAVA_TEST_RE.match(name):
        return "test"
    if ext in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"} and _JS_TEST_RE.match(name):
        return "test"
    if any(p.lower() in _TEST_DIR_PARTS for p in parent_parts):
        return "test"

    if ext in config.DOC_EXTENSIONS or name.lower().startswith("readme") or "docs" in parent_parts:
        return "documentation"

    if ext in config.CONFIG_EXTENSIONS or name in {"Dockerfile", "Makefile", ".gitignore"}:
        return "configuration"

    if ext in config.SOURCE_EXTENSIONS:
        return "source"

    return "other"


def _count_lines(path: Path, size: int, state: _ScanState) -> int:
    if ext_is_binary(path.suffix.lower()):
        return 0
    if size > config.MAX_FILE_SIZE_BYTES:
        state.size_cap_reached = True
        return 0
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    return len(data.decode("utf-8", errors="replace").splitlines())


def ext_is_binary(ext: str) -> bool:
    return ext in config.BINARY_EXTENSIONS


def _count_python_defs(tree: ast.AST) -> tuple[int, int, int]:
    """Return (functions, classes, methods) using Python's ast module."""
    functions = classes = methods = 0

    def visit(node: ast.AST, in_class: bool) -> None:
        nonlocal functions, classes, methods
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if in_class:
                    methods += 1
                else:
                    functions += 1
                visit(child, in_class)
            elif isinstance(child, ast.ClassDef):
                classes += 1
                visit(child, True)
            else:
                visit(child, in_class)

    visit(tree, False)
    return functions, classes, methods


def _scan_tree(root: Path) -> _ScanState:
    state = _ScanState()
    gi_patterns = _load_gitignore_patterns(root)
    stack: list[tuple[Path, str, int]] = [(root, "", 0)]

    while stack:
        current, rel_base, depth = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda e: e.name)
        except OSError as exc:
            state.warnings.append(f"Unreadable directory skipped: {rel_base or '.'} ({exc})")
            continue

        for entry in entries:
            if entry.is_symlink():
                continue  # never follow symlinks while scanning
            rel = f"{rel_base}/{entry.name}" if rel_base else entry.name

            if entry.is_dir():
                if entry.name in config.IGNORED_DIRS:
                    continue
                if any(_gitignore_match(p, d, rel, True) for p, d in gi_patterns):
                    continue
                if depth + 1 > config.MAX_DEPTH:
                    state.depth_exceeded = True
                    continue
                stack.append((entry, rel, depth + 1))
                continue

            if not entry.is_file():
                continue
            if state.file_count >= config.MAX_FILES:
                state.file_cap_reached = True
                break
            if any(_gitignore_match(p, d, rel, False) for p, d in gi_patterns):
                continue

            try:
                size = entry.stat().st_size
            except OSError:
                continue
            state.total_bytes += size
            if state.total_bytes > config.MAX_TOTAL_SIZE_BYTES:
                state.size_cap_reached = True
                break

            ext = entry.suffix.lower()
            category = _classify(rel, entry.name, ext)
            lines = _count_lines(entry, size, state)
            language = config.SOURCE_EXTENSIONS.get(ext)
            is_code = category in ("source", "test")

            state.total_lines += lines
            if is_code:
                state.source_lines += lines
                if language:
                    state.lang_files[language] = state.lang_files.get(language, 0) + 1
                    state.lang_lines[language] = state.lang_lines.get(language, 0) + lines

            if ext == ".py" and is_code:
                state.has_python = True
                try:
                    tree = ast.parse(entry.read_text(encoding="utf-8", errors="replace"))
                    f, c, m = _count_python_defs(tree)
                    state.py_functions += f
                    state.py_classes += c
                    state.py_methods += m
                except (SyntaxError, ValueError):
                    state.warnings.append(f"Python file could not be parsed: {rel}")

            state.files.append(ProjectFile(
                path=rel, language=language, category=category,
                size_bytes=size, lines=lines,
            ))
            state.file_count += 1

        if state.file_cap_reached or state.size_cap_reached:
            break

    if state.depth_exceeded:
        state.warnings.append(
            f"Maximum directory depth ({config.MAX_DEPTH}) exceeded; deeper entries were skipped."
        )
    if state.file_cap_reached:
        state.warnings.append(
            f"Maximum file count ({config.MAX_FILES}) reached; scan truncated."
        )
    if state.size_cap_reached:
        state.warnings.append(
            f"Size limit reached (per-file {config.MAX_FILE_SIZE_BYTES} bytes / "
            f"total {config.MAX_TOTAL_SIZE_BYTES} bytes); some content was skipped."
        )
    return state


# --- Detection helpers ---------------------------------------------------------

def _find_manifests(files: list[ProjectFile]) -> dict[str, ProjectFile]:
    by_name = {f.path.rsplit("/", 1)[-1]: f for f in files}
    return {name: by_name[name] for name in config.DEPENDENCY_MANIFESTS if name in by_name}


def _read_text(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _count_packages(root: Path, manifests: dict[str, ProjectFile], warnings: list[str]) -> tuple[int | None, dict[str, str]]:
    total: int | None = None
    details: dict[str, str] = {}

    def add(count: int | None, label: str, key: str) -> None:
        nonlocal total
        details[key] = label
        if count is not None:
            total = (total or 0) + count

    if "requirements.txt" in manifests:
        text = _read_text(root, manifests["requirements.txt"].path)
        if text is not None:
            n = sum(1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#"))
            add(n, f"{n} requirements", "requirements.txt")

    if "pyproject.toml" in manifests:
        text = _read_text(root, manifests["pyproject.toml"].path)
        if text is not None:
            try:
                data = tomllib.loads(text)
                deps = list(data.get("project", {}).get("dependencies") or [])
                opt = data.get("project", {}).get("optional-dependencies") or {}
                for group in opt.values():
                    deps.extend(group or [])
                add(len(deps), f"{len(deps)} PEP 621 dependencies", "pyproject.toml")
            except tomllib.TOMLDecodeError as exc:
                warnings.append(f"pyproject.toml could not be parsed: {exc}")

    if "Pipfile" in manifests:
        text = _read_text(root, manifests["Pipfile"].path)
        if text is not None:
            try:
                data = tomllib.loads(text)
                n = len(data.get("packages") or {}) + len(data.get("dev-packages") or {})
                add(n or None, f"{n} Pipfile packages", "Pipfile")
            except tomllib.TOMLDecodeError as exc:
                warnings.append(f"Pipfile could not be parsed: {exc}")

    if "pom.xml" in manifests:
        text = _read_text(root, manifests["pom.xml"].path)
        if text is not None:
            n = text.count("<dependency>")
            add(n or None, f"{n} Maven dependencies", "pom.xml")

    for gradle in ("build.gradle", "build.gradle.kts"):
        if gradle in manifests:
            text = _read_text(root, manifests[gradle].path)
            if text is not None:
                n = sum(1 for ln in text.splitlines() if _GRADLE_DEP_RE.match(ln))
                add(n or None, f"{n} Gradle dependencies", gradle)

    if "package.json" in manifests:
        text = _read_text(root, manifests["package.json"].path)
        if text is not None:
            try:
                data = json.loads(text)
                n = len(data.get("dependencies") or {}) + len(data.get("devDependencies") or {})
                add(n or None, f"{n} npm packages", "package.json")
            except json.JSONDecodeError as exc:
                warnings.append(f"package.json could not be parsed: {exc}")

    return total, details


def _detect_frameworks(root: Path, files: list[ProjectFile], manifests: dict[str, ProjectFile]) -> list[str]:
    frameworks: list[str] = []
    manifest_names = set(manifests)

    manifest_text = ""
    for name in ("requirements.txt", "pyproject.toml", "setup.cfg", "Pipfile"):
        if name in manifest_names:
            t = _read_text(root, manifests[name].path) if name in manifests else None
            if t:
                manifest_text += t.lower() + "\n"
    for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        if name in manifest_names:
            t = _read_text(root, manifests[name].path)
            if t:
                manifest_text += t.lower() + "\n"

    py_test_files = [f for f in files if f.path.endswith(".py") and f.category == "test"]

    if ("pytest" in manifest_text
            or any(f.path.rsplit("/", 1)[-1] in {"conftest.py", "pytest.ini"} for f in files)):
        frameworks.append("pytest")
    if py_test_files and any(
        (content := _read_text(root, f.path)) and _UNITTEST_IMPORT_RE.search(content)
        for f in py_test_files[:200]
    ):
        frameworks.append("unittest")

    if "junit" in manifest_text:
        frameworks.append("JUnit")
    if "testng" in manifest_text:
        frameworks.append("TestNG")

    pkg_json = _read_text(root, manifests["package.json"].path) if "package.json" in manifests else None
    if pkg_json:
        low = pkg_json.lower()
        for fw in ("jest", "vitest", "mocha"):
            if f'"{fw}"' in low:
                frameworks.append(fw.capitalize())

    return frameworks


def _detect_endpoints(root: Path, files: list[ProjectFile]) -> tuple[list[DetectedEndpoint], bool]:
    endpoints: list[DetectedEndpoint] = []
    truncated = False
    source_files = [f for f in files if f.category in ("source", "test")]

    for pf in source_files:
        if len(endpoints) >= config.MAX_ENDPOINTS:
            truncated = True
            break
        content = _read_text(root, pf.path)
        if not content:
            continue

        if pf.path.endswith(".py"):
            for m in _PY_API_RE.finditer(content):
                line = content.count("\n", 0, m.start()) + 1
                endpoints.append(DetectedEndpoint(
                    method=m.group(1).upper(), path=m.group(2),
                    source_file=pf.path, line=line,
                ))
        elif pf.path.endswith(".java"):
            for m in _JAVA_API_RE.finditer(content):
                path_match = _JAVA_PATH_RE.search(m.group(2))
                line = content.count("\n", 0, m.start()) + 1
                endpoints.append(DetectedEndpoint(
                    method=m.group(1).upper().replace("MAPPING", ""),
                    path=path_match.group(1) if path_match else "",
                    source_file=pf.path, line=line,
                ))
        elif pf.language in ("JavaScript", "TypeScript"):
            for m in _JS_API_RE.finditer(content):
                line = content.count("\n", 0, m.start()) + 1
                endpoints.append(DetectedEndpoint(
                    method=m.group(1).upper(), path=m.group(2),
                    source_file=pf.path, line=line,
                ))

        if len(endpoints) > config.MAX_ENDPOINTS:
            endpoints = endpoints[: config.MAX_ENDPOINTS]
            truncated = True

    return endpoints, truncated


def _classify_complexity(state: _ScanState, lang_count: int, packages: int | None) -> ComplexityInfo:
    reasons = [
        f"{state.file_count} total files",
        f"{sum(v for k, v in state.lang_files.items())} source/test code files",
        f"{state.source_lines} source lines",
        f"{lang_count} detected languages",
    ]
    if packages is not None:
        reasons.append(f"{packages} declared dependency packages")
    if state.has_python:
        reasons.append(
            f"{state.py_functions + state.py_methods} functions "
            f"({state.py_methods} methods), {state.py_classes} classes (Python)"
        )

    large = (state.file_count >= config.COMPLEXITY_LARGE_SOURCE_FILES
             or state.source_lines >= config.COMPLEXITY_LARGE_SOURCE_LINES)
    small = (state.file_count <= config.COMPLEXITY_SMALL_SOURCE_FILES
             and state.source_lines <= config.COMPLEXITY_SMALL_SOURCE_LINES)

    level = "Large" if large else ("Small" if small else "Medium")
    return ComplexityInfo(level=level, reasons=reasons)


# --- Public API -----------------------------------------------------------------

def profile_project(project_id: str, workspace: Path | None = None) -> ProjectProfile:
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    meta = ingestion.read_meta(ws, project_id)
    root = Path(meta.source_path) if meta.origin == "path" else ingestion.source_dir(ws, project_id)

    if not root.is_dir():
        raise ValueError(f"Project source is missing: {root}")

    state = _scan_tree(root)

    if state.file_count == 0:
        state.warnings.append("No files found to profile.")

    code_lines = sum(state.lang_lines.values())
    languages = sorted(
        (
            LanguageStatistics(
                name=lang,
                files=state.lang_files[lang],
                source_lines=state.lang_lines[lang],
                percentage=round(state.lang_lines[lang] * 100.0 / code_lines, 1)
                if code_lines else 0.0,
            )
            for lang in state.lang_files
        ),
        key=lambda s: (-s.source_lines, s.name),
    )

    categories = [f.category for f in state.files]
    metrics = ProjectMetrics(
        total_files=state.file_count,
        source_files=categories.count("source"),
        test_files=categories.count("test"),
        documentation_files=categories.count("documentation"),
        configuration_files=categories.count("configuration"),
        other_files=categories.count("other"),
        total_lines=state.total_lines,
        source_lines=state.source_lines,
        functions=(state.py_functions + state.py_methods) if state.has_python else None,
        classes=state.py_classes if state.has_python else None,
        methods=state.py_methods if state.has_python else None,
    )
    if not state.has_python and any(l in ("Java", "JavaScript", "TypeScript") for l in state.lang_files):
        state.warnings.append(
            "Advanced syntax metrics (functions/classes) are unavailable for "
            "Java/JavaScript/TypeScript in this milestone; only Python AST analysis is supported."
        )

    test_files = [f for f in state.files if f.category == "test"]
    doc_files = [f for f in state.files if f.category == "documentation"]
    manifests = _find_manifests(state.files)
    packages, dep_details = _count_packages(root, manifests, state.warnings)
    frameworks = _detect_frameworks(root, state.files, manifests)
    endpoints, truncated = _detect_endpoints(root, state.files)
    if truncated:
        state.warnings.append(
            f"API endpoint detection capped at {config.MAX_ENDPOINTS} endpoints."
        )

    complexity = _classify_complexity(state, len(languages), packages)

    included_files: list[ProjectFile] | None = state.files
    if state.file_count > config.MAX_PROFILE_FILE_LIST:
        included_files = None
        state.warnings.append(
            f"File listing omitted ({state.file_count} files > "
            f"{config.MAX_PROFILE_FILE_LIST})."
        )

    return ProjectProfile(
        project_id=project_id,
        name=meta.name,
        origin=meta.origin,
        created_at=datetime.now(timezone.utc),
        languages=languages,
        metrics=metrics,
        tests=ExistingTestInfo(
            files=len(test_files),
            frameworks=frameworks,
            example_files=[f.path for f in test_files[:20]],
        ),
        documentation=DocumentationInfo(
            files=len(doc_files),
            paths=[f.path for f in doc_files[:50]],
        ),
        dependencies=DependencyInfo(
            manifests=sorted(manifests.keys()),
            packages_detected=packages,
            details=dep_details,
        ),
        api=ApiInfo(endpoints_detected=len(endpoints), endpoints=endpoints),
        complexity=complexity,
        warnings=state.warnings,
        files=included_files,
    )
