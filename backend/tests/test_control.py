import concurrent.futures
import json
import time
from unittest.mock import patch
from sentinel_api.models import Policy
from sentinel_api.security import digest
from conftest import enroll, heartbeat, enqueue


def test_enrollment_one_use_expiry_and_secret_redaction(admin):
    client = admin["client"]
    node, issued = enroll(client)
    assert client.post("/api/agent/enroll", json={"token": issued["token"]}).status_code == 403
    issued = client.post("/api/enrollments", json={"name": "Expired"}).json()
    with admin["control"].database.connect(write=True) as db:
        db.execute("UPDATE enrollments SET expires=0 WHERE token=?", (digest(issued["token"]),))
    assert client.post("/api/agent/enroll", json={"token": issued["token"]}).status_code == 403
    content = client.get("/api/overview").text
    assert node["token"] not in content and issued["token"] not in content


def test_task_ownership_claim_and_idempotent_result(admin):
    client = admin["client"]
    node, _ = enroll(client)
    other, _ = enroll(client, "Other")
    heartbeat(client, node)
    task_id = enqueue(client, node)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(lambda _: heartbeat(client, node).json(), range(6)))
    claimed = [v["job"] for v in values if v["job"]]
    assert len(claimed) == 1 and claimed[0]["id"] == task_id
    job = claimed[0]
    payload = dict(job, ok=True, result={"checked": True})
    assert client.post("/api/agent/result", json=payload, headers={"Authorization": "Bearer " + other["token"]}).status_code == 404
    assert client.post("/api/agent/result", json=payload, headers={"Authorization": "Bearer " + node["token"]}).status_code == 200
    assert client.post("/api/agent/result", json=payload, headers={"Authorization": "Bearer " + node["token"]}).json()["already_finished"]
    result = client.get("/api/jobs/" + task_id).json()
    assert result["status"] == "succeeded" and "lease" not in result


def test_revoke_agent_and_cancel_pending_work(admin):
    client = admin["client"]
    node, _ = enroll(client)
    heartbeat(client, node)
    task_id = enqueue(client, node)
    assert client.delete("/api/nodes/" + node["id"]).status_code == 200
    assert heartbeat(client, node).status_code == 401
    assert client.get("/api/jobs/" + task_id).json()["status"] == "failed"


def test_cancel_queued_and_running_tasks(admin):
    client = admin["client"]
    node, _ = enroll(client)
    heartbeat(client, node)
    queued = enqueue(client, node)
    assert client.post("/api/jobs/" + queued + "/cancel", json={}).status_code == 200
    assert heartbeat(client, node).json()["job"] is None
    assert client.get("/api/jobs/" + queued).json()["status"] == "cancelled"
    running = enqueue(client, node)
    job = heartbeat(client, node).json()["job"]
    assert client.post("/api/jobs/" + running + "/cancel", json={}).status_code == 200
    assert heartbeat(client, node, job).json()["cancel_job"] == running
    result = client.post("/api/agent/result", headers={"Authorization": "Bearer " + node["token"]}, json=dict(job, ok=False, cancelled=True, result={"message": "stopped"}))
    assert result.status_code == 200
    assert client.get("/api/jobs/" + running).json()["status"] == "cancelled"


def test_policies_scheduling_and_module_authorization(admin):
    client = admin["client"]
    node, _ = enroll(client)
    heartbeat(client, node, capabilities=["snapshot", "google", "trust", "patrol"])
    endpoint = "/api/nodes/" + node["id"]
    assert client.post(endpoint + "/jobs", json={"action": "google"}).status_code == 409
    assert client.post(endpoint + "/jobs", json={"action": "patrol"}).status_code == 409
    policy = Policy(google=True, interval_minutes=5, scheduled_action="patrol").model_dump()
    data = {"name": "configured", "region": "Tokyo", "group_name": "Ops", "policy": policy}
    assert client.patch(endpoint, json=data).status_code == 200
    assert heartbeat(client, node, capabilities=["snapshot", "google", "trust", "patrol"]).json()["policy"]["google"] is True
    with admin["control"].database.connect(write=True) as db:
        db.execute("UPDATE nodes SET last_scheduled=0 WHERE id=?", (node["id"],))
    admin["control"].maintenance(); admin["control"].maintenance()
    jobs = client.get("/api/overview").json()["jobs"]
    assert len(jobs) == 1 and jobs[0]["action"] == "patrol" and jobs[0]["source"] == "schedule"
    for key, value in (("interval_minutes", 1), ("interval_minutes", True), ("google", "yes"), ("region_path", "../../etc/passwd"), ("scheduled_action", "arbitrary-command")):
        response = client.patch(endpoint, json=dict(data, policy=dict(policy, **{key: value})))
        assert response.status_code in (400, 422), response.text


def test_batch_reports_each_node_and_queue_limit(admin):
    client = admin["client"]
    node, _ = enroll(client)
    heartbeat(client, node)
    response = client.post("/api/jobs/batch", json={"node_ids": [node["id"], "missing", node["id"]], "action": "snapshot"})
    results = response.json()["results"]
    assert len(results) == 2 and "id" in results[0] and "error" in results[1]
    for _ in range(9): enqueue(client, node)
    assert client.post("/api/nodes/" + node["id"] + "/jobs", json={"action": "snapshot"}).status_code == 409


def test_expired_task_is_not_reexecuted_and_recovery_events_are_unique(admin):
    client = admin["client"]
    node, _ = enroll(client)
    heartbeat(client, node)
    task_id = enqueue(client, node)
    heartbeat(client, node)
    with admin["control"].database.connect(write=True) as db:
        db.execute("UPDATE jobs SET lease_expires=0 WHERE id=?", (task_id,))
        db.execute("UPDATE nodes SET seen=?,created=? WHERE id=?", (time.time()-100, time.time()-100, node["id"]))
    admin["control"].maintenance(); admin["control"].maintenance()
    assert client.get("/api/jobs/" + task_id).json()["status"] == "failed"
    assert heartbeat(client, node).json()["job"] is None
    events = client.get("/api/overview").json()["events"]
    assert sum(e["kind"] == "node.offline" for e in events) == 1
    assert sum(e["kind"] == "node.recovered" for e in events) == 1
    with patch("sentinel_api.service.urlopen") as mocked:
        admin["control"].notify_one()
        mocked.assert_not_called()


def test_request_limits_and_downloads(admin):
    client = admin["client"]
    assert client.post("/api/auth/login", json=["wrong"]).status_code == 422
    assert client.post("/api/auth/login", json={"username": "a", "password": "a" * 300000}).status_code == 413
    assert client.post("/api/enrollments", content='{"name":"wrong"}', headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.get("/downloads/agent.py").status_code == 200
    assert client.get("/downloads/modules.tar.gz").status_code == 200
    assert client.get("/api/openapi.json").json()["info"]["title"] == "VPS Sentinel API"
    assert client.get("/").status_code == 404  # The API never serves a frontend.
