"""Bounded source-code repair (Milestone 11).

Consumes a completed M9 re-test result (still-failing verdicts), generates
*evidence-supported* source-code repair candidates, validates each candidate
inside an isolated repair workspace using the existing M6 Docker runner
(single execution mechanism), and stops at the first passing candidate —
returning it as ``validated_pending_approval``. Only the explicit approval
endpoint may apply the validated candidate to the original source; afterwards
a final validation runs against the patched original source.

Guarantees & boundaries
-----------------------
* The autonomous repair loop NEVER modifies the original source. Candidate
  application happens exclusively inside a fresh temporary repair workspace
  (copied source + copied generated tests) destroyed after each attempt, so
  candidate N can never contaminate candidate N+1.
* No unlimited loop: at most REPAIR_MAX_ATTEMPTS (hard-capped
  REPAIR_MAX_ATTEMPTS_HARD_MAX) distinct candidates are validated. The loop
  stops immediately on a pass and stops early when no further
  evidence-supported candidate exists.
* Candidates are bounded and explainable: a deterministic operator-repair rule
  (binary ``return A op B`` bodies) fires only when the source function's own
  name / TestPlan suggests an operation family that contradicts the compiled
  operator. No invented behavior, no expected values, no assertion synthesis,
  no fabrication to satisfy a test.
* The same candidate is never executed twice (per-attempt candidate id set).
* Untrusted project code runs only inside the M6 Docker sandbox (no network,
  bounded memory/CPU/timeout, read-only mounts). M6 ``execute_tests`` is
  reused unchanged except for an optional read-only ``source_root`` override.
* Never commits, never pushes, never rewrites Git history.
"""

import hashlib
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.core import config
from app.models.execution import (
    STATUS_PASSED,
    STATUS_UNAVAILABLE,
    TestExecutionResult,
)
from app.models.repair import (
    APPLICATION_APPLIED,
    APPLICATION_NOT_APPLIED,
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    FINAL_VALIDATION_FAILED,
    FINAL_VALIDATION_NOT_RUN,
    FINAL_VALIDATION_PASSED,
    FINAL_VALIDATION_UNAVAILABLE,
    REPAIR_APPLIED,
    REPAIR_APPROVED,
    REPAIR_BLOCKED,
    REPAIR_FAILED,
    REPAIR_REJECTED,
    REPAIR_UNAVAILABLE,
    REPAIR_VALIDATED_PENDING_APPROVAL,
    REPAIR_VALIDATING,
    VALIDATION_FAILED,
    VALIDATION_PASSED,
    VALIDATION_UNAVAILABLE,
    FinalValidation,
    RepairAttempt,
    RepairCandidate,
    RepairResult,
)

# Simple binary arithmetic body: return <a> <op> <b>
_BINOP_BODY_RE = re.compile(r"^return\s+([A-Za-z_]\w*)\s*([+\-*/%])\s*([A-Za-z_]\w*)\s*$")

# Deterministic operator family evidence derived ONLY from the function's own
# name / TestPlan suggested test name (no invented expectations).
_OP_WORDS: dict[str, set[str]] = {
    "+": {"add", "addition", "sum", "plus"},
    "-": {"subtract", "subtraction", "sub", "minus", "difference"},
    "*": {"multiply", "multiplication", "mul", "product", "times"},
    "/": {"divide", "division", "div", "quotient", "ratio"},
}

