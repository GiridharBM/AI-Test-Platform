"""Tests for the local-path ingestion endpoint."""

from pathlib import Path

from app.services import project_ingestion as ingestion


def test_from_path_valid_directory(client, tmp_path):
    d = tmp_path / "my-project"
    d.mkdir()
    (d / "main.py").write_text("print(1)")
    res = client.post("/api/projects/from-path", json={"path": str(d)})
    assert res.status_code == 200
    body = res.json()
    assert body["origin"] == "path"
    assert body["name"] == "my-project"
    assert body["source_path"] == str(d)


def test_from_path_nonexistent(client):
    res = client.post("/api/projects/from-path", json={"path": "/no/such/dir"})
    assert res.status_code == 400


def test_from_path_file_not_dir(client, tmp_path):
    f = tmp_path / "notadir.txt"
    f.write_text("x")
    res = client.post("/api/projects/from-path", json={"path": str(f)})
    assert res.status_code == 400
    assert "not a directory" in res.json()["detail"].lower()


def test_from_path_drive_root_rejected(client):
    root = Path("C:/") if Path("C:/").is_dir() else Path(tmp_path_anchor())
    res = client.post("/api/projects/from-path", json={"path": str(root)})
    assert res.status_code == 400
    assert "root" in res.json()["detail"].lower()


def tmp_path_anchor():
    """Cross-platform drive root for testing."""
    return Path("D:/") if Path("D:/").is_dir() else Path("/")


def test_from_path_inside_workspace_rejected(client, tmp_path):
    """A path that falls inside the platform workspace must be rejected."""
    from app.core import config
    ws_inner = config.WORKSPACE_DIR / "something"
    ws_inner.mkdir(parents=True, exist_ok=True)
    res = client.post("/api/projects/from-path", json={"path": str(ws_inner)})
    assert res.status_code == 400
    assert "workspace" in res.json()["detail"].lower()


def test_from_path_relative_resolves(client, tmp_path):
    """A path given as relative should still resolve and work."""
    d = tmp_path / "reltest"
    d.mkdir()
    res = client.post("/api/projects/from-path", json={"path": str(d)})
    assert res.status_code == 200
