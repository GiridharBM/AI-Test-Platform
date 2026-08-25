"""End-to-end tests for the test plan API endpoint."""

from pathlib import Path


def _make_project(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def test_plan_full_flow(client, tmp_path):
    project = _make_project(tmp_path / "planproject", {
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

    # Register
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    assert res.status_code == 200
    pid = res.json()["project_id"]

    # Profile
    res = client.post(f"/api/projects/{pid}/profile")
    assert res.status_code == 200

    # Discover
    res = client.post(f"/api/projects/{pid}/discover")
    assert res.status_code == 200
    codemap = res.json()
    assert codemap["project_id"] == pid

    # Plan
    res = client.post(f"/api/projects/{pid}/plan")
    assert res.status_code == 200
    plan = res.json()
    assert plan["project_id"] == pid
    assert plan["summary"]["total_specs"] >= 1
    assert len(plan["specs"]) >= 1

    # parse is untested with many args → should be in plan
    spec_names = [s["target_qualified_name"] for s in plan["specs"]]
    assert "parse" in spec_names


def test_plan_without_codemap_returns_404(client, tmp_path):
    project = _make_project(tmp_path / "nocm", {
        "app.py": "x = 1\n",
    })
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    res = client.post(f"/api/projects/{pid}/profile")
    assert res.status_code == 200

    # No discover → plan should 404
    res = client.post(f"/api/projects/{pid}/plan")
    assert res.status_code == 404


def test_plan_without_profile_returns_404(client, tmp_path):
    project = _make_project(tmp_path / "noprof", {
        "app.py": "x = 1\n",
    })
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]

    # No profile → plan should 404
    res = client.post(f"/api/projects/{pid}/plan")
    assert res.status_code == 404


def test_plan_persisted_in_get(client, tmp_path):
    project = _make_project(tmp_path / "persist", {
        "app.py": (
            "def process(path, data):\n"
            "    pass\n"
        ),
        "test_app.py": "def test_process(): assert True\n",
    })

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")
    client.post(f"/api/projects/{pid}/plan")

    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["test_plan"] is not None
    assert detail["test_plan"]["project_id"] == pid
    assert detail["test_plan"]["summary"]["total_specs"] >= 1


def test_plan_idempotent(client, tmp_path):
    project = _make_project(tmp_path / "idempotent", {
        "app.py": (
            "def compute(x, y, z):\n"
            "    return x + y + z\n"
        ),
    })

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")

    res1 = client.post(f"/api/projects/{pid}/plan")
    res2 = client.post(f"/api/projects/{pid}/plan")
    assert res1.status_code == 200
    assert res2.status_code == 200
    plan1 = res1.json()
    plan2 = res2.json()
    assert plan1["summary"]["total_specs"] == plan2["summary"]["total_specs"]
    assert len(plan1["specs"]) == len(plan2["specs"])


def test_plan_unknown_project_returns_404(client):
    res = client.post("/api/projects/nonexistent/plan")
    assert res.status_code == 404


def test_get_project_without_plan(client, tmp_path):
    project = _make_project(tmp_path / "noplan", {
        "app.py": "x = 1\n",
    })
    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]

    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    assert res.json()["test_plan"] is None


def test_plan_empty_project(client, tmp_path):
    project = tmp_path / "emptyplan"
    project.mkdir()

    res = client.post("/api/projects/from-path", json={"path": str(project)})
    pid = res.json()["project_id"]
    client.post(f"/api/projects/{pid}/profile")
    client.post(f"/api/projects/{pid}/discover")

    res = client.post(f"/api/projects/{pid}/plan")
    assert res.status_code == 200
    plan = res.json()
    assert plan["summary"]["total_specs"] == 0
    assert len(plan["specs"]) == 0
