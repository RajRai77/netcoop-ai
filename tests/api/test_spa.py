"""Optional single-origin serving of the built React app (NETCOOP_FRONTEND_DIST)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from netcoop.api.app import create_app
from netcoop.config import Settings


def _client(tmp_path, dist=None):
    url = f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}"
    return TestClient(create_app(Settings(database_url=url, frontend_dist=str(dist) if dist else None)))


def _dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>NetCoop AI · Network Intelligence</title>", encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    return d


def test_default_serves_minimal_ui(tmp_path):
    c = _client(tmp_path)
    r = c.get("/")
    assert r.status_code == 200 and "NetCoop AI" in r.text
    assert c.get("/command").status_code == 404


def test_react_app_routes_and_api_precedence(tmp_path):
    c = _client(tmp_path, _dist(tmp_path))
    for path in ("/", "/command", "/report", "/topology"):
        r = c.get(path)
        assert r.status_code == 200 and "Network Intelligence" in r.text, path
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/legacy").status_code == 200
    assert c.get("/health/live").status_code == 200
    assert c.get("/api/meta").status_code == 200
    assert c.get("/api/does-not-exist").status_code == 404
    assert c.get("/health/nope").status_code == 404


def test_no_path_traversal(tmp_path):
    c = _client(tmp_path, _dist(tmp_path))
    r = c.get("/..%2Fsecret.txt")
    assert "outside" not in r.text