_OPERATORS = set(_OP_WORDS.keys())
_OP_TO_ALIAS: dict[str, str] = {
    "+": "addition", "-": "subtraction", "*": "multiplication", "/": "division",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _candidate_id(file_path: str, line_no: int, after: str) -> str:
    canonical = "\x1f".join([file_path, str(line_no), after])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _parse_line_no(source_location: str) -> int | None:
    """Parse a "L<line>" source_location into a 1-based line number (or None)."""
    if not source_location:
        return None
    stripped = source_location.strip().upper()
    if stripped.startswith("L"):
        stripped = stripped[1:]
    try:
        line = int(stripped)
    except ValueError:
        return None
    return line if line >= 1 else None


def _resolve_source_file(source_root: Path, file_path: str) -> Path | None:
    """Resolve a project-relative source path only when it is a real, contained
    regular file inside `source_root`. Returns None on any escape/traversal."""
    if not file_path or not file_path.strip():
        return None
    if "\x00" in file_path:
        return None
    cleaned = file_path.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts) or any(len(p) > 255 for p in parts):
        return None
    if len(cleaned) > 1 and cleaned[1] == ":":
        return None
    try:
        root_real = os.path.realpath(str(source_root))
        target = os.path.realpath(str(source_root / Path(*parts)))
    except (OSError, ValueError):
        return None
    if not Path(target).is_relative_to(Path(root_real)):
        return None
    candidate = Path(target)
    if not candidate.is_file():
        return None
    return candidate


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree (no symlinks) for building an isolated workspace."""
    shutil.copytree(src, dst, symlinks=False)


# ---------------------------------------------------------------------------
# Candidate generation (bounded, evidence-supported)
# ---------------------------------------------------------------------------

def _detect_operand_family(fn_name: str, suggested_name: str) -> str | None:
    """Return the operation family operator ('+','-','*','/') implied by the
    function's own name / suggested test name, or None when no word matches."""
    tokens = "".join(ch if ch.isalnum() else " " for ch in f"{fn_name} {suggested_name}").lower().split()
    for op in _OPERATORS:
        if _OP_WORDS[op] & set(tokens):
            return op
    return None


def _generate_candidate(
    fn_name: str,
    fn_args: list[str],
    implied_op: str,
    line_no: int,
    before_line: str,
    current_op: str,
    a: str,
    b: str,
    file_path: str,
    rationale_source: str,
    confidence: float,
) -> RepairCandidate | None:
    """Build a single operator-repair candidate, or None when the body already
    matches the evidence (function is already correct — no candidate)."""
    if current_op == implied_op:
        return None
    indent = before_line[: len(before_line) - len(before_line.lstrip())]
    after_line = f"{indent}return {a} {implied_op} {b}"
    return RepairCandidate(
        candidate_id=_candidate_id(file_path, line_no, after_line.strip()),
        file_path=file_path,
        source_location=f"L{line_no}",
        operation=f"replace_us_op_{current_op}_with_{implied_op}",
        before=before_line.strip(),
        after=after_line.strip(),
        rationale=(
            f"{rationale_source} implies a {_OP_TO_ALIAS[implied_op]} operation "
            f"('{fn_name}'), but the body compiles '{current_op}'; repair aligns "
            f"the operator with the named operation family."
        ),
        confidence=confidence,
    )


def _generate_candidates_for_function(
    fn,
    suggested_test_name: str,
    source_file: Path,
    file_content: str,
) -> list[RepairCandidate]:
    """Generate candidate repairs for a single top-level binop function.

    Only the exact line whose (stripped) text matches a simple binary
    ``return A op B`` is considered. Evidence is the function's own name /
    suggested test name. Zero or one candidate is produced per function.
    """
    candidates: list[RepairCandidate] = []
    lines = file_content.split("\n")
    for line_no in range(fn.line_start, min(fn.line_end, len(lines)) + 1):
        text = lines[line_no - 1].strip()
        m = _BINOP_BODY_RE.match(text)
        if not m:
            continue
        a, op, b = m.group(1), m.group(2), m.group(3)
        if {a, b} != set(fn.args):
            continue
        implied = _detect_operand_family(fn.name, suggested_test_name)
        if implied is None:
            continue
        # Higher confidence when the evidence comes from the function's own name.
        own_name_evidence = _detect_operand_family(fn.name, "")
        if own_name_evidence is not None:
            confidence = 0.8
            rationale_source = "The function name"
        else:
            confidence = 0.6
            rationale_source = "The planned test name"
        candidate = _generate_candidate(
            fn_name=fn.name,
            fn_args=fn.args,
            implied_op=implied,
            line_no=line_no,
            before_line=lines[line_no - 1],
            current_op=op,
            a=a,
            b=b,
            file_path=fn.file_path,
            rationale_source=rationale_source,
            confidence=confidence,
        )
        if candidate is not None:
            candidates.append(candidate)
        break  # only the first (single) binop return statement in the span
    return candidates


