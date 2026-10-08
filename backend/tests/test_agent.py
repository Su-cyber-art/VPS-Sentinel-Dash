import concurrent.futures
import json
from pathlib import Path
import time
from unittest.mock import patch
import pytest

from agent.sentinel_agent import Agent, atomic_json, check_master
from sentinel_api.models import Policy
from conftest import enroll, enqueue, heartbeat


def make_agent(admin):
    node, _ = enroll(admin["client"])
    config = admin["root"] / "agent.json"
    atomic_json(config, dict(node, master="http://192.0.2.10:8080", root=str(admin["root"] / "modules")))
    return node, Agent(config)


def bridge(client):
    def call(master, path, payload, token=None):
        response = client.post(path, json=payload, headers={"Authorization": "Bearer " + token} if token else {})
        assert response.status_code == 200, response.text
        return response.json()
    return call


def test_outbound_agent_snapshot_roundtrip_and_durable_retry(admin):
    client = admin["client"]
    node, agent = make_agent(admin)
    try:
        with patch("agent.sentinel_agent.call", side_effect=bridge(client)):
            agent.tick()
            task_id = enqueue(client, node)
            agent.tick(); agent.future.result(timeout=5)
        with patch("agent.sentinel_agent.call", side_effect=OSError("connection lost")):
            with pytest.raises(OSError): agent.tick()
        assert json.loads(agent.state_path.read_text())["pending"]["id"] == task_id
        restarted = Agent(agent.config_path)
        try:
            with patch("agent.sentinel_agent.call", side_effect=bridge(client)): restarted.tick()
            task = client.get("/api/jobs/" + task_id).json()
            assert task["status"] == "succeeded" and "disk_used_percent" in task["result"]
            assert "pending" not in restarted.state
        finally: restarted.executor.shutdown()
    finally: agent.executor.shutdown()


def test_policy_failure_is_reported_instead_of_silently_losing_task(admin):
    client = admin["client"]
    node, agent = make_agent(admin)
    heartbeat(client, node)
    task_id = enqueue(client, node)
    try:
        with patch("agent.sentinel_agent.call", side_effect=bridge(client)):
            with patch.object(agent, "sync_policy", side_effect=ValueError("missing data")):
                with pytest.raises(ValueError): agent.tick()
            agent.tick()
        result = client.get("/api/jobs/" + task_id).json()
        assert result["status"] == "failed" and "missing data" in result["result"]["error"]
    finally: agent.executor.shutdown()


def test_shell_module_dispatch_and_process_cancellation(admin):
    node, agent = make_agent(admin)
    agent.root.mkdir()
    core = agent.root / "core"; core.mkdir()
    (core / "mod_google.sh").write_text('#!/bin/bash\nprintf "sentinel-fixture-ran\\n"\n')
    (core / "mod_trust.sh").write_text('#!/bin/bash\nsleep 60\n')
    try:
        with patch("agent.sentinel_agent.platform.system", return_value="Linux"):
            result = agent.execute({"action": "google"}, {"google": True})
            assert result["ok"] and "sentinel-fixture-ran" in result["result"]["text"]
            result = agent.execute({"action": "google"}, {"google": False})
            assert not result["ok"]
            future = agent.executor.submit(agent.execute, {"action": "trust"}, {"trust": True})
            time.sleep(0.3)
            agent.cancel_event.set()
            result = future.result(timeout=5)
            assert result["cancelled"] is True and result["ok"] is False
    finally: agent.executor.shutdown()


def test_region_paths_are_contained_and_shell_config_is_quoted(admin):
    node, agent = make_agent(admin)
    agent.root = admin["root"] / "modules with spaces"
    (agent.root / "core").mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / "data/regions/US/CA/Los_Angeles.json"
    target = agent.root / "data/regions/US/CA/Los_Angeles.json"
    target.parent.mkdir(parents=True); target.write_bytes(source.read_bytes())
    try:
        policy = Policy().model_dump()
        agent.sync_policy(policy)
        config = agent.root / "config.conf"
        assert config.stat().st_mode & 0o777 == 0o600
        assert "REGION_JSON_PATH='" + str(target.resolve()) + "'" in config.read_text()
        with pytest.raises(ValueError): agent.sync_policy(dict(policy, region_path="../../outside.json"))
    finally: agent.executor.shutdown()


def test_http_remote_agent_supported_and_malformed_urls_rejected():
    assert check_master("http://192.0.2.10:8080/") == "http://192.0.2.10:8080"
    assert check_master("https://sentinel.example.com") == "https://sentinel.example.com"
    for value in ("ftp://host", "http://u:p@host", "https://host/path", "http://host:wrong", "http://host\n"):
        with pytest.raises(ValueError): check_master(value)
