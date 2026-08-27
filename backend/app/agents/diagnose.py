"""Deterministic failure diagnosis (Milestone 7).

Consumes a completed M6 TestExecutionResult plus the project's CodeMap and
TestPlan and produces a structured DiagnosisResult:

    Failure Extractor -> Failure Classifier -> Fingerprint -> CodeMap Linker
        -> Severity -> DiagnosisResult
            -> Optional local/private AI analysis -> PotentialBug

The deterministic pipeline is fully self-contained: no LLM, no code execution,
no import of user modules, no network access. Every path read from traceback /
execution output is treated as untrusted and validated against the project
before any filesystem use (diagnosis performs no filesystem reads on those
paths anyway — linkage is purely structural against persisted .meta artifacts).
"""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.models.diagnosis import (
    CATEGORY_ASSERTION,
    CATEGORY_COLLECTION_ERROR,
    CATEGORY_EXCEPTION,
    CATEGORY_IMPORT_ERROR,
    CATEGORY_SYNTAX_ERROR,
    CATEGORY_TIMEOUT,
    CATEGORY_UNKNOWN,
    DIAGNOSIS_FAILURES_DIAGNOSED,
    DIAGNOSIS_NO_EXECUTION,
    DIAGNOSIS_NO_FAILURES,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    DiagnosisFinding,
    DiagnosisResult,
    DiagnosisSummary,
    SourceLocation,
)
from app.models.execution import (
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_TIMEOUT,
    STATUS_UNAVAILABLE,
    TestExecutionResult,
)

# pytest -v result line: <file>::<func> PASSED|FAILED|ERROR (also SKIPPED/XFAIL)
_TEST_RESULT_RE = re.compile(
    r"^(?P<file>.+)::(?P<func>[^\s]+)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED)\s*$"
)
# Traceback section header from --tb=short: <6+ underscores> <id> <6+ underscores>
_SECTION_HEADER_RE = re.compile(r"^_{6,}\s*(?P<id>.+?)\s*_{6,}$")
# pytest "E   <ExceptionClass>: <message>" summary line.
_EXCEPTION_SUMMARY_RE = re.compile(r"^E\s+(?P<cls>[A-Za-z_][\w\.]*):\s*(?P<msg>.*)$")
# Frame line: <path>:<lineno>: in <func>
_FRAME_RE = re.compile(r"^(?P<path>.+?):(?P<lineno>\d+):(?:\d+)?\s+in\s+(?P<func>[\w.]+)$")

# Paths prefixes that are container/workspace-local and not project content.
_CONTAINER_PREFIXES = ("/tests/", "/tests", "/tmp/", "/tmp", "./", ".\\")
# Common non-project path markers that would indicate traversal or absolute access.
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def normalize_trace_path(raw: str) -> str | None:
    """Return a safe project-relative posix path from a traceback/execution path.

    Returns None when the path cannot be made safe (absolute, traversal, drive,
    or empty). Diagnosis never uses the returned value for filesystem access;
    it is used only as a structural key against persisted .meta artifacts.
    """
    if not raw:
        return None
    cleaned = raw.replace("\\", "/").strip()
    if _WINDOWS_DRIVE_RE.match(cleaned):
        cleaned = cleaned[2:]
    for prefix in _CONTAINER_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.lstrip("/")
    if not cleaned:
        return None
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts:
        return None
    if any(p == ".." for p in parts):
        return None
    if any(len(p) > 255 for p in parts):
        return None
    return "/".join(parts)


def _safe_basename(rel_path: str) -> str:
    """Return a normalized basename used for weak baseline linkage fallback."""
    n = rel_path.replace("\\", "/").rsplit("/", 1)[-1]
    return n if n else rel_path


