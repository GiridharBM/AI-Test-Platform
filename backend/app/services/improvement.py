"""Deterministic generated-test improvement (Milestone 8).

Consumes a completed M7 DiagnosisResult plus the project's CodeMap and
generated tests (M5) and replaces safe scaffold placeholders with evidence-based
invocation logic:

    DiagnosisResult -> placeholder detection -> CodeMap linkage
        -> deterministic body generation -> atomic write to generated_tests/

Guarantees & boundaries
------------------------
* No code execution, no import of user modules, no network access.
* Only top-level functions with a known deterministic signature are improved.
  Classes/methods require instantiation and are therefore `blocked`
  (insufficient deterministic evidence to construct a valid instance).
* The improved body only verifies that the target is importable and callable
  with its declared signature. It NEVER fabricates a behavioral assertion
  (no `assert result == <invented value>`), never suppresses failures
  (`@skip`, `assert True`, catch-all except, deleting tests), and never
  weakens existing assertions.
* Writes ONLY under `workspace/{project_id}/generated_tests/` and only `*.py`.
  `source/` and `.meta/` are never written.
"""

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.models.codemap import SourceClass, SourceFunction
from app.models.diagnosis import (
    CATEGORY_EXCEPTION,
    DiagnosisFinding,
    DiagnosisResult,
)
from app.models.improvement import (
    CHANGE_BLOCKED,
    CHANGE_IMPROVED,
    CHANGE_NO_CHANGE,
    IMPROVE_BLOCKED,
    IMPROVE_IMPROVED,
    IMPROVE_NO_CHANGE,
    IMPROVE_PARTIAL,
    ImprovementChange,
    ImprovementResult,
)

_PLACEHOLDER_RE = re.compile(r"raise\s+NotImplementedError\(")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Path safety (generated-tests only)
# ---------------------------------------------------------------------------

def _safe_generated_rel_path(raw: str) -> str | None:
    """Return a safe posix path under generated_tests/ or None if unsafe."""
    if not raw or not raw.strip():
        return None
    if "\x00" in raw:
        return None
    if len(raw) > config.MAX_REL_PATH_LENGTH:
        return None
    cleaned = raw.replace("\\", "/").strip()
    if len(cleaned) > 1 and cleaned[1] == ":":
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts:
        return None
    if any(p == ".." for p in parts):
        return None
    if any(len(p) > 255 for p in parts):
        return None
    rel = "/".join(parts)
    if not rel.endswith(".py"):
        return None
    return rel


# ---------------------------------------------------------------------------
# CodeMap linkage
# ---------------------------------------------------------------------------

def _source_index(codemap) -> dict[str, SourceFunction | SourceClass]:
    idx: dict[str, SourceFunction | SourceClass] = {}
    if codemap is None:
        return idx
    for mod in codemap.source_modules:
        for fn in mod.functions:
            idx[fn.name] = fn
            idx[fn.qualified_name] = fn
        for cls in mod.classes:
            idx[cls.name] = cls
            idx[cls.qualified_name] = cls
            for meth in cls.methods:
                idx[meth.qualified_name] = meth
                idx[f"{cls.name}.{meth.name}"] = meth
    return idx


def _is_top_level_function(codemap, key: str) -> bool:
    """True only when `key` resolves to a top-level function (not method/class)."""
    for mod in codemap.source_modules:
        for fn in mod.functions:
            if fn.name == key or fn.qualified_name == key:
                return True
    return False


def _unique_top_level_by_name(codemap, name: str) -> SourceFunction | None:
    """Return the single top-level function whose bare name is `name`.

    Ambiguity is determined from the CodeMap's source modules directly (not
    from the collapsed name->entry index, which cannot represent two modules
    sharing the same bare name). Exactly one match resolves; zero or many are
    refused so an ambiguous name can never silently select a module.
    """
    if codemap is None:
        return None
    matches: list[SourceFunction] = []
    for mod in codemap.source_modules:
        for fn in mod.functions:
            if fn.name == name:
                matches.append(fn)
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_target(
    test_function: str,
    codemap,
    idx: dict[str, SourceFunction | SourceClass],
) -> tuple[str | None, SourceFunction | None]:
    """Resolve a finding's test function to a top-level source function.

    Exact CodeMap `test_mappings` are the primary (preferred) source of truth.
    The `test_`-prefix strip is only a fallback and requires EXACTLY one
    unambiguous top-level candidate — zero or multiple matches are rejected
    (never silently choose the first). Class/method targets require
    instantiation the deterministic core cannot safely attempt, so they are
    ineligible. Returns (qualified_name, SourceFunction) or (None, None).
    """
    if codemap is not None:
        for m in codemap.test_mappings:
            if m.test_function == test_function and m.source_target:
                tgt = idx.get(m.source_target)
                if tgt is not None and _is_top_level_function(codemap, m.source_target):
                    return m.source_target, tgt
    if test_function.startswith("test_"):
        key = test_function[len("test_"):]
        fn = _unique_top_level_by_name(codemap, key)
        if fn is not None and isinstance(fn, SourceFunction):
            return fn.qualified_name, fn
    return None, None


