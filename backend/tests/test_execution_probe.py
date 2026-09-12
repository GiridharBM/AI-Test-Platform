"""Docker-readiness probe: cause surfacing + bounded retry.

Regression for a live acceptance failure where the second execution reported
``unavailable`` ("Docker is not available...") while Docker was healthy. The
python code came from the readiness probe (``docker info``) returning False,
and the old code discarded the underlying stderr/returncode. These tests prove
the cause is surfaced and that a single transient Windows/Docker-Desktop
not-ready moment no longer hard-fails the pipeline, while a genuinely
unavailable daemon still fails closed.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.execution import runner
from app.execution.runner import _docker_available, execute_tests
from app.models.execution import STATUS_UNAVAILABLE


class TestProbeDetailSurfaced:
    def test_unavailable_warning_includes_underlying_stderr(self):
        with patch(
            "app.execution.runner.subprocess.run",
            return_value=MagicMock(
                returncode=1,
                stderr=b"error during connect: failed to connect to the daemon",
            ),
        ) as mock_run, patch("app.execution.runner.config.EXECUTION_DOCKER_PROBE_RETRIES", 0):
            result = execute_tests(Path("/nonexistent"), "proj")
        assert result.overall_status == STATUS_UNAVAILABLE
        # the generic warning now carries the exact probe failure
        assert "error during connect: failed to connect to the daemon" in result.warnings[0]
        assert mock_run.call_count == 1

    def test_probe_timeout_failure_not_hidden(self):
        with patch(
            "app.execution.runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="docker info", timeout=10),
        ) as mock_run, patch("app.execution.runner.config.EXECUTION_DOCKER_PROBE_RETRIES", 0):
            assert _docker_available() is False
        assert "timed out" in runner._docker_probe_detail
        assert mock_run.call_count == 1

    def test_docker_not_on_path_not_hidden(self):
        with patch(
            "app.execution.runner.subprocess.run", side_effect=FileNotFoundError
        ), patch("app.execution.runner.config.EXECUTION_DOCKER_PROBE_RETRIES", 0):
            assert _docker_available() is False
        assert "not found on PATH" in runner._docker_probe_detail


class TestProbeRetry:
    def test_transient_failure_recovers(self):
        """First probes miss (Docker Desktop settling), later probe succeeds."""
        with patch(
            "app.execution.runner.subprocess.run",
            side_effect=[
                subprocess.TimeoutExpired(cmd="docker info", timeout=10),
                MagicMock(returncode=1, stderr=b"daemon not ready"),
                MagicMock(returncode=0),
            ],
        ) as mock_run, patch("app.execution.runner.config.EXECUTION_DOCKER_PROBE_RETRIES", 2):
            assert _docker_available() is True
        assert mock_run.call_count == 3

    def test_persistent_failure_stays_closed(self):
        with patch(
            "app.execution.runner.subprocess.run",
            return_value=MagicMock(returncode=1, stderr=b"daemon down"),
        ) as mock_run, patch("app.execution.runner.config.EXECUTION_DOCKER_PROBE_RETRIES", 1):
            assert _docker_available() is False
        assert mock_run.call_count == 2  # bounded: initial probe + exactly one retry