def _stable_path_key(rel: str) -> str:
    """Stable fingerprint key: strip env/container/workspace roots only.

    Preserves project-relative directory structure so distinct files keep
    distinct keys (src/foo.py != tests/foo.py != nested/foo.py), while
    normalizing environment-specific mounts so the same file fingerprints the
    same regardless of host path (C:\\workspace\\foo.py, /tmp/workspace/foo.py
    and /tests/foo.py all reduce to foo.py).
    """
    n = rel.replace("\\", "/").strip()
    if _WINDOWS_DRIVE_RE.match(n):
        n = n[2:].lstrip("/")
    for prefix in _CONTAINER_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    # Collapse a leading workspace root leaf (C:\workspace, /tmp/workspace, /workspace).
    if n.startswith("workspace/"):
        n = n[len("workspace/"):]
    n = n.lstrip("/")
    return n


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_failed_tests(output: str) -> list[tuple[str, str, str]]:
    """Parse pytest -v progress lines into (rel_test_file, func, status).

    Only FAILED / ERROR entries are returned, in first-appearance order.
    """
    results: list[tuple[str, str, str]] = []
    for line in output.splitlines():
        m = _TEST_RESULT_RE.match(line.strip())
        if not m:
            continue
        status = m.group("status")
        if status not in ("FAILED", "ERROR"):
            continue
        rel_file = normalize_trace_path(m.group("file"))
        if rel_file is None:
            continue
        results.append((rel_file, m.group("func"), status.lower()))
    return results


def _parse_traceback_sections(output: str) -> list[dict]:
    """Split pytest short-traceback output into per-test sections."""
    sections: list[dict] = []
    current: list[str] = []
    current_id: str | None = None
    for line in output.splitlines():
        h = _SECTION_HEADER_RE.match(line)
        if h:
            if current_id is not None:
                sections.append({"id": current_id, "body": "\n".join(current)})
            current_id = h.group("id").replace("____", "").strip()
            current = []
        else:
            if current_id is not None:
                current.append(line)
    if current_id is not None:
        sections.append({"id": current_id, "body": "\n".join(current)})
    return sections


def _classify_exceptions(body: str) -> list[tuple[str, str]]:
    """Extract (exception_class, message) pairs from a traceback body."""
    pairs: list[tuple[str, str]] = []
    for line in body.splitlines():
        m = _EXCEPTION_SUMMARY_RE.match(line)
        if m:
            cls = m.group("cls")
            msg = m.group("msg").strip()
            pairs.append((cls, msg))
    return pairs


def _determine_category(exception_type: str) -> str:
    """Map an exception class name to a deterministic diagnosis category."""
    exc = (exception_type or "").lower()
    if "assertion" in exc:
        return CATEGORY_ASSERTION
    if "modulenotfound" in exc or exc == "importerror" or "import" in exc:
        return CATEGORY_IMPORT_ERROR
    if "syntax" in exc:
        return CATEGORY_SYNTAX_ERROR
    if "timeout" in exc:
        return CATEGORY_TIMEOUT
    return CATEGORY_EXCEPTION


def classify_failure(
    output: str,
    test_file: str,
    test_func: str,
) -> tuple[str, str, str, str]:
    """Classify a failing test into (category, exception_type, message, traceback).

    Uses the traceback section whose header best matches the failing test's
    function name; falls back to scanning the whole output for exception
    summary lines (reliable for import/syntax/collection errors that pytest
    reports outside a per-test FAILURES section). When no exception evidence
    exists, returns (unknown, "", "", "").
    """
    sections = _parse_traceback_sections(output)
    match_exprs = (test_func, f"{test_file}::{test_func}")
    picked_body: str | None = None
    for sec in sections:
        sid = (sec.get("id") or "").strip()
        if any(e and (e in sid or sid in e) for e in match_exprs if e):
            picked_body = sec.get("body", "")
            break
    if picked_body is None and sections:
        picked_body = sections[0].get("body", "")

    traceback = ""
    if picked_body:
        traceback = picked_body.strip()[: config.DIAGNOSIS_MAX_TRACEBACK_BYTES]
        pairs = _classify_exceptions(picked_body)
        if pairs:
            exc_type, msg = pairs[0]
            return _determine_category(exc_type), exc_type, msg, traceback
        assertion = _detect_assertion(picked_body)
        if assertion is not None:
            return CATEGORY_ASSERTION, "AssertionError", assertion, traceback

    # Fallback: scan the whole output for an exception summary line.
    global_pairs = _classify_exceptions(output)
    if global_pairs:
        exc_type, msg = global_pairs[0]
        return _determine_category(exc_type), exc_type, msg, traceback
    global_assertion = _detect_assertion(output)
    if global_assertion is not None:
        return CATEGORY_ASSERTION, "AssertionError", global_assertion, traceback
    return CATEGORY_UNKNOWN, "", "", traceback


# pytest "E   assert ..." lines (assertion rewrite repr, no ExceptionType: prefix).
_ASSERT_SUMMARY_RE = re.compile(r"^E\s+(assert\b.*)$")


