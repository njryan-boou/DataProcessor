"""Verify production frontend serving without changing the API-only workflow."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings


@pytest.fixture
def frontend_dist(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text("<!doctype html><html>DataFlow frontend</html>")
    (directory / "assets" / "app-abc123.js").write_text("console.log('DataFlow');")
    (directory / "assets" / "app-abc123.css").write_text("body { color: black; }")
    return directory


def app_with_build(monkeypatch: pytest.MonkeyPatch, directory: Path | None):
    settings = Settings(_env_file=None, frontend_dist=directory)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    return main_module.create_app()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, frontend_dist: Path):
    with TestClient(app_with_build(monkeypatch, frontend_dist)) as value:
        yield value


@pytest.mark.parametrize("path", ["/", "/index.html", "/dataset", "/dataset/123/visualize"])
def test_frontend_root_and_spa_pages(client: TestClient, path: str):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "DataFlow frontend" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"


def test_head_frontend_returns_headers_without_body(client: TestClient):
    response = client.head("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.content == b""


@pytest.mark.parametrize("path,content_type", [
    ("/assets/app-abc123.js", "javascript"),
    ("/assets/app-abc123.css", "text/css"),
])
def test_built_assets_keep_mime_types(client: TestClient, path: str, content_type: str):
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert "DataFlow frontend" not in response.text


@pytest.mark.parametrize("path", ["/assets/missing.js", "/missing.css", "/assets/missing"])
def test_missing_assets_are_json_not_spa_html(client: TestClient, path: str):
    response = client.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "DELETE"])
@pytest.mark.parametrize("path", ["/api", "/api/missing", "/api/assets/missing.js"])
def test_unknown_api_paths_remain_404(client: TestClient, method: str, path: str):
    response = client.request(method, path)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    if method != "HEAD":
        assert response.json() == {"detail": "Not Found"}


def test_existing_api_and_documentation_are_preserved(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok", "name": "DataFlow"}
    assert client.get("/api/config").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "DataFlow API"
    assert "Swagger UI" in client.get("/docs").text


def test_frontend_does_not_accept_post(client: TestClient):
    response = client.post("/dataset")
    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/%2e%2e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt", "/assets/%5csecret.txt"])
def test_traversal_does_not_serve_outside_files(client: TestClient, frontend_dist: Path, path: str):
    (frontend_dist.parent / "secret.txt").write_text("private outside content")
    response = client.get(path)
    assert response.status_code == 404
    assert "private outside content" not in response.text


def test_symlinks_cannot_serve_outside_build(client: TestClient, frontend_dist: Path):
    secret = frontend_dist.parent / "secret.txt"
    secret.write_text("private outside content")
    (frontend_dist / "assets" / "secret.txt").symlink_to(secret)
    response = client.get("/assets/secret.txt")
    assert response.status_code == 404
    assert "private outside content" not in response.text


def test_unconfigured_frontend_keeps_api_only_behavior(monkeypatch: pytest.MonkeyPatch):
    with TestClient(app_with_build(monkeypatch, None)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/dataset").status_code == 404
        assert client.get("/api/health").json()["status"] == "ok"


@pytest.mark.parametrize("target", ["missing", "empty", "file"])
def test_configured_missing_build_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str):
    directory = tmp_path / target
    if target == "empty":
        directory.mkdir()
    elif target == "file":
        directory.write_text("not a directory")
    with pytest.raises(RuntimeError, match="DATAFLOW_FRONTEND_DIST.*index.html"):
        app_with_build(monkeypatch, directory)


def test_configured_index_cannot_point_outside_build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    directory = tmp_path / "dist"
    directory.mkdir()
    outside = tmp_path / "index.html"
    outside.write_text("outside index")
    (directory / "index.html").symlink_to(outside)
    with pytest.raises(RuntimeError, match="DATAFLOW_FRONTEND_DIST"):
        app_with_build(monkeypatch, directory)


def test_frontend_dist_environment_variable(monkeypatch: pytest.MonkeyPatch, frontend_dist: Path):
    monkeypatch.setenv("DATAFLOW_FRONTEND_DIST", str(frontend_dist))
    assert Settings(_env_file=None).frontend_dist == frontend_dist
