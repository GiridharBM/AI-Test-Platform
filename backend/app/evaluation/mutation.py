"""Bounded deterministic mutation testing (Milestone 10).

Determines whether the generated tests detect controlled behavioral mutations
of the project's Python source. Operates only on isolated temporary copies of
the source; the original source tree is never modified and no mutated source
is left behind.

Boundaries
----------
* Reuses the M6/Docker sandbox for every test execution (never on the host).
* Strict limits: EVALUATION_MAX_MUTANTS mutants, per-mutant timeout, and an
  overall wall-clock budget guard.
* Mutation score denominator = valid executable mutants (killed + survived);
  timeout/error mutants are excluded and the denominator is documented.
* Deterministic: sites are ordered by file path, line, column, operator; the
  same input always yields the same mutant set and order.
"""

import ast
import re
import shutil
import tempfile
import time
from pathlib import Path

from app.core import config
from app.execution.runner import DockerUnavailable, run_sandboxed_command
from app.models.evaluation import (
    EVAL_BLOCKED,
    EVAL_COMPLETED,
    EVAL_UNAVAILABLE,
    MUTANT_ERROR,
    MUTANT_KILLED,
    MUTANT_SURVIVED,
    MUTANT_TIMEOUT,
    Mutant,
    MutationResult,
)

# Operator mutation table: op_name -> (source_node_type_or_None, replacement).
# Boolean flip is handled specially on ast.Constant for bool values.

_BINARY_MUTATIONS = {
    "add_to_sub": (ast.Add, ast.Sub),
    "sub_to_add": (ast.Sub, ast.Add),
    "mult_to_div": (ast.Mult, ast.Div),
    "div_to_mult": (ast.Div, ast.Mult),
}

_COMPARISON_MUTATIONS = {
    "eq_to_ne": (ast.Eq, ast.NotEq),
    "ne_to_eq": (ast.NotEq, ast.Eq),
    "lt_to_ge": (ast.Lt, ast.GtE),
    "ge_to_lt": (ast.GtE, ast.Lt),
    "gt_to_le": (ast.Gt, ast.LtE),
    "le_to_gt": (ast.LtE, ast.Gt),
}