# ---------------------------------------------------------------------------
# Body generation
# ---------------------------------------------------------------------------

def _module_from_path(file_path: str) -> str:
    """Convert a project-relative source path to an importable module name."""
    cleaned = file_path.replace("\\", "/").lstrip("/")
    if cleaned.endswith(".py"):
        cleaned = cleaned[:-3]
    parts = [re.sub(r"[^A-Za-z0-9_]", "_", p) for p in cleaned.split("/")]
    tokens = []
    for part in parts:
        if not part:
            continue
        if part[0].isdigit():
            part = "_" + part
        tokens.append(part)
    return ".".join(tokens) if tokens else ""


def _case_type_value(case_type: str, description: str) -> str | None:
    """Return a deterministic value template ONLY when the TestPlan evidence
    fixes the exact literal (from its own edge-case description/case_type).

    No arbitrary/derived literals: if the plan does not pin the value, we
    return None so the caller blocks rather than inventing a value.
    """
    desc = (description or "").lower()
    if case_type == "none":
        return "None"
    if case_type == "empty":
        return '""'
    if case_type == "boolean":
        return "True"
    if case_type == "boundary" and "zero" in desc:
        return "0"
    # negative / overflow / "very long" describe a *kind*, not an exact
    # literal the improver is allowed to manufacture -> no value.
    return None


def _param_values(fn: SourceFunction, spec) -> list[str] | None:
    """Resolve a deterministic literal for EVERY positional parameter.

    Uses only the TestPlan's explicit edge-case evidence for that target.
    Returns None if any parameter lacks plan-pinned evidence, meaning the
    improver has no right to construct the call.
    """
    if spec is None or not getattr(spec, "edge_cases", None):
        return None
    by_param = {e.parameter: e for e in spec.edge_cases}
    values: list[str] = []
    for argname in fn.args:
        edge = by_param.get(argname)
        if edge is None:
            return None
        value = _case_type_value(edge.case_type, edge.description)
        if value is None:
            return None
        values.append(value)
    return values


def _function_body_lines(
    fn: SourceFunction, module: str, spec,
) -> list[str] | None:
    """Deterministic smoke-invocation body for a top-level function.

    Every argument literal comes from the TestPlan's explicit edge-case
    evidence. Never fabricates a value and never asserts a behavioral result.
    Returns None when no plan evidence exists to construct the call.
    """
    values = _param_values(fn, spec)
    if values is None:
        return None
    sym = fn.name
    args = ", ".join(values)
    if fn.is_async:
        call = f"await {sym}({args})"
    else:
        call = f"{sym}({args})"
    return [
        f"from {module} import {sym}",
        "",
        call,
    ]


def _find_main_test_func(content: str, target_name: str) -> str | None:
    """Return the main generated test function name for a source target.

    Generated files name the main test `test_<target>[_usage]` and edge helpers
    `test_<target>_edge_...`. This returns the first non-edge function whose name
    starts with `test_{target}` — the function whose scaffold we improve. Fully
    deterministic and independent of the pytest nodeid string in the diagnosis.
    """
    prefix = f"test_{target_name}"
    for m in re.finditer(r"^(?:async\s+def|def)\s+(test_[A-Za-z0-9_]+)\s*\(", content, re.M):
        name = m.group(1)
        if not name.startswith(prefix):
            continue
        remainder = name[len(prefix):]
        if remainder.startswith("_edge"):
            continue
        return name
    return None


def _apply_bodies(content: str, func_name: str, body_lines: list[str]) -> str:
    """Replace the target function's scaffold placeholder with the new body.

    Only the first `raise NotImplementedError(...)` inside `func_name`'s body is
    replaced, stopping at the next function/class at the same indentation
    (sibling edge-case helpers are left untouched).
    """
    body = "\n".join(body_lines)
    lines = content.split("\n")
    n = len(lines)
    out: list[str] = []
    i = 0
    while i < n:
        line = lines[i]
        stripped = line.lstrip()
        header = re.match(r"^(?:async\s+def|def)\s+([A-Za-z_]\w*)\s*\(", stripped)
        if header and header.group(1) == func_name:
            indent = line[: len(line) - len(stripped)]
            out.append(line)
            i += 1
            while i < n:
                cur = lines[i]
                cs = cur.lstrip()
                ch = re.match(r"^(?:async\s+def|def|class)\s+", cs)
                if ch and cur[: len(cur) - len(cs)] == indent:
                    break
                if _PLACEHOLDER_RE.search(cur) and "Scaffold generated by AI Test Platform" in cur:
                    for bl in body.split("\n"):
                        out.append(indent + "    " + bl)
                    i += 1
                    break
                out.append(cur)
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _diag_id(findings: list[DiagnosisFinding]) -> str:
    ids = sorted(f.finding_id for f in findings)
    return hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest()


