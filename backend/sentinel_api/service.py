import json
import logging
import secrets
import time
from urllib.request import Request, urlopen

from .config import VERSION
from .database import Database, encode
from .errors import APIError
from .models import Policy
from .security import digest

ACTIONS = {"snapshot", "network", "logs", "google", "trust", "quality", "patrol", "update_data"}


class ControlPlane:
    def __init__(self, config):
        self.config = config
        self.database = Database(config.data_dir)

    def event(self, db, kind, message, node_id=None, notify=False):
        notify = notify and Database.get(db, "telegram_enabled", False)
        db.execute("INSERT INTO events(created,kind,node_id,message,notify) VALUES (?,?,?,?,?)",
                   (time.time(), kind, node_id, message, int(notify)))

    def regions(self):
        base = self.config.root / "data" / "regions"
        result = []
        for path in sorted(base.rglob("*.json")):
            value = json.loads(path.read_text())
            if "google_module" in value:
                result.append({"path": path.relative_to(base).as_posix(), "name": value.get("region_name", path.stem)})
        return result

    @staticmethod
    def node(db, node_id):
        row = db.execute("SELECT * FROM nodes WHERE id=? AND revoked=0", (node_id,)).fetchone()
        if not row:
            raise APIError(404, "节点不存在")
        return row

    @staticmethod
    def node_json(row):
        result = dict(row)
        result.pop("token", None)
        for key in ("metrics", "policy", "capabilities"):
            result[key] = json.loads(result[key])
        result["online"] = time.time() - result["seen"] < 75
        return result

    @staticmethod
    def agent(db, authorization):
        if not authorization.startswith("Bearer "):
            raise APIError(401, "Agent token required")
        row = db.execute("SELECT * FROM nodes WHERE token=? AND revoked=0", (digest(authorization[7:]),)).fetchone()
        if not row:
            raise APIError(401, "Agent token invalid or revoked")
        return row

    def overview(self):
        now = time.time()
        with self.database.connect() as db:
            nodes = [self.node_json(r) for r in db.execute("SELECT * FROM nodes WHERE revoked=0 ORDER BY created")]
            jobs = [dict(r) for r in db.execute("SELECT j.id,j.node_id,j.action,j.status,j.created,j.started,j.finished,j.source,j.cancel_requested,n.name AS node_name FROM jobs j LEFT JOIN nodes n ON n.id=j.node_id ORDER BY j.created DESC LIMIT 200")]
            events = [dict(r) for r in db.execute("SELECT id,created,kind,node_id,message FROM events ORDER BY id DESC LIMIT 200")]
            counts = dict(db.execute("SELECT status,COUNT(*) FROM jobs WHERE created>? GROUP BY status", (now - 86400,)).fetchall())
            hours = [0] * 24
            for row in db.execute("SELECT created FROM jobs WHERE created>?", (now - 86400,)):
                index = 23 - int((now - row[0]) // 3600)
                if 0 <= index < 24:
                    hours[index] += 1
            pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        return {"nodes": nodes, "jobs": jobs, "events": events, "counts": counts, "hours": hours,
                "pending_count": pending, "version": VERSION, "server_time": now}

    def enrollment(self, name):
        token, expires = secrets.token_urlsafe(24), time.time() + 900
        with self.database.connect(write=True) as db:
            db.execute("INSERT INTO enrollments VALUES (?,?,?)", (digest(token), name, expires))
            self.event(db, "enrollment.created", "已为 %s 生成接入令牌（15 分钟有效）" % name)
        return {"token": token, "expires": expires, "master_url": self.config.public_url}

    def register_agent(self, token):
        with self.database.connect(write=True) as db:
            row = db.execute("SELECT * FROM enrollments WHERE token=? AND expires>?", (digest(token), time.time())).fetchone()
            if not row:
                raise APIError(403, "接入令牌已使用或已过期")
            node_id, credential = secrets.token_hex(10), secrets.token_urlsafe(32)
            db.execute("INSERT INTO nodes(id,token,name,created,policy) VALUES (?,?,?,?,?)",
                       (node_id, digest(credential), row["name"], time.time(), encode(Policy().model_dump())))
            db.execute("DELETE FROM enrollments WHERE token=?", (digest(token),))
            self.event(db, "node.enrolled", "%s 已接入" % row["name"], node_id)
        return {"id": node_id, "token": credential}

    def heartbeat(self, authorization, data):
        now = time.time()
        if len(encode(data.metrics).encode()) > 16000:
            raise APIError(400, "Metrics payload too large")
        with self.database.connect(write=True) as db:
            node = self.agent(db, authorization)
            db.execute("UPDATE nodes SET seen=?,metrics=?,hostname=?,platform=?,version=?,capabilities=?,offline_alert=0 WHERE id=?",
                       (now, encode(data.metrics), data.hostname, data.platform, data.version, encode(data.capabilities), node["id"]))
            if node["offline_alert"]:
                self.event(db, "node.recovered", "%s 已恢复连接" % node["name"], node["id"], True)
            active, cancel_job = data.active_job, None
            if active:
                db.execute("UPDATE jobs SET lease_expires=? WHERE id=? AND node_id=? AND lease=? AND status='running'",
                           (now + 120, active.id, node["id"], active.lease))
                task = db.execute("SELECT cancel_requested,status FROM jobs WHERE id=? AND node_id=? AND lease=?",
                                  (active.id, node["id"], active.lease)).fetchone()
                if task and (task["cancel_requested"] or task["status"] == "cancelled"):
                    cancel_job = active.id
            job = None
            if not active and not db.execute("SELECT 1 FROM jobs WHERE node_id=? AND status='running'", (node["id"],)).fetchone():
                row = db.execute("SELECT * FROM jobs WHERE node_id=? AND status='queued' ORDER BY created LIMIT 1", (node["id"],)).fetchone()
                if row:
                    lease = secrets.token_urlsafe(24)
                    db.execute("UPDATE jobs SET status='running',started=?,lease=?,lease_expires=? WHERE id=?", (now, lease, now + 120, row["id"]))
                    job = {"id": row["id"], "action": row["action"], "lease": lease}
            return {"policy": json.loads(node["policy"]), "job": job, "cancel_job": cancel_job, "heartbeat_seconds": 15}

    def complete_task(self, authorization, data):
        if len(encode(data.result).encode()) > 220000:
            raise APIError(400, "Result payload too large")
        with self.database.connect(write=True) as db:
            node = self.agent(db, authorization)
            task = db.execute("SELECT * FROM jobs WHERE id=? AND node_id=? AND lease=?", (data.id, node["id"], data.lease)).fetchone()
            if not task:
                raise APIError(404, "Task lease not found")
            if task["status"] in ("succeeded", "failed", "cancelled"):
                return {"ok": True, "already_finished": True}
            if task["status"] != "running":
                raise APIError(409, "Task is not running")
            status = "cancelled" if data.cancelled else "succeeded" if data.ok else "failed"
            db.execute("UPDATE jobs SET status=?,finished=?,result=? WHERE id=?", (status, time.time(), encode(data.result), task["id"]))
            self.event(db, "job." + status, "%s · %s %s" % (node["name"], task["action"],
                       {"succeeded": "已完成", "failed": "执行失败", "cancelled": "已取消"}[status]), node["id"], status == "failed")
        return {"ok": True}

    def enqueue(self, db, node, action, source="manual"):
        if action not in json.loads(node["capabilities"]):
            raise APIError(409, "该 Agent 尚未安装此模块")
        policy = json.loads(node["policy"])
        if action in ("google", "trust") and not policy[action]:
            raise APIError(409, "请先启用此哨兵模块")
        if action == "patrol" and not (policy["google"] or policy["trust"]):
            raise APIError(409, "巡逻需要至少启用一个哨兵模块")
        count = db.execute("SELECT COUNT(*) FROM jobs WHERE node_id=? AND status IN ('queued','running')", (node["id"],)).fetchone()[0]
        if count >= 10:
            raise APIError(409, "该节点的待执行任务过多")
        task_id = secrets.token_hex(12)
        db.execute("INSERT INTO jobs(id,node_id,action,status,created,source) VALUES (?,?,?,'queued',?,?)", (task_id, node["id"], action, time.time(), source))
        self.event(db, "job.queued", "%s · 已安排 %s" % (node["name"], action), node["id"])
        return task_id

    def create_task(self, node_id, action):
        with self.database.connect(write=True) as db:
            return {"id": self.enqueue(db, self.node(db, node_id), action)}

    def batch_tasks(self, node_ids, action):
        results = []
        for node_id in dict.fromkeys(node_ids):
            try:
                results.append({"node_id": node_id, **self.create_task(node_id, action)})
            except APIError as error:
                results.append({"node_id": node_id, "error": str(error)})
        return {"results": results}

    def update_node(self, node_id, data):
        policy = data.policy.model_dump()
        if policy["region_path"] not in {r["path"] for r in self.regions()}:
            raise APIError(400, "请选择有效的目标地区")
        with self.database.connect(write=True) as db:
            node = self.node(db, node_id)
            action = policy["scheduled_action"]
            if policy["interval_minutes"] and (action not in json.loads(node["capabilities"]) or
                    (action in ("google", "trust") and not policy[action]) or
                    (action == "patrol" and not (policy["google"] or policy["trust"]))):
                raise APIError(400, "请先安装并启用定时任务对应的模块")
            db.execute("UPDATE nodes SET name=?,region=?,group_name=?,policy=?,last_scheduled=? WHERE id=?", (data.name, data.region, data.group_name.strip() or "默认分组", encode(policy), time.time(), node_id))
            self.event(db, "node.updated", "%s 的策略已更新，下次心跳生效" % data.name, node_id)
        return {"ok": True}

    def remove_node(self, node_id):
        with self.database.connect(write=True) as db:
            node = self.node(db, node_id)
            db.execute("UPDATE nodes SET revoked=1 WHERE id=?", (node_id,))
            db.execute("UPDATE jobs SET status='failed',finished=?,result=? WHERE node_id=? AND status IN ('queued','running')", (time.time(), encode({"error": "节点已移除，凭证已撤销"}), node_id))
            self.event(db, "node.removed", "%s 已移除并撤销凭证" % node["name"], node_id)
        return {"ok": True}

    def task(self, task_id):
        with self.database.connect() as db:
            row = db.execute("SELECT j.*,n.name AS node_name FROM jobs j LEFT JOIN nodes n ON n.id=j.node_id WHERE j.id=?", (task_id,)).fetchone()
            if not row:
                raise APIError(404, "任务不存在")
            item = dict(row)
            item.pop("lease", None)
            item["result"] = json.loads(item["result"]) if item["result"] else None
            return item

    def cancel_task(self, task_id):
        with self.database.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise APIError(404, "任务不存在")
            if row["status"] == "queued":
                db.execute("UPDATE jobs SET status='cancelled',finished=?,cancel_requested=1,result=? WHERE id=?", (time.time(), encode({"message": "任务在执行前被取消"}), task_id))
            elif row["status"] == "running":
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (task_id,))
            else:
                raise APIError(409, "任务已结束")
            self.event(db, "job.cancel_requested", "已请求取消 %s 任务" % row["action"], row["node_id"])
        return {"ok": True}

    def settings(self):
        with self.database.connect() as db:
            return {"telegram_enabled": Database.get(db, "telegram_enabled", False),
                    "telegram_configured": self.config.telegram_configured,
                    "public_url": self.config.public_url, "version": VERSION}

    def update_settings(self, enabled):
        if enabled and not self.config.telegram_configured:
            raise APIError(400, "请先在主控环境文件中配置 Telegram Token 和 Chat ID")
        with self.database.connect(write=True) as db:
            Database.set(db, "telegram_enabled", enabled)
            self.event(db, "settings.updated", "Telegram 通知已%s" % ("开启" if enabled else "关闭"))
        return {"ok": True}

    def maintenance(self):
        now = time.time()
        with self.database.connect(write=True) as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            db.execute("DELETE FROM enrollments WHERE expires<?", (now,))
            for row in db.execute("SELECT * FROM jobs WHERE status='running' AND (lease_expires<? OR started<?)", (now, now - 1500)).fetchall():
                db.execute("UPDATE jobs SET status='failed',finished=?,result=? WHERE id=?", (now, encode({"error": "Agent 任务超时，未自动重试，请检查节点日志"}), row["id"]))
                self.event(db, "job.failed", "%s 任务超时" % row["action"], row["node_id"], True)
            for node in db.execute("SELECT * FROM nodes WHERE revoked=0").fetchall():
                if now - max(node["seen"], node["created"]) > 75 and not node["offline_alert"]:
                    db.execute("UPDATE nodes SET offline_alert=1 WHERE id=?", (node["id"],))
                    self.event(db, "node.offline", "%s 已离线" % node["name"], node["id"], True)
                policy = json.loads(node["policy"])
                if (policy["interval_minutes"] and now - node["seen"] < 75 and
                        now - node["last_scheduled"] >= policy["interval_minutes"] * 60 and
                        not db.execute("SELECT 1 FROM jobs WHERE node_id=? AND status IN ('queued','running')", (node["id"],)).fetchone()):
                    try:
                        self.enqueue(db, node, policy["scheduled_action"], "schedule")
                        db.execute("UPDATE nodes SET last_scheduled=? WHERE id=?", (now, node["id"]))
                    except APIError:
                        pass
            db.execute("DELETE FROM events WHERE created<? AND notify=0", (now - 30 * 86400,))
            db.execute("DELETE FROM jobs WHERE finished<?", (now - 30 * 86400,))

    def notify_one(self):
        with self.database.connect() as db:
            if not Database.get(db, "telegram_enabled", False):
                db.execute("UPDATE events SET notify=0 WHERE notify=1")
                return
            row = db.execute("SELECT * FROM events WHERE notify=1 AND attempts<3 ORDER BY id LIMIT 1").fetchone()
        if not row:
            return
        sent = False
        try:
            payload = encode({"chat_id": self.config.telegram_chat, "text": "VPS Sentinel\n" + row["message"]}).encode()
            req = Request("https://api.telegram.org/bot%s/sendMessage" % self.config.telegram_token, payload, {"Content-Type": "application/json"})
            with urlopen(req, timeout=6) as response:
                sent = bool(json.load(response).get("ok"))
        except Exception:
            logging.warning("Telegram event %s delivery failed", row["id"])
        with self.database.connect(write=True) as db:
            db.execute("UPDATE events SET attempts=attempts+1,notify=? WHERE id=?", (0 if sent or row["attempts"] >= 2 else 1, row["id"]))
            if not sent and row["attempts"] >= 2:
                self.event(db, "notification.failed", "Telegram 通知发送失败，请检查凭证和网络")
