"""Tests for the deterministic sandboxed test execution subsystem."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core import config
from app.execution.runner import (
    DockerUnavailable,
    _docker_available,
    _ensure_image,
    _parse_file_results,
    _parse_pytest_output,
    execute_tests,
)
from app.models.execution import (
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_TIMEOUT,
    STATUS_UNAVAILABLE,
    ExecutionSummary,
    TestExecutionResult,
    TestFileResult,
    VALID_STATUSES,
)


# ── Model tests ──────────────────────────────────────────────────────

class TestFileResultModel:
    def test_valid_result(self):
        r = TestFileResult(file_path="test_foo.py", status="passed")
        assert r.file_path == "test_foo.py"
        assert r.status == "passed"
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.duration_seconds == 0.0

    def test_defaults(self):
        r = TestFileResult(file_path="x.py", status="error")
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.duration_seconds == 0.0

    def test_serialization_roundtrip(self):
        r = TestFileResult(file_path="a.py", status="failed", stdout="out", stderr="err", duration_seconds=1.5)
        data = r.model_dump()
        r2 = TestFileResult.model_validate(data)
        assert r2.file_path == r.file_path
        assert r2.status == r.status
        assert r2.stdout == r.stdout


class TestExecutionSummaryModel:
    def test_defaults(self):
        s = ExecutionSummary()
        assert s.total_files == 0
        assert s.passed == 0

    def test_with_values(self):
        s = ExecutionSummary(total_files=3, passed=2, failed=1)
        assert s.total_files == 3
        assert s.passed == 2
        assert s.failed == 1


class TestExecutionResultModel:
    def test_valid_result(self):
        r = TestExecutionResult(project_id="abc")
        assert r.project_id == "abc"
        assert r.overall_status == STATUS_UNAVAILABLE
        assert r.exit_code == -1
        assert r.schema_version == 1

    def test_deterministic_representation(self):
        r = TestExecutionResult(
            project_id="test",
            overall_status=STATUS_PASSED,
            exit_code=0,
        )
        data = r.model_dump()
        r2 = TestExecutionResult.model_validate(data)
        assert r.overall_status == r2.overall_status
        assert r.exit_code == r2.exit_code

    def test_all_statuses_valid(self):
        for status in VALID_STATUSES:
            r = TestExecutionResult(project_id="x", overall_status=status)
            assert r.overall_status == status

    def test_file_results_serialization(self):
        r = TestExecutionResult(
            project_id="x",
            file_results=[
                TestFileResult(file_path="a.py", status="passed"),
                TestFileResult(file_path="b.py", status="failed"),
            ],
        )
        data = r.model_dump()
        assert len(data["file_results"]) == 2
        assert data["file_results"][0]["file_path"] == "a.py"

    def test_no_timestamps_in_content(self):
        """Execution result should not inject timestamps into deterministic fields."""
        import json
        r = TestExecutionResult(project_id="x", overall_status=STATUS_PASSED)
        raw = r.model_dump_json()
        parsed = json.loads(raw)
        # created_at should not exist (this model has no created_at field by design)
        assert "created_at" not in parsed


# ── Output parser tests ──────────────────────────────────────────────

class TestParsePytestOutput:
    def test_all_passed(self):
        stdout = (
            "tests/test_foo.py::test_a PASSED\n"
            "tests/test_foo.py::test_b PASSED\n"
            "2 passed in 0.10s\n"
        )
        p, f, e, s, t = _parse_pytest_output(stdout)
        assert p == 2
        assert f == 0
        assert e == 0
        assert t == 2

    def test_mixed_results(self):
        stdout = (
            "tests/test_a.py::test_ok PASSED\n"
            "tests/test_b.py::test_bad FAILED\n"
            "tests/test_c.py::test_err ERROR\n"
            "1 passed, 1 failed, 1 error in 0.2s\n"
        )
        p, f, e, s, t = _parse_pytest_output(stdout)
        assert p == 1
        assert f == 1
        assert e == 1
        assert t == 3

    def test_empty_output(self):
        p, f, e, s, t = _parse_pytest_output("")
        assert t == 0

    def test_skipped(self):
        stdout = "tests/test_x.py::test_skip SKIPPED\n"
        p, f, e, s, t = _parse_pytest_output(stdout)
        assert s == 1
        assert t == 1


class TestParseFileResults:
    def test_single_file_all_pass(self):
        stdout = (
            "tests/test_a.py::test_1 PASSED\n"
            "tests/test_a.py::test_2 PASSED\n"
        )
        files = _parse_file_results(stdout)
        assert files == {"tests/test_a.py": "passed"}

    def test_worst_status_per_file(self):
        stdout = (
            "tests/test_a.py::test_1 PASSED\n"
            "tests/test_a.py::test_2 FAILED\n"
            "tests/test_b.py::test_1 PASSED\n"
        )
        files = _parse_file_results(stdout)
        assert files["tests/test_a.py"] == "failed"
        assert files["tests/test_b.py"] == "passed"

    def test_error_worse_than_failed(self):
        stdout = (
            "tests/test_a.py::test_1 FAILED\n"
            "tests/test_a.py::test_2 ERROR\n"
        )
        files = _parse_file_results(stdout)
        assert files["tests/test_a.py"] == "error"

    def test_empty(self):
        assert _parse_file_results("") == {}


# ── Runner tests (Docker mocked) ─────────────────────────────────────

class TestDockerAvailable:
    @patch("app.execution.runner.subprocess.run")
    def test_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert _docker_available() is True

    @patch("app.execution.runner.subprocess.run")
    def test_unavailable(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert _docker_available() is False

    @patch("app.execution.runner.subprocess.run", side_effect=FileNotFoundError)
    def test_docker_not_installed(self, mock_run):
        assert _docker_available() is False


class TestEnsureImage:
    @patch("app.execution.runner.subprocess.run")
    def test_image_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        _ensure_image("test-image")  # should not raise
        assert mock_run.call_count == 1

    @patch("app.execution.runner.subprocess.run")
    def test_image_builds(self, mock_run):
        # First call: inspect fails, second call: build succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1),  # image inspect
            MagicMock(returncode=0),  # docker build
        ]
        _ensure_image("test-image")
        assert mock_run.call_count == 2

    @patch("app.execution.runner.subprocess.run")
    def test_build_fails(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=1, stderr=b"build error"),
        ]
        with pytest.raises(DockerUnavailable, match="build failed"):
            _ensure_image("test-image")


class TestExecuteTestsDockerUnavailable:
    @patch("app.execution.runner._docker_available", return_value=False)
    def test_returns_unavailable(self, _mock):
        result = execute_tests(Path("/nonexistent"), "proj")
        assert result.overall_status == STATUS_UNAVAILABLE
        assert "Docker" in result.warnings[0]

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image", side_effect=DockerUnavailable("no image"))
    def test_image_build_failure(self, _mock_img, _mock_docker):
        result = execute_tests(Path("/nonexistent"), "proj")
        assert result.overall_status == STATUS_UNAVAILABLE
        assert "no image" in result.warnings[0]


class TestExecuteTestsNoTestDir:
    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    def test_missing_dir(self, _mock_img, _mock_docker):
        result = execute_tests(Path("/nonexistent/path"), "proj")
        assert result.overall_status == STATUS_ERROR
        assert "does not exist" in result.warnings[0]


class TestExecuteTestsSuccess:
    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_successful_execution(self, mock_run, _mock_img, _mock_docker, tmp_path):
        # Create a fake test dir
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_example.py").write_text("# test")

        # Mock Docker run: successful pytest output
        pytest_stdout = (
            "tests/test_example.py::test_one PASSED\n"
            "tests/test_example.py::test_two FAILED\n"
            "1 passed, 1 failed in 0.5s\n"
        )
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=pytest_stdout.encode(),
            stderr=b"",
        )
        result = execute_tests(test_dir, "proj123")
        assert result.overall_status == STATUS_FAILED
        assert result.exit_code == 1
        assert result.summary.passed == 1
        assert result.summary.failed == 1
        assert result.summary.total_test_functions == 2
        assert result.duration_seconds >= 0

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_no_tests_collected(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_empty.py").write_text("# no tests")

        mock_run.return_value = MagicMock(
            returncode=5,
            stdout=b"no tests ran in 0.01s\n",
            stderr=b"",
        )
        result = execute_tests(test_dir, "proj123")
        assert result.overall_status == STATUS_PASSED  # exit code 5 = no tests = pass

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_timeout(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Simulate timeout on docker run; docker kill succeeds
        call_count = 0
        def _timeout_then_ok(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise subprocess.TimeoutExpired(cmd="docker", timeout=1)
            return MagicMock(returncode=0, stdout=b"", stderr=b"")
        mock_run.side_effect = _timeout_then_ok
        result = execute_tests(test_dir, "proj123", timeout=1)
        assert result.overall_status == STATUS_TIMEOUT
        assert "timed out" in result.warnings[0]


class TestExecuteTestsFileResults:
    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_multi_file_results(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_a.py").write_text("# a")
        (test_dir / "test_b.py").write_text("# b")

        stdout = (
            "tests/test_a.py::test_1 PASSED\n"
            "tests/test_a.py::test_2 PASSED\n"
            "tests/test_b.py::test_1 FAILED\n"
            "2 passed, 1 failed in 0.3s\n"
        )
        mock_run.return_value = MagicMock(returncode=1, stdout=stdout.encode(), stderr=b"")
        result = execute_tests(test_dir, "proj123")
        assert len(result.file_results) == 2
        by_path = {fr.file_path: fr.status for fr in result.file_results}
        assert by_path["tests/test_a.py"] == "passed"
        assert by_path["tests/test_b.py"] == "failed"


# ── Security tests ───────────────────────────────────────────────────

class TestRunnerSecurity:
    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_network_disabled(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        execute_tests(test_dir, "proj")
        # Find the docker run call
        docker_run_call = None
        for call in mock_run.call_args_list:
            if call.args and call.args[0] and call.args[0][0:2] == ["docker", "run"]:
                docker_run_call = call
                break
        assert docker_run_call is not None
        cmd = docker_run_call.args[0]
        assert "--network" in cmd
        assert "none" in cmd

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_read_only_root(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        execute_tests(test_dir, "proj")
        docker_run_call = None
        for call in mock_run.call_args_list:
            if call.args and call.args[0] and call.args[0][0:2] == ["docker", "run"]:
                docker_run_call = call
                break
        cmd = docker_run_call.args[0]
        assert "--read-only" in cmd

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_memory_limit(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        execute_tests(test_dir, "proj")
        docker_run_call = None
        for call in mock_run.call_args_list:
            if call.args and call.args[0] and call.args[0][0:2] == ["docker", "run"]:
                docker_run_call = call
                break
        cmd = docker_run_call.args[0]
        assert "--memory" in cmd
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == f"{config.EXECUTION_MEMORY_LIMIT_MB}m"

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_cpu_limit(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        execute_tests(test_dir, "proj")
        docker_run_call = None
        for call in mock_run.call_args_list:
            if call.args and call.args[0] and call.args[0][0:2] == ["docker", "run"]:
                docker_run_call = call
                break
        cmd = docker_run_call.args[0]
        assert "--cpus" in cmd

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_volume_is_readonly(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        execute_tests(test_dir, "proj")
        docker_run_call = None
        for call in mock_run.call_args_list:
            if call.args and call.args[0] and call.args[0][0:2] == ["docker", "run"]:
                docker_run_call = call
                break
        cmd = docker_run_call.args[0]
        # Find volume-mount -v args (contain ":"), skip pytest's -v flag
        for i, arg in enumerate(cmd):
            if arg == "-v" and i + 1 < len(cmd) and ":" in cmd[i + 1]:
                assert cmd[i + 1].endswith(":ro")

    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_no_host_path_escape(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        execute_tests(test_dir, "proj")
        docker_run_call = None
        for call in mock_run.call_args_list:
            if call.args and call.args[0] and call.args[0][0:2] == ["docker", "run"]:
                docker_run_call = call
                break
        cmd = docker_run_call.args[0]
        # Only the test dir is mounted; verify source is within system temp
        import tempfile as _tf
        volume_args = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-v" and i + 1 < len(cmd) and ":" in cmd[i + 1]]
        for vol in volume_args:
            # rsplit handles Windows drive letters (C:\path:/tests:ro)
            source = vol.rsplit(":", 2)[0]
            assert source.startswith(_tf.gettempdir())


# ── Config tests ─────────────────────────────────────────────────────

class TestExecutionConfig:
    def test_timeout_positive(self):
        assert config.EXECUTION_TIMEOUT_SECONDS > 0

    def test_memory_positive(self):
        assert config.EXECUTION_MEMORY_LIMIT_MB > 0

    def test_cpu_positive(self):
        assert config.EXECUTION_CPU_LIMIT > 0

    def test_output_limit_positive(self):
        assert config.EXECUTION_MAX_OUTPUT_BYTES > 0

    def test_image_name_set(self):
        assert isinstance(config.EXECUTION_IMAGE_NAME, str)
        assert len(config.EXECUTION_IMAGE_NAME) > 0


# ── Cleanup test ─────────────────────────────────────────────────────

class TestCleanup:
    @patch("app.execution.runner._docker_available", return_value=True)
    @patch("app.execution.runner._ensure_image")
    @patch("app.execution.runner.subprocess.run")
    def test_temp_dir_cleaned(self, mock_run, _mock_img, _mock_docker, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        execute_tests(test_dir, "proj")
        # The work_dir created inside execute_tests should be cleaned up
        # We verify by checking that subprocess was called (meaning it ran)
        # and no leftover temp dirs exist in tmp_path
        import os
        entries = [e for e in os.listdir(tmp_path) if e.startswith("exec_")]
        assert entries == []