# ---------------------------------------------------------------------------
# Repair workspace + candidate application
# ---------------------------------------------------------------------------

def _apply_candidate_to_text(content: str, candidate: RepairCandidate) -> tuple[str, bool]:
    """Apply a candidate's single-line replacement to source text.

    Returns (new_content, applied_ok). Only the exact line at the candidate's
    source_location whose stripped content equals candidate.before is replaced
    (preserving indentation). No other change is made.
    """
    line_no = _parse_line_no(candidate.source_location)
    if line_no is None:
        return content, False
    lines = content.split("\n")
    if line_no > len(lines):
        return content, False
    original = lines[line_no - 1]
    if original.strip() != candidate.before.strip():
        return content, False
    indent = original[: len(original) - len(original.lstrip())]
    lines[line_no - 1] = f"{indent}{candidate.after}"
    return "\n".join(lines), True


def _apply_candidate_to_file(path: Path, candidate: RepairCandidate) -> bool:
    content = path.read_text(encoding="utf-8")
    updated, ok = _apply_candidate_to_text(content, candidate)
    if not ok:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


class _RepairWorkspace:
    """Fresh isolated workspace for one candidate validation attempt.

    Layout:
        <tmp>/source/   copy of the project source with the candidate applied
        <tmp>/tests/    copy of the generated tests under validation

    Created per attempt and destroyed afterwards so candidates never
    contaminate one another.
    """

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="repair_"))
        self.source = self.root / "source"
        self.tests = self.root / "tests"

    def setup(
        self,
        source_root: Path,
        generated_test_dir: Path,
        candidates: list[RepairCandidate],
    ) -> str:
        """Populate the workspace: copy source+tests and apply candidates.

        Returns an error string on failure ('' on success). Only candidates
        that resolve to a contained file inside the copied source are applied.
        """
        _copy_tree(source_root, self.source)
        for cand in candidates:
            target = _resolve_source_file(self.source, cand.file_path)
            if target is None:
                return f"candidate {cand.candidate_id} resolved outside copied source"
            if not _apply_candidate_to_file(target, cand):
                return f"candidate {cand.candidate_id} did not match expected 'before'"
        if not generated_test_dir.is_dir():
            return "generated tests directory not found"
        _copy_tree(generated_test_dir, self.tests)
        return ""

    def destroy(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Validation (via the single M6 Docker execution mechanism)
# ---------------------------------------------------------------------------

def _validated_exec(*, test_dir: Path, project_id: str, source_root: Path) -> TestExecutionResult:
    from app.execution.runner import execute_tests

    return execute_tests(test_dir, project_id, source_root=source_root)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _max_attempts() -> int:
    clamped = max(1, min(int(config.REPAIR_MAX_ATTEMPTS), config.REPAIR_MAX_ATTEMPTS_HARD_MAX))
    return clamped


def _resolve_repair_targets(
    codemap, re_test_, diagnosis, suggested_names: dict[str, str],
):
    """Resolve still-failing test functions to their source functions.

    Uses the M8 deterministic naming grammar as the linkage contract so the
    same `test_<target>_basic` / `test_<target>_edge_...` names that caused the
    M8 remediation issue resolve deterministically here.
    """
    from app.services.improvement import _candidate_target_keys, _unique_top_level_by_name

    targeted: list = []
    seen: set[str] = set()
    comparisons = re_test_.comparisons if re_test_ is not None else []
    for comp in comparisons:
        if comp.verdict != "still_failing":
            continue
        found = False
        for key in _candidate_target_keys(comp.test_function):
            fn = _unique_top_level_by_name(codemap, key)
            if fn is not None and not hasattr(fn, "methods"):
                if fn.qualified_name not in seen:
                    seen.add(fn.qualified_name)
                    targeted.append(fn)
                found = True
                break
    return targeted


def repair_from_artifacts(
    diagnosis,
    codemap,
    test_plan,
    re_test,
    source_dir: Path,
    generated_test_dir: Path,
    project_id: str = "",
) -> RepairResult:
    """Run the bounded repair loop from in-memory artifacts.

    Returns a RepairResult; the original source is NEVER modified. Raises
    nothing for expected states (missing inputs surface as blocked reasons).
    """
    warnings: list[str] = []
    reasons: list[str] = []

    if codemap is None:
        return RepairResult(
            project_id=project_id, status=REPAIR_BLOCKED,
            retest_diagnosis_id=(re_test.diagnosis_id if re_test else ""),
            warnings=["CodeMap missing."],
            reasons=["repair blocked: no CodeMap evidence available."],
            created_at=_now(),
        )

    suggested_names: dict[str, str] = {}
    if test_plan is not None:
        for spec in test_plan.specs:
            suggested_names[spec.target_qualified_name] = spec.suggested_test_name

    # --- Resolve still-failing targets from M9 comparisons ---
    targets = _resolve_repair_targets(codemap, re_test, diagnosis, suggested_names)
    if not targets:
        return RepairResult(
            project_id=project_id, status=REPAIR_BLOCKED,
            retest_diagnosis_id=(re_test.diagnosis_id if re_test else ""),
            warnings=["No still-failing target resolvable from M9 re-test."],
            reasons=["no justified repair candidate exists (no resolvable still-failing target)."],
            created_at=_now(),
        )

    # --- Build the candidate pool (bounded + evidence-supported) ---
    pool: list[RepairCandidate] = []
    seen_cands: set[str] = set()
    for fn in sorted(targets, key=lambda f: (f.file_path, f.line_start)):
        source_file = _resolve_source_file(source_dir, fn.file_path)
        if source_file is None:
            warnings.append(f"source unreachable/unsafe for {fn.qualified_name}.")
            continue
        try:
            content = source_file.read_text(encoding="utf-8")
        except OSError as exc:
            warnings.append(f"could not read source for {fn.qualified_name}: {exc}")
            continue
        for cand in _generate_candidates_for_function(
            fn, suggested_names.get(fn.qualified_name, ""), source_file, content,
        ):
            if cand.candidate_id not in seen_cands:
                seen_cands.add(cand.candidate_id)
                pool.append(cand)

    if not pool:
        return RepairResult(
            project_id=project_id, status=REPAIR_BLOCKED,
            retest_diagnosis_id=(re_test.diagnosis_id if re_test else ""),
            warnings=["No evidence-supported repair candidate exists for still-failing targets."],
            reasons=["no justified candidate exists; refusing to invent arbitrary patches."],
            created_at=_now(),
        )

    # --- Bounded validation loop ---
    attempts: list[RepairAttempt] = []
    selected: RepairCandidate | None = None
    max_attempts = _max_attempts()
    tried: set[str] = set()
    unavailable = False

    # Deterministic order: confidence desc, then file/line for stability.
    pool.sort(key=lambda c: (-c.confidence, c.file_path, c.source_location))

    for attempt_no in range(1, max_attempts + 1):
        # Stop early when no further evidence-supported candidate remains.
        next_cand = next((c for c in pool if c.candidate_id not in tried), None)
        if next_cand is None:
            reasons.append("No additional evidence-supported candidate available; stopped early.")
            break

        tried.add(next_cand.candidate_id)
        workspace_obj = _RepairWorkspace()
        try:
            err = workspace_obj.setup(source_dir, generated_test_dir, [next_cand])
            if err:
                attempts.append(RepairAttempt(
                    attempt_number=attempt_no,
                    candidate_id=next_cand.candidate_id,
                    file_path=next_cand.file_path,
                    source_location=next_cand.source_location,
                    operation=next_cand.operation,
                    before=next_cand.before,
                    after=next_cand.after,
                    rationale=next_cand.rationale,
                    validation_status=VALIDATION_FAILED,
                    failure_reason=f"workspace setup failed: {err}",
                    created_at=_now(),
                ))
                continue
            exec_result = _validated_exec(
                test_dir=workspace_obj.tests, project_id=project_id,
                source_root=workspace_obj.source,
            )
        finally:
            workspace_obj.destroy()

        if exec_result.overall_status == STATUS_UNAVAILABLE:
            attempts.append(RepairAttempt(
                attempt_number=attempt_no,
                candidate_id=next_cand.candidate_id,
                file_path=next_cand.file_path,
                source_location=next_cand.source_location,
                operation=next_cand.operation,
                before=next_cand.before,
                after=next_cand.after,
                rationale=next_cand.rationale,
                validation_status=VALIDATION_UNAVAILABLE,
                execution_result=exec_result.model_dump(),
                failure_reason="Docker execution environment unavailable; candidate not validated.",
                created_at=_now(),
            ))
            unavailable = True
            break

        passed = (
            exec_result.overall_status == STATUS_PASSED
            and exec_result.summary.failed == 0
            and exec_result.summary.errors == 0
        )
        attempts.append(RepairAttempt(
            attempt_number=attempt_no,
            candidate_id=next_cand.candidate_id,
            file_path=next_cand.file_path,
            source_location=next_cand.source_location,
            operation=next_cand.operation,
            before=next_cand.before,
            after=next_cand.after,
            rationale=next_cand.rationale,
            validation_status=VALIDATION_PASSED if passed else VALIDATION_FAILED,
            execution_result=exec_result.model_dump(),
            failure_reason=(
                ""
                if passed else
                f"Candidate validation failed: overall={exec_result.overall_status}, "
                f"passed={exec_result.summary.passed}, failed={exec_result.summary.failed}, "
                f"errors={exec_result.summary.errors}."
            ),
            created_at=_now(),
        ))
        if passed:
            cand_for_result = next_cand.model_copy(update={"attempt_number": attempt_no})
            return RepairResult(
                project_id=project_id,
                status=REPAIR_VALIDATED_PENDING_APPROVAL,
                retest_diagnosis_id=(re_test.diagnosis_id if re_test else ""),
                attempts=attempts,
                selected_candidate=cand_for_result,
                approval_state=APPROVAL_PENDING,
                application_state=APPLICATION_NOT_APPLIED,
                warnings=warnings,
                reasons=[f"Candidate {cand_for_result.candidate_id} validated in attempt {attempt_no}."],
                created_at=_now(),
            )

        reasons.append(f"Attempt {attempt_no} failed; candidate {next_cand.candidate_id} rejected.")

    # --- Never reached a pass ---
    if unavailable:
        status = REPAIR_UNAVAILABLE
        reasons.append("repair blocked: Docker execution environment unavailable.")
    elif not attempts:
        status = REPAIR_BLOCKED
        reasons.append("no repair attempt could be prepared.")
    else:
        status = REPAIR_FAILED
        reasons.append("all evidence-supported candidates failed validation; source left untouched.")

    return RepairResult(
        project_id=project_id,
        status=status,
        retest_diagnosis_id=(re_test.diagnosis_id if re_test else ""),
        attempts=attempts,
        approval_state=APPROVAL_PENDING,
        application_state=APPLICATION_NOT_APPLIED,
        warnings=warnings,
        reasons=reasons,
        created_at=_now(),
    )


def repair_project(
    project_id: str,
    workspace: Path | None = None,
) -> RepairResult:
    """Orchestrate bounded source repair from persisted .meta artifacts.

    Reads M7 diagnosis, M3 CodeMap, M4 TestPlan, and M9 re-test result.
    Raises FileNotFoundError when a required artifact does not exist.
    The original source is never modified here.
    """
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    meta = ingestion.read_meta(ws, project_id)
    raw_diag = ingestion.read_diagnosis(ws, project_id)
    if raw_diag is None:
        raise FileNotFoundError("No diagnosis result. Run /diagnose first.")
    from app.models.diagnosis import DiagnosisResult
    diagnosis = DiagnosisResult.model_validate_json(raw_diag)

    raw_codemap = ingestion.read_codemap(ws, project_id)
    if raw_codemap is None:
        raise FileNotFoundError("No CodeMap result. Run /discover first.")
    from app.models.codemap import CodeMap
    codemap = CodeMap.model_validate_json(raw_codemap)

    test_plan = None
    raw_plan = ingestion.read_test_plan(ws, project_id)
    if raw_plan is not None:
        from app.models.test_plan import TestPlan
        test_plan = TestPlan.model_validate_json(raw_plan)

    raw_retest = ingestion.read_retest(ws, project_id)
    if raw_retest is None:
        raise FileNotFoundError("No re-test result. Run /retest first.")
    from app.models.retest import ReTestResult
    re_test = ReTestResult.model_validate_json(raw_retest)

    src_dir = Path(meta.source_path) if meta.origin == "path" else ingestion.source_dir(ws, project_id)
    result = repair_from_artifacts(
        diagnosis, codemap, test_plan, re_test,
        source_dir=src_dir,
        generated_test_dir=Path(ws) / project_id / "generated_tests",
        project_id=project_id,
    )
    ingestion.save_repair(ws, result.model_dump_json())
    return result


# ---------------------------------------------------------------------------
# Approval + application + final validation
# ---------------------------------------------------------------------------

_APPROVAL_REJECTED_SOURCE_CHANGED = "Original source changed since candidate validation; approval invalidated."


def _read_latest_repair(workspace: Path, project_id: str) -> RepairResult:
    from app.services import project_ingestion as ingestion

    raw = ingestion.read_repair(workspace, project_id)
    if raw is None:
        raise FileNotFoundError("No repair result. Run /repair first.")
    return RepairResult.model_validate_json(raw)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def approve_repair(
    project_id: str,
    workspace: Path | None = None,
) -> RepairResult:
    """Explicit human approval: apply the validated candidate to original source.

    Applies ONLY the exact validated patch after verifying candidate state,
    application state, source existence/containment, and that the original
    source content still matches the candidate's expected ``before``. Refuses
    to overwrite newer user changes. Runs final validation afterwards.
    """
    from app.services import project_ingestion as ingestion

    ws = workspace if workspace is not None else config.WORKSPACE_DIR
    meta = ingestion.read_meta(ws, project_id)
    result = _read_latest_repair(ws, project_id)

    # --- Checks 1 & 6: a validated candidate exists and is not superseded ---
    if result.status != REPAIR_VALIDATED_PENDING_APPROVAL or result.selected_candidate is None:
        result.status = REPAIR_REJECTED
        result.approval_state = APPROVAL_REJECTED
        result.reasons.append("No valid candidate pending approval; approval rejected.")
        ingestion.save_repair(ws, result.model_dump_json())
        return result

    candidate = result.selected_candidate

    # --- Check 2: candidate has not already been applied ---
    if result.application_state == APPLICATION_APPLIED:
        result.status = REPAIR_REJECTED
        result.approval_state = APPROVAL_REJECTED
        result.reasons.append("Candidate has already been applied; approval rejected.")
        ingestion.save_repair(ws, result.model_dump_json())
        return result

    # --- Checks 3 & 4: original source still exists, still contained ---
    source_root = Path(meta.source_path) if meta.origin == "path" else ingestion.source_dir(ws, project_id)
    source_file = _resolve_source_file(source_root, candidate.file_path)
    if source_file is None:
        result.status = REPAIR_REJECTED
        result.approval_state = APPROVAL_REJECTED
        result.reasons.append(
            "Original source file missing or escapes the project source root; approval rejected."
        )
        ingestion.save_repair(ws, result.model_dump_json())
        return result

    # --- Checks 5 & 7: original content still matches the validated 'before' ---
    line_no = _parse_line_no(candidate.source_location)
    if line_no is None:
        result.status = REPAIR_REJECTED
        result.approval_state = APPROVAL_REJECTED
        result.reasons.append("Candidate source location is malformed; approval rejected.")
        ingestion.save_repair(ws, result.model_dump_json())
        return result
    try:
        current_lines = source_file.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        result.status = REPAIR_REJECTED
        result.approval_state = APPROVAL_REJECTED
        result.reasons.append(f"Could not read original source for approval: {exc}")
        ingestion.save_repair(ws, result.model_dump_json())
        return result
    if line_no > len(current_lines) or current_lines[line_no - 1].strip() != candidate.before.strip():
        result.status = REPAIR_REJECTED
        result.approval_state = APPROVAL_REJECTED
        result.reasons.append(_APPROVAL_REJECTED_SOURCE_CHANGED)
        ingestion.save_repair(ws, result.model_dump_json())
        return result

    # --- Apply exactly the validated patch ---
    result.status = REPAIR_APPROVED
    result.approval_state = APPROVAL_APPROVED
    try:
        full_text = source_file.read_text(encoding="utf-8")
        updated, ok = _apply_candidate_to_text(full_text, candidate)
        if not ok:
            raise RuntimeError("candidate 'before' no longer matches the source line")
        _atomic_write(source_file, updated)
    except Exception as exc:  # never corrupt the source
        result.status = REPAIR_FAILED
        result.approval_state = APPROVAL_REJECTED
        result.reasons.append(f"Could not apply the validated patch: {exc}")
        ingestion.save_repair(ws, result.model_dump_json())
        return result

    result.application_state = APPLICATION_APPLIED
    result.status = REPAIR_APPLIED

    # --- Final validation against the patched original source ---
    generated_test_dir = Path(ws) / project_id / "generated_tests"
    from app.execution.runner import execute_tests

    try:
        final_exec = execute_tests(generated_test_dir, project_id, source_root=source_root)
    except Exception as exc:  # application already persisted; never lose applied state
        result.final_validation = FinalValidation(
            status=FINAL_VALIDATION_UNAVAILABLE,
            reason=f"Final validation could not run: {exc}.",
        )
        result.reasons.append(f"Candidate applied but final validation could not run: {exc}")
        ingestion.save_repair(ws, result.model_dump_json())
        return result

    if final_exec.overall_status == STATUS_UNAVAILABLE:
        result.final_validation = FinalValidation(
            status=FINAL_VALIDATION_UNAVAILABLE,
            execution_result=final_exec.model_dump(),
            reason="Docker unavailable; final validation could not run.",
        )
        result.reasons.append("Candidate applied but final validation is unavailable.")
    elif (
        final_exec.overall_status == STATUS_PASSED
        and final_exec.summary.failed == 0
        and final_exec.summary.errors == 0
    ):
        result.final_validation = FinalValidation(
            status=FINAL_VALIDATION_PASSED,
            execution_result=final_exec.model_dump(),
            reason="Final validation passed against applied source.",
        )
        result.reasons.append("Candidate applied and final validation passed.")
    else:
        result.final_validation = FinalValidation(
            status=FINAL_VALIDATION_FAILED,
            execution_result=final_exec.model_dump(),
            reason=(
                f"Final validation failed: overall={final_exec.overall_status}, "
                f"failed={final_exec.summary.failed}, errors={final_exec.summary.errors}."
            ),
        )
        result.reasons.append("Candidate applied but final validation failed.")

    ingestion.save_repair(ws, result.model_dump_json())
    return result