"""End-to-end tests for the test scaffold generation API endpoint."""

from pathlib import Path


def _make_project(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def test_generate_full_flow(client, tmp_path):
    project = _make_project(tmp_path / "genproject", {
        "app.py": (
            "def parse(path, data, count, verbose):\n"
            "    pass\n"
            "def helper():\n"
            "    pass\n"
        ),
        "test_app.py": (
            "def test_helper():\n"
            "    assert True\n"
        ),
    })

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    assert res.status_code == 200
    pid = res.json()["project_id"]

    res = client.post(f"/api/projects/{pid}/profile")
    assert res.status_code == 200

    res = client.post(f"/api/projects/{pid}/discover")
    assert res.status_code == 200

    res = client.post(f"/api/projects/{pid}/plan")
    assert res.status_code == 200

    res = client.post(f"/api/projects/{pid}/generate")
    assert res.status_code == 200
    gen = res.json()
    assert gen["project_id"] == pid
    assert len(gen["files"]) >= 1
    assert gen["summary"]["total_test_functions"] >= 1

    content = gen["files"][0]["content"]
    assert "def test_" in content
    assert "NotImplementedError" in content


def test_generate_without_profile_returns_404(client, tmp_path):
    project = _make_project(tmp_path / "noprofgen", {
        "app.py": "x = 1\n",
    })
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]

    res = client.post(f"/api/projects/{pid}/generate")
    assert res.status_code == 404


def test_generate_without_plan_returns_404(client, tmp_path):
    project = _make_project(tmp_path / "noplagen", {
        "app.py": "x = 1\n",
    })
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")

    res = client.post(f"/api/projects/{pid}/generate")
    assert res.status_code == 404


def test_generate_without_codemap_returns_404(client, tmp_path):
    project = _make_project(tmp_path / "nocmgen", {
        "app.py": "x = 1\n",
    })
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")

    res = client.post(f"/api/projects/{pid}/generate")
    assert res.status_code == 404


def test_generate_unknown_project_returns_404(client):
    res = client.post("/api/projects/nonexistent/generate")
    assert res.status_code == 404


def test_generate_persisted_in_get(client, tmp_path):
    project = _make_project(tmp_path / "persistgen", {
        "app.py": "def compute(x):\n    return x\n",
        "test_app.py": "def test_compute(): assert True\n",
    })

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")
    client.post(f"/api/projects/{pid}/plan")
    client.post(f"/api/projects/{pid}/generate")

    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["test_generation"] is not None
    assert detail["test_generation"]["project_id"] == pid


def test_generate_idempotent(client, tmp_path):
    project = _make_project(tmp_path / "idempotentgen", {
        "app.py": "def calc(x, y):\n    return x + y\n",
    })

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")
    client.post(f"/api/projects/{pid}/plan")

    res1 = client.post(f"/api/projects/{pid}/generate")
    res2 = client.post(f"/api/projects/{pid}/generate")
    assert res1.status_code == 200
    assert res2.status_code == 200
    gen1 = res1.json()
    gen2 = res2.json()
    assert gen1["summary"]["total_files"] == gen2["summary"]["total_files"]
    assert gen1["summary"]["total_test_functions"] == gen2["summary"]["total_test_functions"]


def test_generate_empty_project(client, tmp_path):
    project = tmp_path / "emptygen"
    project.mkdir()

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")
    client.post(f"/api/projects/{pid}/plan")

    res = client.post(f"/api/projects/{pid}/generate")
    assert res.status_code == 200
    gen = res.json()
    assert gen["summary"]["total_files"] == 0


def test_get_project_without_generation(client, tmp_path):
    project = _make_project(tmp_path / "nogenget", {
        "app.py": "x = 1\n",
    })
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]

    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    assert res.json()["test_generation"] is None


def test_generated_files_written_to_workspace(client, tmp_path):
    project = _make_project(tmp_path / "wsgen", {
        "app.py": "def process(data):\n    pass\n",
    })

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")
    client.post(f"/api/projects/{pid}/plan")
    client.post(f"/api/projects/{pid}/generate")

    gen_dir = tmp_path / "workspace" / pid / "generated_tests"
    assert gen_dir.is_dir()
    py_files = list(gen_dir.glob("test_*.py"))
    assert len(py_files) >= 1
    init_file = gen_dir / "__init__.py"
    assert init_file.exists()
