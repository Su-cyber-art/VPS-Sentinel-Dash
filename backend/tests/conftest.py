from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from sentinel_api.cli import provision
from sentinel_api.config import Config
from sentinel_api.main import create_app


@pytest.fixture
def environment(tmp_path):
    initial = provision(tmp_path / "state")
    config = Config(data_dir=tmp_path / "state", maintenance=False)
    with TestClient(create_app(config)) as client:
        yield {"client": client, "initial": initial["initial_password"], "data": tmp_path / "state", "root": tmp_path,
               "control": client.app.state.service}


def login(client, password, username="admin"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()


@pytest.fixture
def admin(environment):
    client = environment["client"]
    login(client, environment["initial"])
    response = client.post("/api/auth/password", json={"current_password": environment["initial"], "new_password": "changed-test-password-2026"})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    environment["password"] = "changed-test-password-2026"
    return environment


def enroll(client, name="Test node"):
    response = client.post("/api/enrollments", json={"name": name})
    assert response.status_code == 201, response.text
    issued = response.json()
    response = client.post("/api/agent/enroll", json={"token": issued["token"]})
    assert response.status_code == 200, response.text
    return response.json(), issued


def heartbeat(client, node, active=None, capabilities=None):
    return client.post("/api/agent/heartbeat", headers={"Authorization": "Bearer " + node["token"]}, json={
        "metrics": {"load_1m": 0.25}, "hostname": "test-host", "platform": "Linux", "version": "0.2.0",
        "capabilities": capabilities or ["snapshot", "network", "logs"], "active_job": active,
    })


def enqueue(client, node, action="snapshot"):
    response = client.post("/api/nodes/" + node["id"] + "/jobs", json={"action": action})
    assert response.status_code == 202, response.text
    return response.json()["id"]
