"""Integration tests for the project-level test discovery flow."""

from pathlib import Path


def _make_project(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _setup_project(client, tmp_path, files: dict[str, str]) -> str:
    """Register a local project, profile it, return project_id."""
    project = _make_project(tmp_path / "proj", files)
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    assert res.status_code == 200
    pid = res.json()["project_id"]
    res2 = client.post(f"/api/projects/{pid}/profile")
    assert res2.status_code == 200
    return pid


def test_discover_full_flow(client, tmp_path):
    pid = _setup_project(client, tmp_path, {
        "app.py": (
            "def login(): pass\n"
            "def logout(): pass\n"
        ),
        "tests/test_app.py": (
            "def test_login():\n"
            "    assert login() is None\n"
        ),
    })
    res = client.post(f"/api/projects/{pid}/discover")
    assert res.status_code == 200
    codemap = res.json()
    assert codemap["project_id"] == pid
    assert len(codemap["source_modules"]) == 1
    assert len(codemap["test_functions"]) == 1
    assert codemap["test_functions"][0]["name"] == "test_login"
    assert codemap["coverage_summary"]["total_targets"] == 2


def test_discover_without_profile_succeeds(client, tmp_path):
    # Register but don't profile
    project = _make_project(tmp_path / "noprof", {"app.py": "x = 1"})
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    # Discover should still work (it doesn't require profile)
    res2 = client.post(f"/api/projects/{pid}/discover")
    assert res2.status_code == 200
    assert res2.json()["coverage_summary"]["total_targets"] == 0


def test_discover_unknown_project_returns_404(client):
    res = client.post("/api/projects/nonexistent/discover")
    assert res.status_code == 404


def test_discover_idempotent(client, tmp_path):
    pid = _setup_project(client, tmp_path, {
        "calc.py": "def add(a, b): return a + b\n",
        "test_calc.py": "def test_add(): assert add(1, 2) == 3\n",
    })
    res1 = client.post(f"/api/projects/{pid}/discover")
    res2 = client.post(f"/api/projects/{pid}/discover")
    assert res1.status_code == 200
    assert res2.status_code == 200
    c1, c2 = res1.json(), res2.json()
    assert c1["coverage_summary"]["total_targets"] == c2["coverage_summary"]["total_targets"]
    assert len(c1["test_functions"]) == len(c2["test_functions"])


def test_get_project_with_codemap(client, tmp_path):
    pid = _setup_project(client, tmp_path, {
        "app.py": "def run(): pass\n",
        "test_app.py": "def test_run(): pass\n",
    })
    client.post(f"/api/projects/{pid}/discover")
    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["codemap"] is not None
    assert detail["codemap"]["project_id"] == pid
    assert detail["profile"] is not None


def test_get_project_without_codemap(client, tmp_path):
    pid = _setup_project(client, tmp_path, {"app.py": "x = 1\n"})
    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    assert res.json()["codemap"] is None


def test_discover_project_with_no_tests(client, tmp_path):
    pid = _setup_project(client, tmp_path, {
        "app.py": "def foo(): pass\ndef bar(): pass\n",
    })
    res = client.post(f"/api/projects/{pid}/discover")
    assert res.status_code == 200
    codemap = res.json()
    assert codemap["test_functions"] == []
    assert codemap["coverage_summary"]["targets_without_tests"] == 2
    assert codemap["coverage_summary"]["targets_with_tests"] == 0
    assert codemap["coverage_summary"]["coverage_percentage"] == 0.0


def test_discover_project_with_no_source(client, tmp_path):
    pid = _setup_project(client, tmp_path, {
        "test_empty.py": "def test_nothing(): pass\n",
    })
    res = client.post(f"/api/projects/{pid}/discover")
    assert res.status_code == 200
    codemap = res.json()
    assert len(codemap["test_functions"]) == 1
    assert codemap["coverage_summary"]["total_targets"] == 0


def test_discover_project_with_syntax_errors(client, tmp_path):
    pid = _setup_project(client, tmp_path, {
        "bad.py": "def foo(\n  indent",
        "good.py": "def bar(): pass\n",
    })
    res = client.post(f"/api/projects/{pid}/discover")
    assert res.status_code == 200
    codemap = res.json()
    assert any("syntax" in w.lower() or "parse" in w.lower() for w in codemap["warnings"])
    # good.py should still be analyzed (bad.py is included as empty module)
    assert len(codemap["source_modules"]) == 2


def test_discover_via_upload_flow(client):
    res = client.post(
        "/api/projects/upload",
        files=[
            ("files", ("proj/calc.py", b"def add(a, b): return a + b\n")),
            ("files", ("proj/test_calc.py", b"def test_add(): assert add(1, 2) == 3\n")),
        ],
    )
    assert res.status_code == 200
    pid = res.json()["project_id"]
    res2 = client.post(f"/api/projects/{pid}/profile")
    assert res2.status_code == 200
    res3 = client.post(f"/api/projects/{pid}/discover")
    assert res3.status_code == 200
    codemap = res3.json()
    assert codemap["coverage_summary"]["total_targets"] == 1
    assert codemap["coverage_summary"]["targets_with_tests"] == 1


def test_codemap_persisted(client, tmp_path):
    pid = _setup_project(client, tmp_path, {
        "app.py": "def greet(): pass\n",
        "test_greet.py": "def test_greet(): pass\n",
    })
    client.post(f"/api/projects/{pid}/discover")
    # GET should return the persisted codemap
    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    assert res.json()["codemap"] is not None
    assert res.json()["codemap"]["coverage_summary"]["total_targets"] == 1


def test_health_still_works(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "ai-test-platform"}
