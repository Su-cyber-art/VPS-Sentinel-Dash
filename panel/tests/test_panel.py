"""HTTP integration tests with a real local Agent; no external services contacted."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from panel.agent import Agent, atomic_json, check_master
from panel.server import DEFAULT_POLICY, Server, Store, digest, encode


class PanelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.password = "sentinel-test-password-2026"
        self.store = Store(Path(self.temp.name) / "master", admin_password=self.password)
        self.server = Server(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%s" % self.server.server_port
        self.cookie = ""
        self.csrf = ""
        status, result, headers = self.request("POST", "/api/login", {"password": self.password})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = result["csrf"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, data=None, auth=True, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        merged = {"Content-Type": "application/json"}
        if auth:
            merged.update(Cookie=self.cookie, **{"X-CSRF-Token": self.csrf})
        merged.update(headers or {})
        conn.request(method, path, json.dumps(data) if data is not None else None, merged)
        response = conn.getresponse()
        body = response.read()
        status, result_headers = response.status, dict(response.getheaders())
        conn.close()
        try:
            value = json.loads(body)
        except ValueError:
            value = body
        return status, value, result_headers

    def enroll(self, name="test-node"):
        status, value, _ = self.request("POST", "/api/enrollments", {"name": name})
        self.assertEqual(status, 200)
        enrollment = value["token"]
        status, node, _ = self.request("POST", "/api/agent/enroll", {"token": enrollment}, auth=False)
        self.assertEqual(status, 200)
        return node, enrollment

    def heartbeat(self, node, active=None):
        return self.request("POST", "/api/agent/heartbeat", {
            "metrics": {"load_1m": 0.5}, "hostname": "integration-host", "platform": "Linux",
            "version": "0.1.0", "capabilities": ["snapshot", "network", "logs"], "active_job": active,
        }, auth=False, headers={"Authorization": "Bearer " + node["token"]})

    def enqueue(self, node, action="snapshot"):
        status, value, _ = self.request("POST", "/api/nodes/" + node["id"] + "/jobs", {"action": action})
        self.assertEqual(status, 200, value)
        return value["id"]

    def result(self, node, job, ok=True):
        return self.request("POST", "/api/agent/result", dict(job, ok=ok, result={"checked": True}),
                            auth=False, headers={"Authorization": "Bearer " + node["token"]})

    def test_login_csrf_and_origin(self):
        self.assertEqual(self.request("GET", "/api/overview", auth=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/login", {"password": "wrong"})[0], 401)
        self.assertEqual(self.request("POST", "/api/enrollments", {"name": "bad"}, headers={"X-CSRF-Token": ""})[0], 403)
        self.assertEqual(self.request("POST", "/api/enrollments", {"name": "bad"}, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/setup", {"setup_token": self.store.setup_token, "password": self.password})[0], 409)
        self.assertEqual(self.request("GET", "/api/session")[1]["authenticated"], True)
        self.assertEqual(self.request("POST", "/api/logout", {})[0], 200)
        self.assertEqual(self.request("GET", "/api/overview")[0], 401)

    def test_enrollment_one_use_expiry_and_secret_redaction(self):
        node, token = self.enroll()
        self.assertEqual(self.request("POST", "/api/agent/enroll", {"token": token}, auth=False)[0], 403)
        _, issued, _ = self.request("POST", "/api/enrollments", {"name": "expires"})
        with self.store.db() as db:
            db.execute("UPDATE enrollments SET expires=0 WHERE token=?", (digest(issued["token"]),))
        self.assertEqual(self.request("POST", "/api/agent/enroll", {"token": issued["token"]}, auth=False)[0], 403)
        _, overview, _ = self.request("GET", "/api/overview")
        self.assertNotIn(node["token"], json.dumps(overview))
        self.assertNotIn("token", overview["nodes"][0])

    def test_task_ownership_idempotency_and_revocation(self):
        node, _ = self.enroll()
        other, _ = self.enroll("other")
        self.heartbeat(node)
        self.enqueue(node)
        _, response, _ = self.heartbeat(node)
        job = response["job"]
        self.assertIsNotNone(job)
        self.assertIsNone(self.heartbeat(node, active=job)[1]["job"])
        self.assertEqual(self.result(other, job)[0], 404)
        self.assertEqual(self.result(node, job)[0], 200)
        self.assertTrue(self.result(node, job)[1]["already_finished"])
        detail = self.request("GET", "/api/jobs/" + job["id"])[1]
        self.assertEqual(detail["status"], "succeeded")
        self.assertNotIn("lease", detail)
        self.assertEqual(self.request("DELETE", "/api/nodes/" + node["id"], {})[0], 200)
        self.assertEqual(self.heartbeat(node)[0], 401)

    def test_only_one_poll_can_claim_a_job(self):
        node, _ = self.enroll()
        self.heartbeat(node)
        self.enqueue(node)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: self.heartbeat(node), range(6)))
        self.assertTrue(all(r[0] == 200 for r in responses))
        self.assertEqual(sum(r[1]["job"] is not None for r in responses), 1)

    def test_agent_round_trip_and_durable_result_retry(self):
        node, _ = self.enroll()
        config = Path(self.temp.name) / "agent.json"
        atomic_json(config, dict(node, master=self.base, root=str(Path(self.temp.name) / "modules")))
        agent = Agent(config)
        try:
            agent.tick()
            jid = self.enqueue(node)
            agent.tick()
            agent.future.result(timeout=3)
            # A lost result upload must remain on disk, then be sent on the next tick.
            with patch("panel.agent.call", side_effect=OSError("temporary outage")):
                with self.assertRaises(OSError):
                    agent.tick()
            self.assertIn("pending", json.loads(agent.state_path.read_text()))
            restarted = Agent(config)
            try:
                restarted.tick()
                detail = self.request("GET", "/api/jobs/" + jid)[1]
                self.assertEqual(detail["status"], "succeeded")
                self.assertIn("disk_used_percent", detail["result"])
                self.assertNotIn("pending", restarted.state)
            finally:
                restarted.executor.shutdown()
        finally:
            agent.executor.shutdown()

    def test_expired_lease_is_failed_without_reexecution(self):
        node, _ = self.enroll()
        self.heartbeat(node)
        jid = self.enqueue(node)
        _, response, _ = self.heartbeat(node)
        with self.store.db() as db:
            db.execute("UPDATE jobs SET lease_expires=0 WHERE id=?", (jid,))
        self.store.maintenance()
        self.assertEqual(self.request("GET", "/api/jobs/" + jid)[1]["status"], "failed")
        self.assertIsNone(self.heartbeat(node)[1]["job"])
        self.assertTrue(self.result(node, response["job"])[1]["already_finished"])

    def test_policy_sync_failure_is_returned_as_task_failure(self):
        node, _ = self.enroll()
        self.heartbeat(node)
        jid = self.enqueue(node)
        config = Path(self.temp.name) / "agent.json"
        atomic_json(config, dict(node, master=self.base, root=str(Path(self.temp.name) / "modules")))
        agent = Agent(config)
        try:
            with patch.object(agent, "sync_policy", side_effect=ValueError("missing region")):
                with self.assertRaises(ValueError):
                    agent.tick()
            self.assertIn("pending", json.loads(agent.state_path.read_text()))
            agent.tick()
            detail = self.request("GET", "/api/jobs/" + jid)[1]
            self.assertEqual(detail["status"], "failed")
            self.assertIn("missing region", detail["result"]["error"])
        finally:
            agent.executor.shutdown()

    def test_region_config_quotes_paths_and_uses_selected_region(self):
        node, _ = self.enroll()
        root = Path(self.temp.name) / "modules with spaces"
        (root / "core").mkdir(parents=True)
        source = Path(__file__).resolve().parents[2] / "data" / "regions" / DEFAULT_POLICY["region_path"]
        target = root / "data" / "regions" / DEFAULT_POLICY["region_path"]
        target.parent.mkdir(parents=True)
        target.write_bytes(source.read_bytes())
        config = Path(self.temp.name) / "agent.json"
        atomic_json(config, dict(node, master=self.base, root=str(root)))
        agent = Agent(config)
        try:
            agent.sync_policy(DEFAULT_POLICY)
            text = (root / "config.conf").read_text()
            self.assertIn("REGION_JSON_PATH='" + str(target.resolve()) + "'", text)
            self.assertIn("ENABLE_GOOGLE=false", text)
            self.assertEqual((root / "config.conf").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                agent.sync_policy(dict(DEFAULT_POLICY, region_path="../../outside.json"))
        finally:
            agent.executor.shutdown()

    def test_policy_validation_and_scheduling(self):
        node, _ = self.enroll()
        self.heartbeat(node)
        policy = dict(DEFAULT_POLICY, interval_minutes=5)
        data = {"name": "scheduled", "region": "Tokyo", "group_name": "test", "policy": policy}
        endpoint = "/api/nodes/" + node["id"]
        self.assertEqual(self.request("PATCH", endpoint, data)[0], 200)
        with self.store.db() as db:
            db.execute("UPDATE nodes SET last_scheduled=0 WHERE id=?", (node["id"],))
        self.store.maintenance()
        self.store.maintenance()
        jobs = self.request("GET", "/api/overview")[1]["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "schedule")
        for key, invalid in (("interval_minutes", 1), ("interval_minutes", True),
                             ("region_path", "../../etc/passwd"), ("scheduled_action", "exec"), ("google", "yes")):
            changed = dict(data, policy=dict(policy, **{key: invalid}))
            self.assertEqual(self.request("PATCH", endpoint, changed)[0], 400)
        self.assertEqual(self.request("POST", endpoint + "/jobs", {"action": "rm -rf /"})[0], 400)
        self.assertEqual(self.request("POST", endpoint + "/jobs", {"action": "google"})[0], 409)

    def test_offline_recovery_events_and_disabled_notifications(self):
        node, _ = self.enroll()
        self.heartbeat(node)
        with self.store.db() as db:
            db.execute("UPDATE nodes SET seen=?,created=? WHERE id=?", (time.time()-100, time.time()-100, node["id"]))
        self.store.maintenance()
        self.store.maintenance()
        events = self.request("GET", "/api/overview")[1]["events"]
        self.assertEqual(sum(e["kind"] == "node.offline" for e in events), 1)
        self.heartbeat(node)
        events = self.request("GET", "/api/overview")[1]["events"]
        self.assertEqual(sum(e["kind"] == "node.recovered" for e in events), 1)
        with patch("panel.server.urlopen") as request:
            self.store.notify_one()
            request.assert_not_called()

    def test_password_change_invalidates_sessions(self):
        self.assertEqual(self.request("POST", "/api/password", {"current_password": "wrong", "new_password": "long-enough-password"})[0], 403)
        self.assertEqual(self.request("POST", "/api/password", {"current_password": self.password, "new_password": "new-long-enough-password"})[0], 200)
        self.assertEqual(self.request("GET", "/api/overview")[0], 401)
        self.assertEqual(self.request("POST", "/api/login", {"password": "new-long-enough-password"})[0], 200)

    def test_http_input_bounds_and_static_files(self):
        self.assertEqual(self.request("POST", "/api/login", ["not-an-object"])[0], 400)
        self.assertEqual(self.request("POST", "/api/login", {"password": "a"*300000})[0], 413)
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"IP Sentinel", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/../../etc/passwd")[0], 404)
        self.assertEqual(self.request("GET", "/download/agent.py")[0], 200)
        self.assertEqual(self.request("GET", "/download/modules.tar.gz")[0], 200)

    def test_agent_rejects_plaintext_remote_and_malformed_master(self):
        self.assertEqual(check_master("http://127.0.0.1:8080/"), "http://127.0.0.1:8080")
        self.assertEqual(check_master("https://sentinel.example.com"), "https://sentinel.example.com")
        for value in ("http://192.168.1.1:8080", "https://user:pass@example.com", "https://example.com/path", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                check_master(value)


if __name__ == "__main__":
    unittest.main()