def improve_project(
    project_id: str,
    workspace: Path | None = None,
) -> ImprovementResult:
    """Orchestrate deterministic test improvement from persisted .meta artifacts.

    Raises FileNotFoundError if the diagnosis result does not exist.
    """
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    ingestion.read_meta(ws, project_id)

    raw_diag = ingestion.read_diagnosis(ws, project_id)
    if raw_diag is None:
        raise FileNotFoundError("No diagnosis result. Run /diagnose first.")

    diagnosis = DiagnosisResult.model_validate_json(raw_diag)

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

    return improve_diagnosis(diagnosis, codemap, ws, project_id, test_plan=test_plan)


def improve_diagnosis(
    diagnosis: DiagnosisResult,
    codemap,
    gen_root: Path | None = None,
    project_id: str = "",
    test_plan=None,
) -> ImprovementResult:
    """Improve failing generated tests for a diagnosis against its codemap
    and (when available) the M4 TestPlan.

    `gen_root` (default config.WORKSPACE_DIR) is the generated-tests workspace.
    The diagnosed `test_file` is resolved only under
    `gen_root/{project_id}/generated_tests/` with `*.py`-only, path-safe logic.
    Argument literals are taken ONLY from the TestPlan's explicit edge-case
    evidence; a target without pinned evidence is `blocked`, never fabricated.
    """
    ws_root = gen_root if gen_root is not None else config.WORKSPACE_DIR
    gt_root = Path(ws_root) / project_id / "generated_tests"

    specs_by_target: dict = {}
    if test_plan is not None:
        for s in test_plan.specs:
            specs_by_target[s.target_qualified_name] = s

    idx = _source_index(codemap)
    changes: list[ImprovementChange] = []
    warnings: list[str] = []

    # Per-file improved bodies keyed by target name (resolved once from the code map).
    file_to_targets: dict[str, dict[str, list[str]]] = {}
    seen: set[str] = set()

    for finding in diagnosis.findings:
        if len(changes) >= config.IMPROVE_MAX_CHANGES:
            warnings.append("Stopped after IMPROVE_MAX_CHANGES.")
            break

        test_file = _safe_generated_rel_path(finding.test_file)

        # Non-placeholder / non-actionable categories cannot be repaired safely.
        if finding.category != CATEGORY_EXCEPTION or finding.exception_type != "NotImplementedError":
            changes.append(ImprovementChange(
                finding_id=finding.finding_id,
                test_file=finding.test_file,
                test_function=finding.test_function,
                status=CHANGE_BLOCKED,
                reason="finding is not a NotImplementedError scaffold placeholder; "
                       "deterministic regeneration cannot safely repair it",
            ))
            continue

        if test_file is None:
            changes.append(ImprovementChange(
                finding_id=finding.finding_id,
                test_file=finding.test_file,
                test_function=finding.test_function,
                status=CHANGE_BLOCKED,
                reason="unsafe or non-.py test path; refusing to write outside generated_tests/",
            ))
            continue

        finding_key = f"{test_file}::{finding.test_function}"
        if finding_key in seen:
            continue
        seen.add(finding_key)

        target_name, fn = _resolve_target(finding.test_function, codemap, idx)
        if target_name is None or not isinstance(fn, SourceFunction):
            changes.append(ImprovementChange(
                finding_id=finding.finding_id,
                test_file=finding.test_file,
                test_function=finding.test_function,
                status=CHANGE_BLOCKED,
                reason="insufficient evidence: no resolvable top-level source function "
                       "with a known signature (classes/methods are not deterministically improvable)",
            ))
            continue

        module = _module_from_path(fn.file_path)
        if not module:
            changes.append(ImprovementChange(
                finding_id=finding.finding_id,
                test_file=finding.test_file,
                test_function=finding.test_function,
                status=CHANGE_BLOCKED,
                reason="insufficient evidence: could not derive an importable module "
                       "from the source code map",
            ))
            continue

        spec = specs_by_target.get(fn.qualified_name)
        body_lines = _function_body_lines(fn, module, spec)
        if body_lines is None:
            changes.append(ImprovementChange(
                finding_id=finding.finding_id,
                test_file=finding.test_file,
                test_function=finding.test_function,
                status=CHANGE_BLOCKED,
                reason="insufficient evidence to construct deterministic test inputs",
            ))
            continue

        file_to_targets.setdefault(test_file, {})[target_name] = body_lines
        changes.append(ImprovementChange(
            finding_id=finding.finding_id,
            test_file=test_file,
            test_function=finding.test_function,
            status=CHANGE_IMPROVED,
            reason="replaced NotImplementedError scaffold with an import-and-invoke "
                   "body using TestPlan edge-case evidence "
                   "(no fabricated behavioral assertion)",
        ))
    # end loop

    # Apply all improved bodies to their files (deterministic file ordering).
    files_modified = 0
    for test_file in sorted(file_to_targets.keys()):
        if files_modified >= config.IMPROVE_MAX_TEST_FILES:
            warnings.append("Stopped writing after IMPROVE_MAX_TEST_FILES.")
            break
        target_path = gt_root / test_file
        if not _path_within(gt_root, target_path):
            for ch in changes:
                if ch.test_file == test_file and ch.status == CHANGE_IMPROVED:
                    ch.status = CHANGE_BLOCKED
                    ch.reason = "resolved path escapes generated_tests/ (symlink/path containment)"
            continue
        if not target_path.is_file():
            for ch in changes:
                if ch.test_file == test_file and ch.status == CHANGE_IMPROVED:
                    ch.status = CHANGE_BLOCKED
                    ch.reason = "generated test file not present on disk"
            continue
        try:
            original = target_path.read_text(encoding="utf-8")
        except OSError as exc:
            for ch in changes:
                if ch.test_file == test_file and ch.status == CHANGE_IMPROVED:
                    ch.status = CHANGE_BLOCKED
                    ch.reason = f"could not read generated test file: {exc}"
            continue

        improved = original
        applied_any = False
        for target_name in sorted(file_to_targets[test_file].keys()):
            func_name = _find_main_test_func(improved, target_name)
            if func_name is None:
                continue
            improved = _apply_bodies(improved, func_name, file_to_targets[test_file][target_name])
            applied_any = True
        if not applied_any or improved == original:
            for ch in changes:
                if ch.test_file == test_file and ch.status == CHANGE_IMPROVED:
                    ch.status = CHANGE_NO_CHANGE
                    ch.reason = "placeholder not found; no change applied"
            continue

        if len(improved.encode("utf-8")) > config.IMPROVE_MAX_TEST_BYTES:
            for ch in changes:
                if ch.test_file == test_file and ch.status == CHANGE_IMPROVED:
                    ch.status = CHANGE_BLOCKED
                    ch.reason = "improved file exceeds IMPROVE_MAX_TEST_BYTES"
            continue

        _atomic_write(target_path, improved)
        files_modified += 1
        for ch in changes:
            if ch.test_file == test_file and ch.status == CHANGE_IMPROVED:
                ch.before = original
                ch.after = improved

    improved_count = sum(1 for c in changes if c.status == CHANGE_IMPROVED)
    blocked_count = sum(1 for c in changes if c.status == CHANGE_BLOCKED)

    if not changes:
        status = IMPROVE_NO_CHANGE
    elif blocked_count == 0 and improved_count == 0:
        status = IMPROVE_NO_CHANGE  # every finding already improved / untouched
    elif blocked_count == 0:
        status = IMPROVE_IMPROVED
    elif improved_count == 0:
        status = IMPROVE_BLOCKED
    else:
        status = IMPROVE_PARTIAL

    return ImprovementResult(
        project_id=project_id or diagnosis.project_id,
        diagnosis_id=_diag_id(diagnosis.findings),
        created_at=_now(),
        status=status,
        changes=changes,
        files_modified=files_modified,
        warnings=warnings,
    )


def _atomic_write(path: Path, content: str) -> None:
    """Atomically write text under the generated-tests tree."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _path_within(root: Path, path: Path) -> bool:
    """True only when `path`'s fully-resolved (symlink-aware) location stays
    inside `root`. Defends the write path against a symlinked intermediate
    directory that would otherwise redirect a write outside generated_tests/.
    Works on both Windows and Linux via os.path.realpath.
    """
    try:
        root_real = os.path.realpath(str(root))
        target_real = os.path.realpath(str(path))
    except (OSError, ValueError):
        return False
    try:
        return Path(target_real).is_relative_to(Path(root_real))
    except (ValueError, OSError):
        return False
