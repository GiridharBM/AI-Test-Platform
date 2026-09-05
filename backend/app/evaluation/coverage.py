"""Dynamic Python execution coverage (Milestone 10).

This is a *runtime* measurement of which source lines/branches are actually
exercised by the generated tests inside the sandbox. It is entirely separate
from the M3 static CoverageSummary (target-to-test mapping) and does not
modify or replace it.

Implementation notes:
- The established `coverage` package is the minimal tool that can measure
  dynamic line/branch coverage; there is no stdlib equivalent. It is installed
  in the sandbox image so measurement runs under the M6 security model rather
  than on the host.
- Branch data is reported only because the tool can produce it; when absent it
  is never fabricated.
- Coverage data files are written to /tmp (the container's writable tmpfs),
  never to the read-only /tests or /source mounts.
"""

import json
from pathlib import Path

from app.core import config
from app.execution.runner import DockerUnavailable, run_sandboxed_command
from app.models.evaluation import (
    EVAL_BLOCKED,
    EVAL_COMPLETED,
    EVAL_ERROR,
    EVAL_UNAVAILABLE,
    CoverageFile,
    CoverageResult,
)

# Inside the container: run pytest under coverage measuring the mounted source,
# then emit coverage's JSON summary to stdout. Test pass/fail is irrelevant to
# coverage measurement, so the pytest output is diverted to avoid polluting the
# parsable JSON on stdout.
# COVERAGE_FILE and the JSON target live in the in-container /tmp tmpfs: the
# /tests and /source mounts are read-only, so writing the default `.coverage`
# file into the working directory (/tests) would fail.
_COVERAGE_CMD = (
    "cd /tests && "
    "COVERAGE_FILE=/tmp/.coverage coverage run --branch --source=/source -m pytest -q -p no:cacheprovider "
    ">/tmp/pytest_out.txt 2>&1; "
    "COVERAGE_FILE=/tmp/.coverage coverage json -o /tmp/cov.json -q; "
    "cat /tmp/cov.json"
)


def _normalize(path: str) -> str:
    """Strip the in-container /source prefix to a project-relative path."""
    if path.startswith("/source/"):
        return path[len("/source/"):]
    return path


def parse_coverage_json(raw: str) -> tuple[
    list[CoverageFile], int, int, int, int, float | None
]:
    """Parse coverage.py's `coverage json` output into structured per-file data.

    Returns (files, line_total, line_covered, branch_total, branch_covered,
    branch_percentage). branch_percentage is None when branch data is absent.
    Raises ValueError when the payload is not usable coverage data.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("coverage data missing or malformed") from exc

    files_obj = data.get("files") or {}
    if not isinstance(files_obj, dict):
        raise ValueError("coverage data has no file map")

    files: list[CoverageFile] = []
    line_total = line_covered = branch_total = branch_covered = 0
    branch_possible = False

    for path in sorted(files_obj.keys()):
        info = files_obj[path]
        if not isinstance(info, dict):
            continue
        summary = info.get("summary") or {}
        bsum = info.get("summary_branches") or {}
        missing = info.get("missing_lines") or []
        executable = int(summary.get("num_statements") or 0)
        covered = int(summary.get("covered_lines") or 0)
        bt = int(bsum.get("num_branches") or 0)
        bc = int(bsum.get("covered_branches") or 0)
        pct = summary.get("percent_covered") or 0.0
        if bsum:
            branch_possible = True
        files.append(CoverageFile(
            file_path=_normalize(path),
            executable_lines=executable,
            covered_lines=covered,
            missing_lines=sorted(int(x) for x in missing),
            percentage=round(float(pct), 3),
            branch_total=bt,
            branch_covered=bc,
        ))
        line_total += executable
        line_covered += covered
        branch_total += bt
        branch_covered += bc

    if branch_possible and branch_total > 0:
        branch_percentage = round(branch_covered / branch_total * 100, 3)
    elif branch_possible:
        branch_percentage = 0.0
    else:
        branch_percentage = None

    return files, line_total, line_covered, branch_total, branch_covered, branch_percentage


def run_coverage(
    source_root: Path,
    test_dir: Path,
    project_id: str = "",
    timeout: int | None = None,
) -> CoverageResult:
    """Measure dynamic line/branch coverage of test execution in the sandbox."""
    if source_root is None or not source_root.is_dir():
        return CoverageResult(
            status=EVAL_BLOCKED,
            warnings=["No source directory to measure coverage against."],
        )
    if not test_dir.is_dir():
        return CoverageResult(
            status=EVAL_BLOCKED,
            warnings=["No generated tests to measure coverage with."],
        )

    timeout = timeout if timeout is not None else config.COVERAGE_TIMEOUT_SECONDS
    try:
        outcome = run_sandboxed_command(
            project_id, source_root, test_dir,
            ["/bin/sh"], ["-c", _COVERAGE_CMD],
            timeout=timeout,
        )
    except DockerUnavailable as exc:
        return CoverageResult(
            status=EVAL_UNAVAILABLE,
            warnings=[str(exc)],
        )

    if outcome.timed_out:
        return CoverageResult(
            status=EVAL_BLOCKED,
            warnings=[f"Coverage measurement timed out after {timeout}s."],
        )

    try:
        files, lt, lc, bt, bc, bp = parse_coverage_json(outcome.stdout)
    except ValueError as exc:
        return CoverageResult(
            status=EVAL_ERROR,
            warnings=["Coverage tool produced no usable data."],
            reasons=[str(exc)],
        )

    if not files and outcome.returncode not in (0, 1, 5):
        return CoverageResult(
            status=EVAL_ERROR,
            warnings=["Coverage measurement failed to produce results."],
        )

    pct = round(lc / lt * 100, 3) if lt > 0 else 0.0
    return CoverageResult(
        status=EVAL_COMPLETED,
        line_total=lt,
        line_covered=lc,
        line_percentage=pct,
        branch_total=bt,
        branch_covered=bc,
        branch_percentage=bp,
        files=files,
    )