def _iter_source_files(source_root: Path):
    """Yield (relative_posix_path, text) for Python files, deterministically."""
    if not source_root.is_dir():
        return
    files = []
    for path in source_root.rglob("*.py"):
        parts = path.relative_to(source_root).parts
        if any(part in config.IGNORED_DIRS for part in parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files.append((path.relative_to(source_root).as_posix(), text))
    for rel, text in sorted(files, key=lambda x: x[0]):
        yield rel, text


def discover_mutation_sites(source_text: str) -> list[tuple[int, int, int, str]]:
    """Return ordered (line, col, op_index, op_name) mutation sites."""
    tree = ast.parse(source_text)
    sites: list[tuple[int, int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            for name, (src_op, _dst) in _BINARY_MUTATIONS.items():
                if isinstance(node.op, src_op):
                    sites.append((node.lineno, node.col_offset, 0, name))
        elif isinstance(node, ast.Compare):
            for idx, op in enumerate(node.ops):
                for name, (src_op, _dst) in _COMPARISON_MUTATIONS.items():
                    if isinstance(op, src_op):
                        # Comparison operators lack position; use the Compare
                        # node's position plus the operator's index.
                        sites.append((node.lineno, node.col_offset, idx, name))
        elif isinstance(node, ast.AugAssign):
            for name, (src_op, _dst) in _BINARY_MUTATIONS.items():
                if isinstance(node.op, src_op):
                    sites.append((node.lineno, node.col_offset, 0, f"{name}_aug"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            sites.append((node.lineno, node.col_offset, 0, "bool_flip"))
    return sites


class _MutantReplacer(ast.NodeTransformer):
    """Applies one operator mutation at the first matching (line, col, op_index)."""

    def __init__(self, line: int, col: int, op_index: int, op_name: str):
        self.line = line
        self.col = col
        self.op_index = op_index
        self.op_name = op_name
        self.applied = False

    def _match(self, lineno, col_offset):
        return lineno == self.line and col_offset == self.col and not self.applied

    def visit_BinOp(self, node):
        if self.op_index == 0 and self.op_name in _BINARY_MUTATIONS:
            base = _BINARY_MUTATIONS[self.op_name]
            if (
                self._match(node.lineno, node.col_offset)
                and isinstance(node.op, base[0])
            ):
                node.op = base[1]()
                self.applied = True
        return self.generic_visit(node)

    def visit_AugAssign(self, node):
        base = _BINARY_MUTATIONS.get(self.op_name[:-4]) if self.op_name.endswith("_aug") else None
        if (
            self.op_index == 0
            and self._match(node.lineno, node.col_offset)
            and base
            and isinstance(node.op, base[0])
        ):
            node.op = base[1]()
            self.applied = True
        return self.generic_visit(node)

    def visit_Compare(self, node):
        new_ops = []
        for idx, op in enumerate(node.ops):
            base = _COMPARISON_MUTATIONS.get(self.op_name)
            if (
                idx == self.op_index
                and self._match(node.lineno, node.col_offset)
                and base
                and isinstance(op, base[0])
            ):
                new_ops.append(base[1]())
                self.applied = True
            else:
                new_ops.append(op)
        node.ops = new_ops
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if (
            self.op_index == 0
            and self.op_name == "bool_flip"
            and isinstance(node.value, bool)
            and self._match(node.lineno, node.col_offset)
        ):
            node.value = not node.value
            self.applied = True
        return self.generic_visit(node)


def apply_mutation(source_text: str, line: int, col: int, op_index: int, op_name: str) -> str | None:
    """Apply a single mutation. Returns new source text, or None if the site
    is no longer present (e.g. line numbers drifted)."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return None
    replacer = _MutantReplacer(line, col, op_index, op_name)
    new_tree = replacer.visit(tree)
    if not replacer.applied:
        return None
    return ast.unparse(new_tree)


# pytest emits a trailing progress column on per-test lines in verbose mode,
# e.g. `test_app.py::test_add FAILED [ 50%]`. The classifier must tolerate it.
_RESULT_LINE_RE = re.compile(
    r"::\S+\s+(PASSED|FAILED|ERROR|SKIPPED)(?:\s*\[\s*\d+%\])?\s*$"
)

# Per-mutant runs use -v so pytest emits per-test outcome lines that the
# classifier can parse from real output (not just exit codes).
_PYTEST_ARGS = ["-v", "--no-header", "--tb=short", "-p", "no:cacheprovider"]


def _count_pytest_results(stdout: str) -> tuple[int, int, int, int]:
    """Count per-test PASSED/FAILED/ERROR/SKIPPED lines in pytest output.

    Tolerant of the `[ NN%]` progress column real pytest appends in verbose
    mode. Also accepts the short `path ERROR`/`path FAILED` forms used in
    legacy/example output.
    """
    passed = failed = errors = skipped = 0
    for raw in stdout.splitlines():
        line = raw.rstrip()
        m = _RESULT_LINE_RE.search(line)
        if m:
            kind = m.group(1)
            if kind == "PASSED":
                passed += 1
            elif kind == "FAILED":
                failed += 1
            elif kind == "ERROR":
                errors += 1
            else:
                skipped += 1
        elif "::" not in line and line.endswith((" PASSED", " FAILED", " ERROR", " SKIPPED")):
            if line.endswith(" PASSED"):
                passed += 1
            elif line.endswith(" FAILED"):
                failed += 1
            elif line.endswith(" ERROR"):
                errors += 1
            else:
                skipped += 1
    return passed, failed, errors, skipped


def classify_mutant(stdout: str, timed_out: bool, returncode: int | None = None) -> tuple[str, str]:
    """Classify a mutant outcome from a sandboxed test run.

    Relies on the pytest exit code as the primary signal, falling back to the
    parsed per-test lines only to distinguish *killed* from *error* when pytest
    exited with code 1. Collection, import, usage, internal-error, and
    no-tests exits (2/3/4/5) are never classified as killed: they cannot
    demonstrate the tests detecting the mutation.

    Returns (status, reason). Deterministic given identical inputs.
    """
    if timed_out:
        return MUTANT_TIMEOUT, "test execution timed out on the mutant"

    passed, failed, errors, skipped = _count_pytest_results(stdout)

    if returncode is not None:
        if returncode == 0:
            return MUTANT_SURVIVED, "all tests passed on the mutant"
        if returncode in (2, 3, 4, 5):
            return MUTANT_ERROR, f"pytest could not assess the mutant (exit code {returncode})"
        # returncode == 1: at least one test failed or errored.
        if failed > 0:
            return MUTANT_KILLED, "a test failed on the mutant"
        if errors > 0:
            return MUTANT_ERROR, "a test errored on the mutant"
        return MUTANT_ERROR, "pytest reported a failure but no FAILED/ERROR test line was parsed"

    if failed > 0:
        return MUTANT_KILLED, "a test failed on the mutant"
    if errors > 0:
        return MUTANT_ERROR, "test collection/error on the mutant"
    return MUTANT_SURVIVED, "all tests passed on the mutant"


def derive_mutation_summary(statuses: list[str]) -> MutationResult:
    """Derive a MutationResult from a list of per-mutant statuses."""
    killed = sum(1 for s in statuses if s == MUTANT_KILLED)
    survived = sum(1 for s in statuses if s == MUTANT_SURVIVED)
    timeout = sum(1 for s in statuses if s == MUTANT_TIMEOUT)
    error = sum(1 for s in statuses if s == MUTANT_ERROR)
    valid = killed + survived
    score = round(killed / valid * 100, 3) if valid > 0 else None
    reasons = [f"{killed} killed, {survived} survived, {timeout} timed out, {error} errored."]
    if not statuses:
        reasons = ["No valid mutants produced."]
    return MutationResult(
        status=EVAL_COMPLETED,
        total_mutants=len(statuses),
        killed=killed,
        survived=survived,
        timeout=timeout,
        error=error,
        valid_mutants=valid,
        mutation_score=score,
        reasons=reasons,
    )


def run_mutation(
    source_root: Path,
    test_dir: Path,
    project_id: str = "",
    max_mutants: int | None = None,
    timeout: int | None = None,
) -> MutationResult:
    """Run bounded mutation testing on an isolated copy of the source."""
    max_mutants = max_mutants if max_mutants is not None else config.EVALUATION_MAX_MUTANTS
    timeout = timeout if timeout is not None else config.MUTATION_TIMEOUT_SECONDS
    total_budget = config.EVALUATION_TOTAL_TIMEOUT_SECONDS

    if source_root is None or not source_root.is_dir():
        return MutationResult(
            status=EVAL_BLOCKED,
            warnings=["No source directory to mutate."],
        )
    if not test_dir.is_dir():
        return MutationResult(
            status=EVAL_BLOCKED,
            warnings=["No generated tests to run against mutants."],
        )

    # Deterministically collect sites across source files.
    candidates: list[tuple[str, int, int, int, str]] = []
    for rel, text in _iter_source_files(source_root):
        try:
            sites = discover_mutation_sites(text)
        except SyntaxError:
            continue
        for line, col, op_index, op in sites:
            candidates.append((rel, line, col, op_index, op))

    chosen = candidates[: max(0, max_mutants)]
    if not chosen:
        return MutationResult(
            status=EVAL_COMPLETED,
            total_mutants=0,
            valid_mutants=0,
            mutation_score=0.0,
            reasons=["No mutation sites found or mutation disabled."],
        )

    results: list[Mutant] = []
    deadline = time.monotonic() + max(1, total_budget)
    base = Path(tempfile.mkdtemp(prefix="mut_"))

    def _cleanup_dir(d):
        shutil.rmtree(d, ignore_errors=True)

    try:
        for idx, (rel, line, col, op_index, op) in enumerate(chosen):
            if time.monotonic() > deadline:
                results.append(Mutant(
                    id=f"mutant-{idx}-{op}-{line}",
                    file_path=rel, line=line, operator=op,
                    description=op, status=MUTANT_TIMEOUT,
                    reason="overall evaluation budget exceeded",
                ))
                continue
            mutant_src = base / f"mutant_{idx}"
            shutil.copytree(source_root, mutant_src)
            target = mutant_src / rel
            text = target.read_text(encoding="utf-8", errors="replace")
            new_text = apply_mutation(text, line, col, op_index, op)
            if new_text is None:
                _cleanup_dir(mutant_src)
                continue
            try:
                ast.parse(new_text)
            except SyntaxError:
                _cleanup_dir(mutant_src)
                continue
            target.write_text(new_text, encoding="utf-8")

            try:
                outcome = run_sandboxed_command(
                    project_id, mutant_src, test_dir,
                    ["pytest"], _PYTEST_ARGS,
                    timeout=timeout,
                )
            except DockerUnavailable as exc:
                _cleanup_dir(base)
                return MutationResult(
                    status=EVAL_UNAVAILABLE,
                    warnings=[str(exc)],
                )

            status, reason = classify_mutant(outcome.stdout, outcome.timed_out, outcome.returncode)
            results.append(Mutant(
                id=f"mutant-{idx}-{op}-{line}",
                file_path=rel, line=line, operator=op,
                description=op, status=status, reason=reason,
            ))
            _cleanup_dir(mutant_src)
    finally:
        _cleanup_dir(base)

    summary = derive_mutation_summary([m.status for m in results])
    summary.mutants = results
    if any(m.reason == "overall evaluation budget exceeded" for m in results):
        summary.warnings.append("Overall evaluation budget reached; some mutants not fully measured.")
    return summary
