from pathlib import Path
import json
import secrets
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient

from sentinel_api.cli import provision
from sentinel_api.config import Config
from sentinel_api.database import Database, encode
from sentinel_api.main import create_app
from sentinel_api.security import password_hash, digest
from conftest import enroll, login


def test_initial_password_gates_all_administration(environment):
    client = environment["client"]
    result = login(client, environment["initial"])
    assert result["must_change_password"] is True
    for path in ("/api/overview", "/api/nodes", "/api/settings", "/api/regions", "/api/jobs/doesnotexist"):
        response = client.get(path)
        assert response.status_code == 403
        assert response.json()["code"] == "password_change_required"
    for method, path, payload in (
        ("POST", "/api/enrollments", {"name": "blocked"}),
        ("POST", "/api/nodes/anything/jobs", {"action": "snapshot"}),
        ("POST", "/api/jobs/batch", {"node_ids": ["node"], "action": "snapshot"}),
        ("POST", "/api/jobs/anything/cancel", {}),
        ("DELETE", "/api/nodes/anything", {}),
        ("PUT", "/api/settings", {"telegram_enabled": False}),
    ):
        response = client.request(method, path, json=payload)
        assert response.status_code == 403, (path, response.text)
    with environment["control"].database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0] == 0


def test_password_change_unlocks_access_rotates_session_and_rejects_old(environment):
    client = environment["client"]
    login(client, environment["initial"])
    old_cookie = client.cookies.get("sentinel_session")
    response = client.post("/api/auth/password", json={"current_password": environment["initial"], "new_password": environment["initial"]})
    assert response.status_code == 400
    response = client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "changed-password-2026"})
    assert response.status_code == 403
    response = client.post("/api/auth/password", json={"current_password": environment["initial"], "new_password": "changed-password-2026"})
    assert response.status_code == 200
    assert response.json()["must_change_password"] is False
    assert client.cookies.get("sentinel_session") != old_cookie
    assert client.get("/api/overview").status_code == 200
    assert client.get("/api/overview", headers={"Cookie": "sentinel_session=" + old_cookie}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": environment["initial"]}).status_code == 401
    assert login(client, "changed-password-2026")["must_change_password"] is False


def test_bootstrap_print_file_is_one_time_and_restart_preserves_password(tmp_path):
    password_file = tmp_path / "password"
    first = provision(tmp_path / "state", "operator", password_file)
    password = password_file.read_text()
    assert first == {"created": True, "username": "operator"}
    assert len(password) >= 20 and password_file.stat().st_mode & 0o777 == 0o600
    second = provision(tmp_path / "state", "different-name", tmp_path / "another-password")
    assert second == {"created": False, "username": "operator"}
    assert not (tmp_path / "another-password").exists()
    with TestClient(create_app(Config(data_dir=tmp_path / "state", maintenance=False))) as client:
        assert login(client, password, "operator")["must_change_password"] is True
    other = provision(tmp_path / "other")
    assert other["initial_password"] != password


def test_password_reset_invalidates_sessions_but_preserves_nodes(admin):
    client = admin["client"]
    node, _ = enroll(client)
    initial = provision(admin["data"], reset=True)["initial_password"]
    assert client.get("/api/overview").status_code == 401
    assert login(client, initial)["must_change_password"] is True
    with admin["control"].database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM nodes WHERE id=?", (node["id"],)).fetchone()[0] == 1


def test_cookie_flags_support_http_and_optional_https(tmp_path):
    initial = provision(tmp_path)["initial_password"]
    for address, secure in (("http://example.test:8080", False), ("https://example.test", True)):
        with TestClient(create_app(Config(data_dir=tmp_path, public_url=address, maintenance=False)), base_url=address) as client:
            response = client.post("/api/auth/login", json={"username": "admin", "password": initial})
            cookie = response.headers["set-cookie"]
            assert ("Secure" in cookie) is secure
            assert "HttpOnly" in cookie and "SameSite=strict" in cookie


def test_csrf_origin_and_proxy_compatibility(admin):
    client = admin["client"]
    assert client.get("/api/overview", headers={"Cookie": ""}).status_code == 401
    assert client.post("/api/enrollments", json={"name": "n"}, headers={"X-CSRF-Token": ""}).status_code == 403
    assert client.post("/api/enrollments", json={"name": "n"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/enrollments", json={"name": "n"}, headers={"Origin": "https://panel.example", "Host": "panel.example"}).status_code == 201
    assert client.post("/api/auth/login", json={"username": "测试", "password": admin["password"]}).status_code == 401


def test_login_rate_limit(environment):
    client = environment["client"]
    for _ in range(8):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": environment["initial"]}).status_code == 429


def test_v01_database_migration_preserves_nodes_and_forces_password_change(tmp_path):
    source = Path(__file__).resolve().parents[1] / "sentinel_api/schema.sql"
    db = sqlite3.connect(tmp_path / "sentinel.sqlite3")
    db.executescript(source.read_text())
    salt = secrets.token_hex(16)
    db.execute("INSERT INTO settings VALUES (?,?)", ("password", encode({"salt": salt, "hash": password_hash("v01-password-2026", salt)})))
    db.execute("INSERT INTO nodes(id,token,name,created,policy) VALUES (?,?,?,?,?)", ("node", digest("old-agent"), "Existing node", time.time(), "{}"))
    db.execute("INSERT INTO sessions VALUES (?,?,?)", ("old", "csrf", time.time()+100))
    db.commit(); db.close()
    with TestClient(create_app(Config(data_dir=tmp_path, maintenance=False))) as client:
        assert login(client, "v01-password-2026")["must_change_password"] is True
        with client.app.state.service.database.connect() as db:
            assert db.execute("SELECT name FROM nodes WHERE id='node'").fetchone()[0] == "Existing node"
            assert db.execute("SELECT COUNT(*) FROM sessions WHERE token='old'").fetchone()[0] == 0
            assert "cancel_requested" in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}


@pytest.mark.parametrize("value", ["ftp://host", "http://user:pw@host", "http://host/path", "http://host:wrong", "http://host\n"])
def test_public_url_rejects_malformed_origins(tmp_path, value):
    with pytest.raises(ValueError):
        Config(data_dir=tmp_path, public_url=value)
