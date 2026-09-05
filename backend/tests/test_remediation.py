"""Remediation guard tests for the first M10 audit findings (F1-F4).

These tests exist to (a) lock in the fixes and (b) protect against regression:

- F1: coverage data/JSON are written to the in-container /tmp tmpfs, never to
  the read-only /tests or /source mounts.
- F2: mutant classification is returncode-aware and parses *real* pytest -v
  output (including the trailing `[ NN%]` progress column). Non-zero exit codes
  (2/3/4/5 = collection/import/usage/internal/no-tests) are never classed as
  killed. An end-to-end pipeline test proves killed_count > 0 using real
  pytest subprocess output behind a Docker-boundary test double.
- F3: the only place that builds `docker run` argv is app.execution.runner
  (the M6 runner); sandbox.py is gone and every M10 measurement component
  executes through the shared runner with the M6 security flags.
- F4: bare `pytest` (testpaths=tests) must not collect workspace test files.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import config
from app.evaluation import mutation as mut
from app.evaluation.coverage import _COVERAGE_CMD
from app.execution.runner import DockerUnavailable, SandboxCommandResult, run_sandboxed_command
from app.models.evaluation import (
    EVAL_COMPLETED,
    MUTANT_ERROR,
    MUTANT_KILLED,
    MUTANT_SURVIVED,
    MUTANT_TIMEOUT,
)

# ── F1 / F2: helpers ─────────────────────────────────────────────────

def _real_pytest_run(files, cwd_root=None):
    """Run real pytest on a temp project; return (returncode, stdout, stderr)."""
    root = Path(cwd_root) if cwd_root else Path(
        tempfile.mkdtemp(prefix="realpytest_")
    )
    try:
        for name, text in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        cmd = [sys.executable, "-m", "pytest", "-v", "--no-header",
               "-p", "no:cacheprovider", "-p", "no:randomly"]
        res = subprocess.run(
            cmd, capture_output=True, cwd=str(root), timeout=120,
            env={**os.environ, "PYTHONPATH": str(root)},
        )
        return res.returncode, res.stdout.decode(errors="replace"), res.stderr.decode(errors="replace")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _host_pytest_backed_double(pid, source_root, test_dir, entrypoint, args,
                               timeout=None, memory_limit=None, cpu_limit=None,
                               image=None):
    """Stand-in for the Docker boundary that runs pytest on the host instead.

    Mirrors what the container executes: tests copied at test_dir run against
    the (mutated) source at source_root via PYTHONPATH. Returns real pytest
    bytes so the classifier is exercised on genuine output.
    """
    res = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-p", "no:randomly"],
        capture_output=True, cwd=str(test_dir), timeout=120,
        env={**os.environ, "PYTHONPATH": str(source_root)},
    )
    return SandboxCommandResult(
        returncode=res.returncode,
        stdout=res.stdout.decode(errors="replace"),
        stderr=res.stderr.decode(errors="replace"),
        duration_seconds=0.1,
        timed_out=False,
    )


# ── F1: coverage command writes only to /tmp ────────────────────────

class TestCoverageCommandPaths:
    def test_coverage_data_and_json_live_in_tmp(self):
        assert "COVERAGE_FILE=/tmp/.coverage" in _COVERAGE_CMD
        assert "coverage run" in _COVERAGE_CMD
        assert "-o /tmp/cov.json" in _COVERAGE_CMD
        assert "cat /tmp/cov.json" in _COVERAGE_CMD

    def test_no_writable_targets_on_ro_mounts(self):
        # No `coverage ... xxx` form may target /tests or /source, and no plain
        # `.coverage` data file may be written to the working directory.
        assert "/tests/" not in _COVERAGE_CMD.replace("cd /tests", "")
        assert "/source" not in _COVERAGE_CMD.replace("--source=/source", "")
        assert "COVERAGE_FILE" in _COVERAGE_CMD  # env-var form, not cwd default

    def test_run_coverage_forwards_fixed_command(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "app.py").write_text("x=1")
        tdir = tmp_path / "gen"
        tdir.mkdir()
        from app.evaluation import coverage as cov
        with patch("app.evaluation.coverage.run_sandboxed_command") as m:
            m.return_value = SandboxCommandResult(0, "{}", "", 0.5, False)
            cov.run_coverage(src, tdir, "p1")
        entrypoint, args = m.call_args.args[3], m.call_args.args[4]
        assert entrypoint == ["/bin/sh"]
        assert args[0] == "-c"
        assert "/tmp/.coverage" in args[1]
        assert "-o /tmp/cov.json" in args[1]


# ── F2: returncode-aware classification ─────────────────────────────

class TestClassifyMutantReturncodes:
    def test_zero_rc_withper_test_lines_survived(self):
        out = "tests/test_app.py::test_add PASSED [ 50%]\n1 passed in 0.1s\n"
        s, r = mut.classify_mutant(out, False, returncode=0)
        assert s == MUTANT_SURVIVED

    def test_rc1_with_failed_line_killed(self):
        out = "tests/test_app.py::test_add FAILED [100%]\n1 failed in 0.1s\n"
        s, r = mut.classify_mutant(out, False, returncode=1)
        assert s == MUTANT_KILLED

    def test_rc1_but_no_failed_line_is_error(self):
        # Exit 1 with no parseable FAILED line must never be classed killed.
        s, r = mut.classify_mutant("some pytest failure\n", False, returncode=1)
        assert s == MUTANT_ERROR

    def test_rc1_with_error_line_is_error(self):
        s, r = mut.classify_mutant("tests/test_app.py::test_x ERROR [100%]\n1 error\n",
                                   False, returncode=1)
        assert s == MUTANT_ERROR

    def test_collection_and_suite_exit_codes_never_killed(self):
        out = "ERROR tests/test_app.py - ImportError: No module named 'nope'\n"
        for rc in (2, 3, 4, 5):
            s, r = mut.classify_mutant(out, False, returncode=rc)
            assert s == MUTANT_ERROR, f"rc={rc} must be error, got {s}"

    def test_timeout_wins_over_everything(self):
        s, r = mut.classify_mutant("", True, returncode=0)
        assert s == MUTANT_TIMEOUT

    def test_legacy_no_returncode_still_works(self):
        # Existing callers / unit data without an explicit returncode keep the
        # old line-based behavior.
        assert mut.classify_mutant("tests/test_a.py::t FAILED\n", False)[0] == MUTANT_KILLED
        assert mut.classify_mutant("tests/test_a.py::t PASSED\n", False)[0] == MUTANT_SURVIVED
        assert mut.classify_mutant("tests/test_a.py ERROR\n", False)[0] == MUTANT_ERROR


class TestClassifyMutantRealPytestOutput:
    """Classification must agree with genuinely produced pytest output."""

    @pytest.mark.parametrize("body,expected_kind", [
        ("def test_x():\n    assert True\n", MUTANT_SURVIVED),
        ("def test_x():\n    assert False\n", MUTANT_KILLED),
    ])
    def test_real_pass_and_fail(self, body, expected_kind):
        rc, out, err = _real_pytest_run({"test_m.py": body})
        assert rc == (0 if expected_kind == MUTANT_SURVIVED else 1)
        s, r = mut.classify_mutant(out, False, returncode=rc)
        assert s == expected_kind

    @pytest.mark.parametrize("body", [
        "import nonexistent_module_xyz\n",                       # import error
        "def broken(:\n    pass\n",                              # syntax error
        "import pytest\n"
        "@pytest.fixture\n"
        "def fx():\n    raise RuntimeError('boom')\n"
        "def test_x(fx):\n    pass\n",                           # setup ERROR
    ])
    def test_real_errors_never_killed(self, body):
        rc, out, err = _real_pytest_run({"test_m.py": body})
        s, r = mut.classify_mutant(out, False, returncode=rc)
        assert s == MUTANT_ERROR
        assert s != MUTANT_KILLED

    def test_real_no_tests_collected_is_error(self):
        rc, out, err = _real_pytest_run({})
        assert rc == 5
        s, r = mut.classify_mutant(out, False, returncode=rc)
        assert s == MUTANT_ERROR


class TestMutationEndToEndKillsRealMutant:
    """Full pipeline: discover -> apply -> execute -> classify -> score, with
    real pytest output behind the Docker-boundary double. Must yield killed>0."""

    def test_killed_count_above_zero(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "app.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8")
        tdir = tmp_path / "gen"
        tdir.mkdir()
        (tdir / "test_app.py").write_text(
            "from app import add\n"
            "def test_add():\n    assert add(1, 1) == 2\n", encoding="utf-8")
        with patch("app.evaluation.mutation.run_sandboxed_command",
                   side_effect=_host_pytest_backed_double):
            r = mut.run_mutation(src, tdir, "p1", max_mutants=20)
        assert r.status == EVAL_COMPLETED
        assert r.killed > 0
        assert r.survived == 0
        assert r.mutation_score == 100.0


# ── F3: single Docker execution mechanism ───────────────────────────

def _source_modules():
    return sorted((config.BACKEND_DIR / "app").rglob("*.py"))


def test_only_runner_builds_docker_run_argv():
    """No module other than app.execution.runner may construct `docker run`."""
    def has_docker_run(text):
        toks = [
            t.string.strip("\"'") for t in tokenize.generate_tokens(
                io.StringIO(text).readline)
            if t.type == tokenize.STRING
        ]
        for i, v in enumerate(toks):
            if v == "docker" and i + 1 < len(toks) and toks[i + 1] == "run":
                return True
        return False

    offenders = []
    for path in _source_modules():
        if path.name == "runner.py":
            continue
        if has_docker_run(path.read_text(encoding="utf-8")):
            offenders.append(path)
    assert offenders == []


def test_sandbox_module_removed():
    assert not (config.BACKEND_DIR / "app" / "evaluation" / "sandbox.py").is_file()


def test_m10_components_use_shared_runner():
    for name in ("coverage", "mutation", "benchmark"):
        text = (config.BACKEND_DIR / "app" / "evaluation" / f"{name}.py").read_text(
            encoding="utf-8")
        assert "from app.execution.runner import" in text
        assert "run_sandboxed_command" in text


class TestRunSandboxedCommandSecurity:
    def test_exact_m6_security_flags(self, tmp_path):
        tdir = tmp_path / "gen"
        tdir.mkdir()
        src = tmp_path / "source"
        src.mkdir()
        (src / "app.py").write_text("x = 1\n")
        with patch("app.execution.runner._docker_available", return_value=True), \
             patch("app.execution.runner._ensure_image"), \
             patch("app.execution.runner.subprocess.run") as m:
            m.return_value = type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()
            res = run_sandboxed_command("p1", src, tdir, ["pytest"], ["-v"])
        assert res.returncode == 0
        argv = m.call_args.args[0]
        d = dict(zip(argv, argv[1:] + [""]))
        assert d["--name"] == "eval_p1"
        assert d["--network"] == "none"
        assert d["--read-only"] == "--tmpfs"
        assert d["--tmpfs"] == "/tmp:size=64m"
        assert d["--memory"].endswith("m")
        assert "--entrypoint" in argv and d["--entrypoint"] == "pytest"
        assert any(a.endswith(":/tests:ro") for a in argv)
        assert any(a.endswith(":/source:ro") for a in argv)
        assert "-e" in argv and d["-e"] == "PYTHONPATH=/source"

    def test_unavailable_raises(self, tmp_path):
        tdir = tmp_path / "gen"
        tdir.mkdir()
        with patch("app.execution.runner._docker_available", return_value=False):
            with pytest.raises(DockerUnavailable):
                run_sandboxed_command("p1", tmp_path / "source", tdir, ["pytest"], [])


# ── F4: bare pytest must not collect workspace tests ────────────────

def test_pytest_config_testpaths():
    ini = (config.BACKEND_DIR / "pytest.ini").read_text(encoding="utf-8")
    assert "testpaths" in ini
    assert "tests" in ini


def test_bare_pytest_does_not_collect_workspace_tests(tmp_path):
    """Bare `pytest` from backend must collect only tests/, never
    workspace/**/generated_tests (duplicate test_app.py basenames otherwise
    cause import-file-mismatch collection errors)."""
    ws_proj = config.BACKEND_DIR / "workspace" / "e2e_guard_proj"
    gen = ws_proj / "generated_tests"
    gen.mkdir(parents=True)
    (gen / "test_app.py").write_text(
        "def test_workspace_polluter():\n    assert True\n", encoding="utf-8")
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            capture_output=True, cwd=str(config.BACKEND_DIR), timeout=180,
        )
    finally:
        shutil.rmtree(ws_proj, ignore_errors=True)
    combined = (res.stdout + res.stderr).decode(errors="replace")
    assert res.returncode == 0
    assert "import file mismatch" not in combined
    assert "e2e_guard_proj" not in combined
    assert "test_workspace_polluter" not in combined
    assert "collected" in combined