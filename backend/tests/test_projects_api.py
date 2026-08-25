"""End-to-end tests for the project API endpoints."""

from pathlib import Path


def test_full_upload_profile_get_flow(client):
    # Upload
    res = client.post(
        "/api/projects/upload",
        files=[
            ("files", ("proj/app.py", b"class App:\n    def run(self): pass\n")),
            ("files", ("proj/test_app.py", b"def test_run(): assert True\n")),
        ],
    )
    assert res.status_code == 200
    pid = res.json()["project_id"]

    # Profile
    res2 = client.post(f"/api/projects/{pid}/profile")
    assert res2.status_code == 200
    profile = res2.json()
    assert profile["metrics"]["total_files"] == 2
    assert profile["tests"]["files"] == 1

    # GET
    res3 = client.get(f"/api/projects/{pid}")
    assert res3.status_code == 200
    detail = res3.json()
    assert detail["project_id"] == pid
    assert detail["profile"] is not None
    assert detail["profile"]["metrics"]["total_files"] == 2


def test_full_from_path_profile_get_flow(client, tmp_path):
    d = tmp_path / "sample"
    d.mkdir()
    (d / "main.py").write_text("print('hello')")
    (d / "README.md").write_text("# Sample")

    # Register
    res = client.post("/api/projects/from-path", json={"path": str(d)})
    assert res.status_code == 200
    pid = res.json()["project_id"]
    assert res.json()["origin"] == "path"

    # Profile
    res2 = client.post(f"/api/projects/{pid}/profile")
    assert res2.status_code == 200
    assert res2.json()["metrics"]["total_files"] == 2

    # GET
    res3 = client.get(f"/api/projects/{pid}")
    assert res3.status_code == 200
    assert res3.json()["source_path"] == str(d)


def test_profile_unknown_project_returns_404(client):
    res = client.post("/api/projects/nonexistent/profile")
    assert res.status_code == 404


def test_get_unknown_project_returns_404(client):
    res = client.get("/api/projects/nonexistent")
    assert res.status_code == 404


def test_health_still_works(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "ai-test-platform"}


def test_get_project_without_profile(client):
    res = client.post(
        "/api/projects/upload",
        files=[("files", ("x.py", b"print(1)"))],
    )
    pid = res.json()["project_id"]
    res2 = client.get(f"/api/projects/{pid}")
    assert res2.status_code == 200
    assert res2.json()["profile"] is None
