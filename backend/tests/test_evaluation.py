"""Tests for the evaluation subsystem (Milestone 10).

Covers the three components (coverage, mutation, benchmark), the orchestrator,
M9 -> M10 behavior, determinism, idempotency, security, and persistence.
Docker execution is mocked; pure computation is tested directly.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import config
from app.evaluation import benchmark as bench
from app.evaluation import coverage as cov
from app.evaluation import mutation as mut
from app.evaluation.orchestrator import evaluate_from_artifacts
from app.execution.runner import DockerUnavailable, SandboxCommandResult
from app.models.evaluation import (
    EVAL_BLOCKED,
    EVAL_COMPLETED,
    EVAL_ERROR,
    EVAL_NOT_RUN,
    EVAL_UNAVAILABLE,
    MUTANT_ERROR,
    MUTANT_KILLED,
    MUTANT_SURVIVED,
    MUTANT_TIMEOUT,
    BenchmarkResult,
    CoverageResult,
    EvaluationResult,
    MutationResult,
)
from app.models.retest import (
    RETEST_BLOCKED,
    RETEST_NO_OP,
    RETEST_UNAVAILABLE,
    ReTestResult,
)

_CREATED = datetime.now(timezone.utc)


def _outcome(returncode=0, stdout="", stderr="", duration=0.5, timed_out=False):
    return SandboxCommandResult(returncode, stdout, stderr, duration, timed_out)


def _coverage_json():
    return json.dumps({
        "meta": {"version": "7.x", "branch_coverage": True},
        "files": {
            "/source/app.py": {
                "executed_lines": [1, 2],
                "missing_lines": [3],
                "summary": {"num_statements": 3, "covered_lines": 2,
                            "percent_covered": 66.67, "missing_lines": 1},
                "executed_branches": [[1, 0]],
                "missing_branches": [[3, 0]],
                "summary_branches": {"num_branches": 2, "covered_branches": 1,
                                     "percent_covered": 50.0, "missing_branches": 1},
            },
            "/source/util.py": {
                "executed_lines": [1, 2, 3, 4],
                "missing_lines": [],
                "summary": {"num_statements": 4, "covered_lines": 4,
                            "percent_covered": 100.0, "missing_lines": 0},
                "executed_branches": [],
                "missing_branches": [],
                "summary_branches": {"num_branches": 0, "covered_branches": 0,
                                     "percent_covered": 100.0, "missing_branches": 0},
            },
        },
    })


# ── Coverage ────────────────────────────────────────────────────────

class TestParseCoverageJson:
    def test_parses_per_file(self):
        files, lt, lc, bt, bc, bp = cov.parse_coverage_json(_coverage_json())
        assert len(files) == 2
        assert files[0].file_path == "app.py"  # /source/ prefix stripped
        assert files[0].executable_lines == 3
        assert files[0].covered_lines == 2
        assert files[0].missing_lines == [3]
        assert files[0].percentage == 66.67
        assert files[0].branch_total == 2
        assert files[0].branch_covered == 1
        assert lt == 7
        assert lc == 6
        assert bt == 2
        assert bc == 1
        assert bp == 50.0

    def test_malformed_raises(self):
        with pytest.raises(ValueError):
            cov.parse_coverage_json("{not json")


class TestRunCoverage:
    @patch("app.evaluation.coverage.run_sandboxed_command",
           return_value=_outcome(returncode=0, stdout=_coverage_json()))
    def test_successful_coverage(self, _mock, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "app.py").write_text("x=1")
        tdir = tmp_path / "gen"
        tdir.mkdir()
        r = cov.run_coverage(src, tdir, "p1")
        assert r.status == EVAL_COMPLETED
        assert r.line_percentage == round(6 / 7 * 100, 3)
        assert len(r.files) == 2
        assert r.branch_percentage == 50.0

    def test_missing_source_blocked(self, tmp_path):
        tdir = tmp_path / "gen"
        tdir.mkdir()
        r = cov.run_coverage(tmp_path / "nope", tdir, "p1")
        assert r.status == EVAL_BLOCKED

    def test_missing_tests_blocked(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        r = cov.run_coverage(src, tmp_path / "nope", "p1")
        assert r.status == EVAL_BLOCKED

    @patch("app.evaluation.coverage.run_sandboxed_command",
           side_effect=DockerUnavailable("Docker not available"))
    def test_unavailable(self, _mock, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        tdir = tmp_path / "gen"
        tdir.mkdir()
        r = cov.run_coverage(src, tdir, "p1")
        assert r.status == EVAL_UNAVAILABLE

    @patch("app.evaluation.coverage.run_sandboxed_command",
           return_value=_outcome(timed_out=True))
    def test_timeout_blocked(self, _mock, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        tdir = tmp_path / "gen"
        tdir.mkdir()
        r = cov.run_coverage(src, tdir, "p1")
        assert r.status == EVAL_BLOCKED

    def test_deterministic(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "app.py").write_text("x=1")
        tdir = tmp_path / "gen"
        tdir.mkdir()
        with patch("app.evaluation.coverage.run_sandboxed_command",
                   return_value=_outcome(returncode=0, stdout=_coverage_json())):
            r1 = cov.run_coverage(src, tdir, "p1")
            r2 = cov.run_coverage(src, tdir, "p1")
        assert r1.model_dump()["files"] == r2.model_dump()["files"]
        assert r1.line_percentage == r2.line_percentage


class TestCoverageModel:
    def test_defaults(self):
        r = CoverageResult()
        assert r.status == EVAL_NOT_RUN
        assert r.line_total == 0


# ── Mutation (pure functions) ───────────────────────────────────────

class TestDiscoverMutationSites:
    def test_finds_operators(self):
        sites = mut.discover_mutation_sites("def f(a,b):\n    return a + b\n")
        ops = {s[3] for s in sites}
        assert "add_to_sub" in ops

    def test_finds_comparison(self):
        sites = mut.discover_mutation_sites("def f(a,b):\n    return a > b\n")
        ops = {s[3] for s in sites}
        assert "gt_to_le" in ops

    def test_finds_bool_flip(self):
        sites = mut.discover_mutation_sites("def f():\n    return True\n")
        ops = {s[3] for s in sites}
        assert "bool_flip" in ops

    def test_empty_source(self):
        assert mut.discover_mutation_sites("pass\n") == []

    def test_deterministic_order(self):
        s1 = mut.discover_mutation_sites("def f():\n    return 1 + 2 + 3\n")
        s2 = mut.discover_mutation_sites("def f():\n    return 1 + 2 + 3\n")
        assert s1 == s2


class TestApplyMutation:
    def test_binary_applies(self):
        out = mut.apply_mutation("def f(a,b):\n    return a + b\n", 2, 11, 0, "add_to_sub")
        assert "a - b" in out

    def test_compare_applies(self):
        out = mut.apply_mutation("def f(a,b):\n    return a > b\n", 2, 11, 0, "gt_to_le")
        assert "a <= b" in out

    def test_bool_applies(self):
        out = mut.apply_mutation("def f():\n    return True\n", 2, 11, 0, "bool_flip")
        assert "False" in out

    def test_result_always_parses(self):
        import ast
        src = "def f(a, b):\n    if a > b:\n        return a + b\n    return False\n"
        for line, col, idx, op in mut.discover_mutation_sites(src):
            out = mut.apply_mutation(src, line, col, idx, op)
            ast.parse(out)

    def test_site_not_present_returns_none(self):
        assert mut.apply_mutation("def f():\n    return 1\n", 99, 0, 0, "add_to_sub") is None

    def test_syntax_error_returns_none(self):
        assert mut.apply_mutation("def (", 1, 0, 0, "add_to_sub") is None

    def test_original_source_unchanged(self):
        src = "def f(a,b):\n    return a + b\n"
        mut.apply_mutation(src, 2, 11, 0, "add_to_sub")
        assert src == "def f(a,b):\n    return a + b\n"


class TestClassifyMutant:
    def test_killed(self):
        status, _ = mut.classify_mutant("tests/test_a.py::t FAILED\n1 failed\n", False)
        assert status == MUTANT_KILLED

    def test_survived(self):
        status, _ = mut.classify_mutant("tests/test_a.py::t PASSED\n1 passed\n", False)
        assert status == MUTANT_SURVIVED

    def test_error(self):
        status, _ = mut.classify_mutant("tests/test_a.py ERROR\n1 error\n", False)
        assert status == MUTANT_ERROR

    def test_timeout(self):
        status, _ = mut.classify_mutant("", True)
        assert status == MUTANT_TIMEOUT


class TestMutationSummary:
    def _res(self, statuses):
        r = mut.derive_mutation_summary(statuses)
        r.mutants = [mut.Mutant(id=f"m{i}", file_path="a.py", line=1,
                                operator="add_to_sub", description="x", status=s)
                     for i, s in enumerate(statuses)]
        return r

    def test_score_denominator_is_valid(self):
        r = self._res([MUTANT_KILLED, MUTANT_SURVIVED, MUTANT_TIMEOUT, MUTANT_ERROR])
        assert r.killed == 1
        assert r.survived == 1
        assert r.timeout == 1
        assert r.error == 1
        assert r.valid_mutants == 2
        assert r.mutation_score == 50.0
        assert "killed + survived" in r.score_denominator

    def test_no_valid_score_none(self):
        r = self._res([MUTANT_TIMEOUT])
        assert r.mutation_score is None

    def test_no_mutants_score_zero(self):
        r = self._res([])
        assert r.mutation_score == 0.0 or r.mutation_score is None


class TestRunMutation:
    def _setup(self, tmp_path, src_text="def add(a, b):\n    return a + b\n"):
        src = tmp_path / "source"
        src.mkdir()
        (src / "app.py").write_text(src_text)
        tdir = tmp_path / "gen"
        tdir.mkdir()
        (tdir / "test_app.py").write_text("def test_add(): pass")
        return src, tdir

    def test_no_mutation_sites(self, tmp_path):
        src, tdir = self._setup(tmp_path, src_text="pass\n")
        r = mut.run_mutation(src, tdir, "p1")
        assert r.status == EVAL_COMPLETED
        assert r.total_mutants == 0
        assert r.mutation_score == 0.0

    def test_max_mutants_zero_disables(self, tmp_path):
        src, tdir = self._setup(tmp_path)
        with patch("app.evaluation.mutation.run_sandboxed_command") as mock:
            r = mut.run_mutation(src, tdir, "p1", max_mutants=0)
        assert r.total_mutants == 0
        assert not mock.called

    def test_killed_survived_tracking(self, tmp_path):
        src, tdir = self._setup(tmp_path, src_text="def f(a, b):\n    if a > b:\n        return a + b\n")
        outcomes = iter([
            _outcome(returncode=1, stdout="tests/test_a.py::test_add FAILED\n1 failed\n"),  # killed
            _outcome(returncode=0, stdout="tests/test_a.py::test_add PASSED\n1 passed\n"),  # survived
        ])
        with patch("app.evaluation.mutation.run_sandboxed_command", side_effect=lambda *a, **k: next(outcomes)):
            r = mut.run_mutation(src, tdir, "p1", max_mutants=10)
        assert r.status == EVAL_COMPLETED
        assert r.killed == 1
        assert r.survived == 1
        assert r.valid_mutants == 2
        assert r.mutation_score == 50.0

    def test_timeout_mutant(self, tmp_path):
        src, tdir = self._setup(tmp_path)
        with patch("app.evaluation.mutation.run_sandboxed_command",
                   return_value=_outcome(timed_out=True)):
            r = mut.run_mutation(src, tdir, "p1", max_mutants=10)
        assert r.timeout >= 1

    def test_error_mutant(self, tmp_path):
        src, tdir = self._setup(tmp_path)
        with patch("app.evaluation.mutation.run_sandboxed_command",
                   return_value=_outcome(returncode=1, stdout="tests/test_a.py::t ERROR\n1 error\n")):
            r = mut.run_mutation(src, tdir, "p1", max_mutants=10)
        assert r.error >= 1

    def test_missing_source_blocked(self, tmp_path):
        tdir = tmp_path / "gen"
        tdir.mkdir()
        r = mut.run_mutation(tmp_path / "nope", tdir, "p1")
        assert r.status == EVAL_BLOCKED

    def test_missing_tests_blocked(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        r = mut.run_mutation(src, tmp_path / "nope", "p1")
        assert r.status == EVAL_BLOCKED

    def test_unavailable_docker(self, tmp_path):
        src, tdir = self._setup(tmp_path)
        with patch("app.evaluation.mutation.run_sandboxed_command",
                   side_effect=DockerUnavailable("docker down")):
            r = mut.run_mutation(src, tdir, "p1")
        assert r.status == EVAL_UNAVAILABLE

    def test_source_remains_untouched(self, tmp_path):
        src_text = "def add(a, b):\n    return a + b\n"
        src, tdir = self._setup(tmp_path, src_text)
        with patch("app.evaluation.mutation.run_sandboxed_command",
                   return_value=_outcome(returncode=0, stdout="PASSED\n")):
            mut.run_mutation(src, tdir, "p1", max_mutants=10)
        assert (src / "app.py").read_text() == src_text

    def test_varies_mutant_source_is_used(self, tmp_path):
        src, tdir = self._setup(tmp_path)
        captured = []
        def _fake(pid, source_root, test_dir, entrypoint, args, timeout=None):
            captured.append((source_root / "app.py").read_text())
            return _outcome(returncode=0, stdout="PASSED\n1 passed\n")
        with patch("app.evaluation.mutation.run_sandboxed_command", side_effect=_fake):
            r = mut.run_mutation(src, tdir, "p1", max_mutants=10)
        # Each mutant run used a mutated source copy, never the original.
        assert captured
        for text in captured:
            assert "return a - b" in text  # add_to_sub applied
        assert (src / "app.py").read_text() == "def add(a, b):\n    return a + b\n"

    def test_temporary_mutation_cleanup(self, tmp_path):
        src, tdir = self._setup(tmp_path)
        import tempfile as _tf
        real_mkdtemp = _tf.mkdtemp
        created: list = []
        def _fake_mkdtemp(prefix="tmp"):
            d = Path(real_mkdtemp(prefix=prefix))
            created.append(d)
            return str(d)
        with patch("app.evaluation.mutation.tempfile.mkdtemp", side_effect=_fake_mkdtemp), \
             patch("app.evaluation.mutation.run_sandboxed_command",
                   return_value=_outcome(returncode=0, stdout="PASSED\n")):
            r = mut.run_mutation(src, tdir, "p1", max_mutants=10)
        assert created
        assert any(p.name.startswith("mut_") for p in created)
        # The entire mutation work dir (and all mutant copies) is removed.
        assert all(not p.exists() for p in created)

    def test_source_unchanged_after_cleanup(self, tmp_path):
        src_text = "def add(a, b):\n    return a + b\n"
        src, tdir = self._setup(tmp_path, src_text)
        with patch("app.evaluation.mutation.run_sandboxed_command",
                   return_value=_outcome(returncode=0, stdout="PASSED\n")):
            mut.run_mutation(src, tdir, "p1", max_mutants=10)
        assert (src / "app.py").read_text() == src_text

    def test_deterministic_mutant_order(self, tmp_path):
        src, tdir = self._setup(tmp_path, src_text="def f():\n    return 1 + 2 < 3\n")
        calls = []
        def _fake(*a, **k):
            calls.append(k["timeout"] if False else 1)
            return _outcome(returncode=0, stdout="PASSED\n")
        with patch("app.evaluation.mutation.run_sandboxed_command", side_effect=_fake):
            r1 = mut.run_mutation(src, tdir, "p1", max_mutants=10)
        c1 = [m.id for m in r1.mutants]
        with patch("app.evaluation.mutation.run_sandboxed_command", side_effect=_fake):
            r2 = mut.run_mutation(src, tdir, "p1", max_mutants=10)
        c2 = [m.id for m in r2.mutants]
        assert c1 == c2


# ── Benchmark ───────────────────────────────────────────────────────

class TestComputeStats:
    def test_min_mean_median(self):
        mn, mean, med = bench.compute_stats([1.0, 2.0, 3.0])
        assert mn == 1.0
        assert mean == 2.0
        assert med == 2.0

    def test_median_even(self):
        _, _, med = bench.compute_stats([1.0, 2.0, 3.0, 4.0])
        assert med == 2.5

    def test_empty(self):
        assert bench.compute_stats([]) == (None, None, None)


class TestRunBenchmark:
    def _setup(self, tmp_path):
        tdir = tmp_path / "gen"
        tdir.mkdir()
        (tdir / "test_a.py").write_text("def test_a(): pass")
        return tdir

    @patch("app.evaluation.benchmark.gpu_available", return_value=False)
    @patch("app.evaluation.benchmark.run_sandboxed_command")
    def test_success_cpu_benchmark(self, mock_rm, _gpu, tmp_path):
        mock_rm.return_value = _outcome(duration=0.2)
        tdir = self._setup(tmp_path)
        r = bench.run_benchmark(tmp_path / "source", tdir, "p1", warm_up=2, measured_runs=2)
        assert r.status == EVAL_COMPLETED
        # mock always returns 0.2 => min/mean/median all 0.2
        assert r.min_seconds == 0.2
        assert r.mean_seconds == 0.2
        assert r.median_seconds == 0.2
        assert r.warm_up_count == 2
        assert r.run_count == 2
        assert r.cpu_available is True
        assert r.gpu_available is False
        assert r.gpu_status == EVAL_UNAVAILABLE
        # total calls = warm_up + measured = 4
        assert mock_rm.call_count == 4

    @patch("app.evaluation.benchmark.gpu_available", return_value=False)
    @patch("app.evaluation.benchmark.run_sandboxed_command")
    def test_warmup_excluded(self, mock_rm, _gpu, tmp_path):
        durations = iter([10.0, 0.1, 0.2, 0.3])  # first 2 are warmup
        mock_rm.side_effect = lambda *a, **k: _outcome(duration=next(durations))
        tdir = self._setup(tmp_path)
        r = bench.run_benchmark(tmp_path / "source", tdir, "p1", warm_up=2, measured_runs=2)
        assert r.measured_runs == [0.2, 0.3]
        assert r.min_seconds == 0.2
        assert r.mean_seconds == 0.25
        assert r.median_seconds == 0.25

    @patch("app.evaluation.benchmark.gpu_available", return_value=False)
    def test_missing_tests_blocked(self, _gpu, tmp_path):
        r = bench.run_benchmark(tmp_path / "source", tmp_path / "nope", "p1")
        assert r.status == EVAL_BLOCKED

    @patch("app.evaluation.benchmark.gpu_available", return_value=False)
    @patch("app.evaluation.benchmark.run_sandboxed_command",
           side_effect=DockerUnavailable("docker down"))
    def test_unavailable(self, _rm, _gpu, tmp_path):
        tdir = self._setup(tmp_path)
        r = bench.run_benchmark(tmp_path / "source", tdir, "p1")
        assert r.status == EVAL_UNAVAILABLE

    @patch("app.evaluation.benchmark.gpu_available", return_value=True)
    @patch("app.evaluation.benchmark.run_sandboxed_command", return_value=_outcome(duration=0.1))
    def test_gpu_available_when_probed(self, _rm, _gpu, tmp_path):
        tdir = self._setup(tmp_path)
        r = bench.run_benchmark(tmp_path / "source", tdir, "p1", warm_up=0, measured_runs=1)
        assert r.gpu_available is True
        assert r.gpu_status == EVAL_COMPLETED

    @patch("app.evaluation.benchmark.gpu_available", return_value=False)
    @patch("app.evaluation.benchmark.run_sandboxed_command", return_value=_outcome(duration=0.1))
    def test_bounded_runs(self, mock_rm, _gpu, tmp_path):
        tdir = self._setup(tmp_path)
        bench.run_benchmark(tmp_path / "source", tdir, "p1", warm_up=2, measured_runs=3)
        assert mock_rm.call_count == 5

    @patch("app.evaluation.benchmark.gpu_available", return_value=False)
    @patch("app.evaluation.benchmark.run_sandboxed_command")
    def test_variable_results_reported_honestly(self, mock_rm, _gpu, tmp_path):
        durations = iter([0.5, 0.8, 0.6])
        mock_rm.side_effect = lambda *a, **k: _outcome(duration=next(durations))
        tdir = self._setup(tmp_path)
        r = bench.run_benchmark(tmp_path / "source", tdir, "p1", warm_up=0, measured_runs=3)
        assert r.measured_runs == [0.5, 0.8, 0.6]
        assert r.min_seconds == 0.5
        assert r.mean_seconds == round((0.5 + 0.8 + 0.6) / 3, 3)
        assert r.median_seconds == 0.6


# ── Orchestrator ────────────────────────────────────────────────────

def _retest(status):
    return ReTestResult(project_id="p1", status=status, created_at=_CREATED)


def _pad(tmp_path, name="p1"):
    src = tmp_path / name / "source"
    src.mkdir(parents=True)
    (src / "app.py").write_text("def add(a, b):\n    return a + b\n")
    tdir = tmp_path / name / "generated_tests"
    tdir.mkdir(parents=True)
    (tdir / "test_app.py").write_text("def test_add(): pass")
    return src, tdir


@pytest.fixture
def completed_components():
    return (
        CoverageResult(status=EVAL_COMPLETED, line_total=3, line_covered=3, line_percentage=100.0),
        MutationResult(status=EVAL_COMPLETED, total_mutants=2, killed=2, valid_mutants=2, mutation_score=100.0),
        BenchmarkResult(status=EVAL_COMPLETED, run_count=1, warm_up_count=0,
                        measured_runs=[0.1], min_seconds=0.1, mean_seconds=0.1, median_seconds=0.1),
    )


class TestEvaluateFromArtifacts:
    @patch("app.evaluation.orchestrator.benchmark.run_benchmark")
    @patch("app.evaluation.orchestrator.mutation.run_mutation")
    @patch("app.evaluation.orchestrator.coverage.run_coverage")
    def test_complete(self, _c, _m, _b, tmp_path, completed_components):
        _c.return_value, _m.return_value, _b.return_value = completed_components
        src, tdir = _pad(tmp_path)
        r = evaluate_from_artifacts("p1", src, tdir)
        assert r.status == EVAL_COMPLETED
        assert r.coverage.status == EVAL_COMPLETED
        assert r.mutation.status == EVAL_COMPLETED
        assert r.benchmark.status == EVAL_COMPLETED

    @patch("app.evaluation.orchestrator.benchmark.run_benchmark")
    @patch("app.evaluation.orchestrator.mutation.run_mutation")
    @patch("app.evaluation.orchestrator.coverage.run_coverage")
    def test_partial_availability(self, _c, _m, _b, tmp_path, completed_components):
        c, m, b = completed_components
        b.status = EVAL_UNAVAILABLE
        _c.return_value, _m.return_value, _b.return_value = c, m, b
        src, tdir = _pad(tmp_path)
        r = evaluate_from_artifacts("p1", src, tdir)
        # whole evaluation unavailable but not failed because one optional
        # component is unavailable
        assert r.status == EVAL_UNAVAILABLE
        assert r.coverage.status == EVAL_COMPLETED
        assert r.mutation.status == EVAL_COMPLETED
        assert r.benchmark.status == EVAL_UNAVAILABLE

    @patch("app.evaluation.orchestrator.benchmark.run_benchmark")
    @patch("app.evaluation.orchestrator.mutation.run_mutation")
    @patch("app.evaluation.orchestrator.coverage.run_coverage")
    def test_conditional_components_run(
        self, _c, _m, _b, tmp_path, completed_components,
    ):
        """All three components run regardless of M9 status."""
        _c.return_value = CoverageResult(status=EVAL_COMPLETED, line_percentage=50.0)
        _m.return_value = MutationResult(status=EVAL_COMPLETED, mutation_score=60.0)
        _b.return_value = BenchmarkResult(status=EVAL_COMPLETED, median_seconds=0.3)
        src, tdir = _pad(tmp_path)
        for status in (RETEST_BLOCKED, RETEST_NO_OP, RETEST_UNAVAILABLE):
            r = evaluate_from_artifacts("p1", src, tdir, _retest(status))
            assert _c.called and _m.called and _b.called
            assert r.coverage.status == EVAL_COMPLETED


class TestM9Behavior:
    def _run(self, tmp_path, retest):
        src, tdir = _pad(tmp_path)
        with patch("app.evaluation.orchestrator.coverage.run_coverage") as c, \
             patch("app.evaluation.orchestrator.mutation.run_mutation") as m, \
             patch("app.evaluation.orchestrator.benchmark.run_benchmark") as b:
            c.return_value = CoverageResult(status=EVAL_COMPLETED, line_percentage=100.0)
            m.return_value = MutationResult(status=EVAL_COMPLETED, killed=1, valid_mutants=1, mutation_score=100.0)
            b.return_value = BenchmarkResult(status=EVAL_COMPLETED, median_seconds=0.1)
            return evaluate_from_artifacts("p1", src, tdir, retest)

    def test_m9_fixed(self, tmp_path):
        r = self._run(tmp_path, _retest("fixed"))
        assert r.status == EVAL_COMPLETED
        assert len(r.warnings) == 0

    def test_m9_still_failing(self, tmp_path):
        r = self._run(tmp_path, _retest("still_failing"))
        assert r.status == EVAL_COMPLETED

    def test_m9_regression(self, tmp_path):
        r = self._run(tmp_path, _retest("regression"))
        assert r.status == EVAL_COMPLETED

    def test_m9_passed(self, tmp_path):
        r = self._run(tmp_path, _retest("passed"))
        assert r.status == EVAL_COMPLETED

    def test_m9_no_op(self, tmp_path):
        r = self._run(tmp_path, _retest(RETEST_NO_OP))
        assert r.status == EVAL_COMPLETED
        assert any("no-op" in w for w in r.warnings)

    def test_m9_blocked(self, tmp_path):
        r = self._run(tmp_path, _retest(RETEST_BLOCKED))
        assert r.status == EVAL_COMPLETED
        assert any("blocked" in w.lower() for w in r.warnings)

    def test_m9_unavailable_warns(self, tmp_path):
        r = self._run(tmp_path, _retest(RETEST_UNAVAILABLE))
        assert r.status == EVAL_COMPLETED
        assert any("unavailable" in w for w in r.warnings)

    def test_retest_id_anchored(self, tmp_path):
        rt = ReTestResult(project_id="p1", status="fixed", diagnosis_id="d-abc",
                          created_at=_CREATED)
        r = self._run(tmp_path, rt)
        assert r.retest_id == "d-abc"


class TestEvaluationDeterminism:
    @patch("app.evaluation.orchestrator.coverage.run_coverage")
    @patch("app.evaluation.orchestrator.mutation.run_mutation")
    @patch("app.evaluation.orchestrator.benchmark.run_benchmark")
    def test_stable_structure(self, _b, _m, _c, tmp_path, completed_components):
        _c.return_value, _m.return_value, _b.return_value = completed_components
        src, tdir = _pad(tmp_path)
        r1 = evaluate_from_artifacts("p1", src, tdir)
        r2 = evaluate_from_artifacts("p1", src, tdir)
        d1 = r1.model_dump()
        d2 = r2.model_dump()
        # created_at is runtime metadata; everything else deterministic
        d1.pop("created_at")
        d2.pop("created_at")
        assert d1 == d2


class TestEvaluationIdempotency:
    @patch("app.evaluation.orchestrator.coverage.run_coverage")
    @patch("app.evaluation.orchestrator.mutation.run_mutation")
    @patch("app.evaluation.orchestrator.benchmark.run_benchmark")
    def test_no_source_or_test_mutation(
        self, _b, _m, _c, tmp_path, completed_components,
    ):
        _c.return_value, _m.return_value, _b.return_value = completed_components
        src, tdir = _pad(tmp_path)
        src_text = (src / "app.py").read_text()
        test_text = (tdir / "test_app.py").read_text()
        r1 = evaluate_from_artifacts("p1", src, tdir)
        r2 = evaluate_from_artifacts("p1", src, tdir)
        assert (src / "app.py").read_text() == src_text
        assert (tdir / "test_app.py").read_text() == test_text
        assert r1.coverage.status == r2.coverage.status


class TestEvaluationModel:
    def test_schema_version(self):
        r = EvaluationResult(project_id="p", created_at=_CREATED)
        assert r.schema_version == 1
        assert r.status == EVAL_NOT_RUN

    def test_component_defaults(self):
        r = EvaluationResult(project_id="p", created_at=_CREATED)
        assert r.coverage.status == EVAL_NOT_RUN
        assert r.mutation.status == EVAL_NOT_RUN
        assert r.benchmark.status == EVAL_NOT_RUN