def _detect_assertion(body: str) -> str | None:
    """Return the assertion expression text from an 'E   assert ...' line, or None."""
    for line in body.splitlines():
        m = _ASSERT_SUMMARY_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

def fingerprint(
    test_file: str,
    test_func: str,
    category: str,
    exception_type: str,
    message: str,
) -> str:
    """Stable deterministic fingerprint for a failure locus.

    Normalizes unstable values (paths -> basename, message whitespace) so the
    same logical failure yields the same fingerprint. No UUIDs, no timestamps.
    """
    norm_file = _stable_path_key(test_file)
    norm_msg = " ".join((message or "").split())
    canonical = "\x1f".join(
        [norm_file.lower(), (test_func or ""), category, exception_type, norm_msg]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

def severity_for(status: str, category: str) -> str:
    """Deterministic severity derived from execution status and category.

    Rules:
    - timeout / collection_error / syntax_error / import_error -> high
    - exception / assertion -> medium
    - unknown -> low
    """
    if status == "timeout" or category in {
        CATEGORY_TIMEOUT,
        CATEGORY_COLLECTION_ERROR,
        CATEGORY_SYNTAX_ERROR,
        CATEGORY_IMPORT_ERROR,
    }:
        return SEVERITY_HIGH
    if category in {CATEGORY_EXCEPTION, CATEGORY_ASSERTION}:
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


# ---------------------------------------------------------------------------
# CodeMap linkage (read-only, structural)
# ---------------------------------------------------------------------------

def _resolve_qualified_name(codemap, qualified_name: str):
    """Resolve a qualified name to (file_path, line_start, line_end) or None."""
    if not qualified_name:
        return None
    for mod in codemap.source_modules:
        if mod.functions:
            for func in mod.functions:
                if func.qualified_name == qualified_name:
                    return func.file_path, func.line_start, func.line_end
        if mod.classes:
            for cls in mod.classes:
                if cls.qualified_name == qualified_name:
                    return cls.file_path, cls.line_start, cls.line_end
                for method in cls.methods:
                    if method.qualified_name == qualified_name:
                        return method.file_path, method.line_start, method.line_end
    return None


def link_to_codemap(
    codemap,
    test_file: str,
    test_func: str,
    traceback: str,
) -> list[SourceLocation]:
    """Link a failing test to source locations via the CodeMap.

    Priority:
    1. Direct traceback file/line against a codemap source module (high conf).
    2. Via test_mappings: failing test -> source_target -> source location.
    3. Direct baseline match of the failing test file to a source module name.
    Returns an empty list when no reliable mapping exists (no invented data).
    """
    locations: list[SourceLocation] = []
    seen: set[str] = set()

    def _add(loc: SourceLocation) -> None:
        key = (loc.source_file, loc.line_start, loc.line_end, loc.qualified_name)
        if key not in seen:
            seen.add(key)
            locations.append(loc)

    # 1. Direct traceback evidence: <source_path>:<lineno>: in <func>
    if traceback:
        for line in traceback.splitlines():
            m = _FRAME_RE.match(line.strip())
            if not m:
                continue
            rel = normalize_trace_path(m.group("path"))
            if not rel:
                continue
            lineno = int(m.group("lineno"))
            func = m.group("func")
            rel_base = rel.replace("\\", "/").rsplit("/", 1)[-1]
            for mod in codemap.source_modules:
                mod_base = mod.path.replace("\\", "/").rsplit("/", 1)[-1]
                # Match exact project-relative path, or a shared basename
                # (strict within the same file), so container/abs prefixes that
                # we cannot reconstruct still resolve to the right source file.
                if mod.path != rel and rel_base != mod_base:
                    continue
                target = _symbol_at(codemap, mod.path, lineno, func)
                if target:
                    _add(SourceLocation(
                        source_file=target[0],
                        line_start=target[1],
                        line_end=target[2],
                        qualified_name=target[3],
                        confidence=0.9,
                    ))

    # 2. Via test_mappings.
    rel_file = normalize_trace_path(test_file) or test_file
    rel_base = rel_file.replace("\\", "/").rsplit("/", 1)[-1]
    for tm in codemap.test_mappings:
        # The failing generated test may live under a different relative base
        # than the codemap's source-tree test paths, so match on function name
        # (strongest signal) with a basename-aware file constraint.
        tm_base = tm.test_file.replace("\\", "/").rsplit("/", 1)[-1]
        func_ok = tm.test_function == test_func or test_func.endswith(tm.test_function)
        file_ok = tm.test_file == rel_file or tm_base == rel_base
        if not (func_ok and file_ok):
            continue
        if tm.method == "none":
            continue
        resolved = _resolve_qualified_name(codemap, tm.source_target)
        if resolved:
            _add(SourceLocation(
                source_file=resolved[0],
                line_start=resolved[1],
                line_end=resolved[2],
                qualified_name=tm.source_target,
                confidence=min(1.0, tm.confidence),
            ))

    # 3. Direct baseline match: test file name matches a source module.
    base = _safe_basename(rel_file).lower().replace("_test", "").replace("test_", "")
    if not base:
        base = _safe_basename(rel_file).lower()
    for mod in codemap.source_modules:
        if mod.path.replace("\\", "/").rsplit("/", 1)[-1].lower() == base:
            target = _symbol_at(codemap, mod.path, None, None)
            if target:
                _add(SourceLocation(
                    source_file=target[0],
                    line_start=target[1],
                    line_end=target[2],
                    qualified_name=target[3],
                    confidence=0.4,
                ))
            break

    return locations[:5]


def _symbol_at(codemap, file_path: str, lineno: int | None, func: str | None):
    """Return (file_path, line_start, line_end, qualified_name) best covering a line."""
    best = None
    for mod in codemap.source_modules:
        if mod.path != file_path:
            continue
        symbols: list[tuple[str, int, int]] = []
        for f in mod.functions:
            symbols.append((f.qualified_name, f.line_start, f.line_end))
            if f.qualified_name.rsplit(".", 1)[-1] == func:
                best = (file_path, f.line_start, f.line_end, f.qualified_name)
        for c in mod.classes:
            symbols.append((c.qualified_name, c.line_start, c.line_end))
            for m in c.methods:
                symbols.append((m.qualified_name, m.line_start, m.line_end))
        if best:
            return best
        if lineno is not None:
            for qn, ls, le in symbols:
                if ls <= lineno <= le:
                    return (file_path, ls, le, qn)
        if symbols:
            return (file_path, symbols[0][1], symbols[0][2], symbols[0][0])
        break
    return best


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _build_finding_id(category: str, test_file: str, test_func: str) -> str:
    digest = hashlib.sha256(
        "\x1f".join(
            [category, _stable_path_key(test_file).lower(), test_func]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"{category}-{digest}"


def diagnose_execution(
    execution: TestExecutionResult,
    codemap=None,
    test_plan=None,
) -> DiagnosisResult:
    """Run deterministic diagnosis over a TestExecutionResult (no AI)."""
    warnings: list[str] = []
    output = "\n".join([execution.stdout or "", execution.stderr or ""])

    if execution.overall_status in (STATUS_UNAVAILABLE,):
        warnings.append("Execution was unavailable; no failure analysis possible.")
        return DiagnosisResult(
            project_id=execution.project_id,
            created_at=_now(),
            overall_status=DIAGNOSIS_NO_EXECUTION,
            warnings=warnings,
        )

    if execution.overall_status == STATUS_TIMEOUT:
        finding = DiagnosisFinding(
            finding_id=_build_finding_id(CATEGORY_TIMEOUT, "execution", "timeout"),
            test_file="",
            test_function="(execution timeout)",
            status="timeout",
            failure_signature=fingerprint(
                "", "(execution timeout)", CATEGORY_TIMEOUT, "", ""),
            exception_type="TimeoutExpired",
            message="Execution timed out.",
            traceback="",
            category=CATEGORY_TIMEOUT,
            severity=severity_for("timeout", CATEGORY_TIMEOUT),
        )
        return DiagnosisResult(
            project_id=execution.project_id,
            created_at=_now(),
            overall_status=DIAGNOSIS_FAILURES_DIAGNOSED,
            findings=[finding],
            summary=_build_summary([finding], []),
            warnings=warnings,
        )

    if not execution.stdout and not execution.stderr:
        warnings.append("No output captured from execution; nothing to diagnose.")
        status = (
            DIAGNOSIS_NO_FAILURES
            if execution.overall_status == STATUS_PASSED
            else DIAGNOSIS_NO_EXECUTION
        )
        return DiagnosisResult(
            project_id=execution.project_id,
            created_at=_now(),
            overall_status=status,
            warnings=warnings,
        )

    failed = extract_failed_tests(output)
    findings: list[DiagnosisFinding] = []
    seen_keys: set[str] = set()

    for rel, func, status in failed:
        category, exc_type, message, traceback = classify_failure(output, rel, func)
        key = (rel, func)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        locations = link_to_codemap(codemap, rel, func, traceback) if codemap else []
        findings.append(DiagnosisFinding(
            finding_id=_build_finding_id(category, rel, func),
            test_file=rel,
            test_function=func,
            status=status,
            failure_signature=fingerprint(rel, func, category, exc_type, message),
            exception_type=exc_type,
            message=message,
            traceback=traceback,
            linked_locations=locations,
            category=category,
            severity=severity_for(status, category),
        ))
        if len(findings) >= config.DIAGNOSIS_MAX_FINDINGS:
            warnings.append(
                f"Finding count exceeded {config.DIAGNOSIS_MAX_FINDINGS}; truncated."
            )
            break

    # Collection errors are reported by pytest but may not appear as -v FAILED lines.
    if "ERROR collecting" in output or "error in collecting" in output:
        finding = DiagnosisFinding(
            finding_id=_build_finding_id(CATEGORY_COLLECTION_ERROR, "", ""),
            test_file="",
            test_function="(collection)",
            status="collection_error",
            failure_signature=fingerprint(
                "", "(collection)", CATEGORY_COLLECTION_ERROR, "", ""),
            exception_type="",
            message="Test collection failed.",
            traceback="",
            category=CATEGORY_COLLECTION_ERROR,
            severity=severity_for("error", CATEGORY_COLLECTION_ERROR),
        )
        findings.append(finding)

    # Cap the total list deterministically.
    findings = findings[: config.DIAGNOSIS_MAX_FINDINGS]
    findings.sort(key=lambda f: (f.test_file, f.test_function))

    if not findings:
        warnings.append("Execution reported no failing tests.")
    overall = DIAGNOSIS_FAILURES_DIAGNOSED if findings else DIAGNOSIS_NO_FAILURES

    return DiagnosisResult(
        project_id=execution.project_id,
        created_at=_now(),
        overall_status=overall,
        findings=findings,
        summary=_build_summary(findings, []),
        warnings=warnings,
    )


def _build_summary(findings: list[DiagnosisFinding], bugs: list) -> DiagnosisSummary:
    by_cat: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    linked = 0
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
        linked += len(f.linked_locations)
    return DiagnosisSummary(
        total_findings=len(findings),
        by_category=dict(sorted(by_cat.items())),
        by_severity=dict(sorted(by_sev.items())),
        linked_locations=linked,
        potential_bugs=len(bugs),
    )


def diagnose_project(
    project_id: str,
    workspace: Path | None = None,
) -> DiagnosisResult:
    """Orchestrate diagnosis for a project from its persisted .meta artifacts.

    Raises FileNotFoundError if the execution result does not exist. Runs the
    deterministic core and, if DIAGNOSIS_AI_ENABLED, appends local/private AI
    potential-bug analysis (never external).
    """
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    meta = ingestion.read_meta(ws, project_id)

    raw_exec = ingestion.read_execution(ws, project_id)
    if raw_exec is None:
        raise FileNotFoundError("No execution result. Run execute first.")

    execution = TestExecutionResult.model_validate_json(raw_exec)

    codemap = None
    raw_codemap = ingestion.read_codemap(ws, project_id)
    if raw_codemap:
        from app.models.codemap import CodeMap
        codemap = CodeMap.model_validate_json(raw_codemap)

    test_plan = None
    raw_plan = ingestion.read_test_plan(ws, project_id)
    if raw_plan:
        from app.models.test_plan import TestPlan
        test_plan = TestPlan.model_validate_json(raw_plan)

    result = diagnose_execution(execution, codemap, test_plan)

    if config.DIAGNOSIS_AI_ENABLED:
        # Optional local/private AI boundary. Must never touch the network.
        try:
            from app.agents import llm
            bug = llm.analyze(
                {
                    "project_id": project_id,
                    "execution": execution,
                    "findings": [f.model_dump() for f in result.findings],
                }
            )
            if bug is not None:
                result.potential_bugs.append(bug)
                result.summary.potential_bugs = len(result.potential_bugs)
        except Exception as exc:  # fail-safe: never break deterministic diagnosis
            result.warnings.append(f"Optional AI analysis unavailable: {exc}")

    return result
