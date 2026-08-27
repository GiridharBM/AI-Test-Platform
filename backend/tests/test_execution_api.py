"""Tests for the test execution API endpoint."""

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.execution import STATUS_PASSED, STATUS_UNAVAILABLE


client = TestClient(app, raise_server_exceptions=False)


def _register_project(tmp_path: Path) -> str:
    """Register a local project and return its project_id."""
    # Create a minimal Python project
    src = tmp_path / "myproject"
    src.mkdir()
    (src / "app.py").write_text(
        'def add(a, b):\n    return a + b\n',
        encoding="utf-8",
    )
    (src / "test_app.py").write_text(
        'def test_add():\n    assert 1 + 1 == 2\n',
        encoding="utf-8",
    )
    resp = client.post("/api/projects/from-path", json={"path": str(src)})
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _run_pipeline(project_id: str) -> None:
    """Run profile → discover → plan → generate."""
    resp = client.post(f"/api/projects/{project_id}/profile")
    assert resp.status_code == 200
    resp = client.post(f"/api/projects/{project_id}/discover")
    assert resp.status_code == 200
    resp = client.post(f"/api/projects/{project_id}/plan")
    assert resp.status_code == 200
    resp = client.post(f"/api/projects/{project_id}/generate")
    assert resp.status_code == 200


# ── Execute endpoint tests ───────────────────────────────────────────

class TestExecuteEndpoint:
    def test_execute_full_flow(self, tmp_path):
        """Execute the full pipeline through to execution."""
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)

        with patch("app.execution.runner._docker_available", return_value=False):
            resp = client.post(f"/api/projects/{project_id}/execute")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == project_id
        assert data["overall_status"] == STATUS_UNAVAILABLE
        assert data["schema_version"] == 1
        assert "Docker" in data["warnings"][0]

    def test_execute_without_generate_returns_404(self):
        """Execute without prior generate should return 404."""
        # Create a project but don't run pipeline
        src = Path("C:/tmp/fakeproj_test_nonexist")
        try:
            src.mkdir(parents=True, exist_ok=True)
            (src / "app.py").write_text("x = 1\n")
            resp = client.post("/api/projects/from-path", json={"path": str(src)})
            pid = resp.json()["project_id"]
            resp = client.post(f"/api/projects/{pid}/execute")
            assert resp.status_code == 404
            assert "generate" in resp.json()["detail"].lower()
        finally:
            import shutil
            shutil.rmtree(src, ignore_errors=True)

    def test_execute_unknown_project_returns_404(self):
        resp = client.post("/api/projects/nonexistent/execute")
        assert resp.status_code == 404

    def test_execute_persisted_in_get(self, tmp_path):
        """After execution, results should appear in GET /{id}."""
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)

        with patch("app.execution.runner._docker_available", return_value=False):
            client.post(f"/api/projects/{project_id}/execute")

        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution"] is not None
        assert data["execution"]["project_id"] == project_id
        assert data["execution"]["overall_status"] == STATUS_UNAVAILABLE

    def test_execute_idempotent(self, tmp_path):
        """Executing twice should overwrite with the latest result."""
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)

        with patch("app.execution.runner._docker_available", return_value=False):
            resp1 = client.post(f"/api/projects/{project_id}/execute")
            resp2 = client.post(f"/api/projects/{project_id}/execute")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Both should have the same structure
        assert resp1.json()["overall_status"] == resp2.json()["overall_status"]

    def test_execute_failed_tests_return_200(self, tmp_path):
        """Failed tests should still return HTTP 200 with status=failed."""
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)

        pytest_stdout = (
            "tests/test_example.py::test_one PASSED\n"
            "tests/test_example.py::test_two FAILED\n"
            "1 passed, 1 failed in 0.5s\n"
        )

        with patch("app.execution.runner._docker_available", return_value=True), \
             patch("app.execution.runner._ensure_image"), \
             patch("app.execution.runner.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "returncode": 1,
                "stdout": pytest_stdout.encode(),
                "stderr": b"",
            })()
            resp = client.post(f"/api/projects/{project_id}/execute")

        assert resp.status_code == 200
        assert resp.json()["overall_status"] == "failed"
        assert resp.json()["summary"]["failed"] == 1

    def test_execute_timeout_returns_200(self, tmp_path):
        """Timeout should return HTTP 200 with status=timeout."""
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)

        import subprocess as sp

        call_count = 0
        def _timeout_then_ok(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise sp.TimeoutExpired(cmd="docker", timeout=1)
            return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

        with patch("app.execution.runner._docker_available", return_value=True), \
             patch("app.execution.runner._ensure_image"), \
             patch("app.execution.runner.subprocess.run", side_effect=_timeout_then_ok):
            resp = client.post(f"/api/projects/{project_id}/execute")

        assert resp.status_code == 200
        assert resp.json()["overall_status"] == "timeout"

    def test_execute_result_structure(self, tmp_path):
        """Verify the full structure of the execution result."""
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)

        with patch("app.execution.runner._docker_available", return_value=False):
            resp = client.post(f"/api/projects/{project_id}/execute")

        data = resp.json()
        assert "project_id" in data
        assert "overall_status" in data
        assert "exit_code" in data
        assert "stdout" in data
        assert "stderr" in data
        assert "duration_seconds" in data
        assert "summary" in data
        assert "file_results" in data
        assert "warnings" in data
        assert "schema_version" in data

    def test_get_without_execution_returns_null(self, tmp_path):
        """GET /{id} before execution should have null execution field."""
        project_id = _register_project(tmp_path)
        _run_pipeline(project_id)

        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["execution"] is None


# ── Persistence tests ────────────────────────────────────────────────

class TestExecutionPersistence:
    def test_save_and_read(self, tmp_path):
        from app.services.project_ingestion import read_execution, save_execution

        ws = tmp_path / "workspace"
        pid = "test-project-123"
        (ws / pid / ".meta").mkdir(parents=True)

        result_json = '{"project_id": "' + pid + '", "overall_status": "passed", "exit_code": 0}'
        save_execution(ws, result_json)
        data = read_execution(ws, pid)
        assert data is not None
        assert '"project_id"' in data

    def test_read_missing(self, tmp_path):
        from app.services.project_ingestion import read_execution

        ws = tmp_path / "workspace"
        assert read_execution(ws, "nonexistent") is None

    def test_file_at_correct_path(self, tmp_path):
        from app.services.project_ingestion import save_execution

        ws = tmp_path / "workspace"
        pid = "proj-abc"
        (ws / pid / ".meta").mkdir(parents=True)

        save_execution(ws, '{"project_id": "' + pid + '", "overall_status": "passed"}')
        assert (ws / pid / ".meta" / "execution.json").is_file()
