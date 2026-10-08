#!/usr/bin/env python3
"""Single-operator control plane. Python 3.9+, SQLite, no pip dependencies."""
import argparse
import contextlib
import hashlib
import hmac
import io
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tarfile
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.0"
ACTIONS = {"snapshot", "network", "logs", "google", "trust", "quality"}
DEFAULT_POLICY = {"google": False, "trust": False, "interval_minutes": 0,
                  "scheduled_action": "snapshot", "region_path": "US/CA/Los_Angeles.json"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, csrf TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS enrollments (token TEXT PRIMARY KEY, name TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS nodes (
 id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 region TEXT DEFAULT '', group_name TEXT DEFAULT '默认分组', hostname TEXT DEFAULT '',
 platform TEXT DEFAULT '', version TEXT DEFAULT '', seen REAL DEFAULT 0,
 created REAL NOT NULL, metrics TEXT DEFAULT '{}', policy TEXT NOT NULL,
 capabilities TEXT DEFAULT '[]', last_scheduled REAL DEFAULT 0,
 offline_alert INTEGER DEFAULT 0, revoked INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, node_id TEXT NOT NULL, action TEXT NOT NULL,
 status TEXT NOT NULL, created REAL NOT NULL, started REAL, finished REAL,
 lease TEXT, lease_expires REAL, result TEXT, source TEXT DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS jobs_node ON jobs(node_id, status, created);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, kind TEXT, node_id TEXT,
 message TEXT, notify INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0
);
"""


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def label(value, limit=80):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise APIError(400, "请输入有效的名称（最多 %s 个字符）" % limit)
    return value.strip()


class Store:
    def __init__(self, directory, public_url="", admin_password=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "sentinel.sqlite3"
        self.public_url = public_url.rstrip("/")
        if self.public_url and (urlparse(self.public_url).scheme != "https" or
                                not urlparse(self.public_url).netloc):
            raise ValueError("SENTINEL_PUBLIC_URL must be an HTTPS origin")
        self.lock = threading.Lock()
        self.attempts = {}
        self.setup_token = os.environ.get("SENTINEL_SETUP_TOKEN") or secrets.token_urlsafe(24)
        with self.db() as db:
            db.executescript(SCHEMA)
            db.execute("PRAGMA journal_mode=WAL")
            if admin_password and not self.setting(db, "password"):
                self.set_password(db, admin_password)
        os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def setting(db, key, default=None):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def set_setting(db, key, value):
        db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, encode(value)))

    def set_password(self, db, password):
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise APIError(400, "管理密码需要 12–256 个字符")
        salt = secrets.token_hex(16)
        self.set_setting(db, "password", {"salt": salt, "hash": password_hash(password, salt)})

    def event(self, db, kind, message, node_id=None, notify=False):
        enabled = self.setting(db, "telegram_enabled", False)
        db.execute("INSERT INTO events(created,kind,node_id,message,notify) VALUES (?,?,?,?,?)",
                   (time.time(), kind, node_id, message, int(notify and enabled)))

    def session(self, db, cookie):
        jar = SimpleCookie()
        try:
            jar.load(cookie or "")
            token = jar["sentinel_session"].value
        except (KeyError, ValueError):
            raise APIError(401, "请先登录")
        row = db.execute("SELECT * FROM sessions WHERE token=? AND expires>?",
                         (digest(token), time.time())).fetchone()
        if not row:
            raise APIError(401, "登录已过期，请重新登录")
        return row

    def agent(self, db, bearer):
        if not bearer.startswith("Bearer "):
            raise APIError(401, "Agent token required")
        row = db.execute("SELECT * FROM nodes WHERE token=? AND revoked=0",
                         (digest(bearer[7:]),)).fetchone()
        if not row:
            raise APIError(401, "Agent token invalid or revoked")
        return row

    def login(self, data, setup, client):
        now = time.time()
        with self.lock:
            self.attempts = {k: v for k, v in self.attempts.items() if now - v[-1] < 60}
            attempts = [t for t in self.attempts.get(client, []) if now - t < 60]
            if len(attempts) >= 8:
                raise APIError(429, "尝试次数过多，请一分钟后再试")
            self.attempts[client] = attempts + [now]
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            saved = self.setting(db, "password")
            password = data.get("password", "")
            if setup:
                if saved:
                    raise APIError(409, "管理员已创建")
                token = data.get("setup_token", "")
                if not isinstance(token, str) or not hmac.compare_digest(token, self.setup_token):
                    raise APIError(403, "初始化密钥不正确，请查看主控启动终端")
                self.set_password(db, password)
                self.event(db, "admin.setup", "管理员账户已创建")
            elif not saved or not isinstance(password, str) or len(password) > 256 or not hmac.compare_digest(
                    saved["hash"], password_hash(password, saved["salt"])):
                raise APIError(401, "密码不正确")
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), csrf, now + 43200))
        return {"authenticated": True, "csrf": csrf}, token

    def regions(self):
        base = ROOT.parent / "data" / "regions"
        regions = []
        for path in sorted(base.rglob("*.json")):
            try:
                data = json.loads(path.read_text())
                if "google_module" in data:
                    regions.append({"path": str(path.relative_to(base)), "name": data.get("region_name", path.stem)})
            except (ValueError, OSError):
                continue
        return regions

    @staticmethod
    def node_json(row):
        item = dict(row)
        item.pop("token", None)
        for key in ("metrics", "policy", "capabilities"):
            item[key] = json.loads(item[key])
        item["online"] = time.time() - item["seen"] < 75
        return item

    def enqueue(self, db, node, action, source="manual"):
        if action not in ACTIONS:
            raise APIError(400, "不支持的任务")
        if action not in json.loads(node["capabilities"]):
            raise APIError(409, "该 Agent 尚未安装此模块，请查看接入说明")
        if action in ("google", "trust") and not json.loads(node["policy"])[action]:
            raise APIError(409, "请先在节点策略中启用此实验模块")
        count = db.execute("SELECT COUNT(*) FROM jobs WHERE node_id=? AND status IN ('queued','running')",
                           (node["id"],)).fetchone()[0]
        if count >= 10:
            raise APIError(409, "该节点的待执行任务过多")
        jid = secrets.token_hex(12)
        db.execute("INSERT INTO jobs(id,node_id,action,status,created,source) VALUES (?,?,?,'queued',?,?)",
                   (jid, node["id"], action, time.time(), source))
        self.event(db, "job.queued", "%s · 已安排 %s" % (node["name"], action), node["id"])
        return jid

    def heartbeat(self, db, node, data):
        now = time.time()
        metrics = data.get("metrics", {})
        capabilities = data.get("capabilities", [])
        if not isinstance(metrics, dict) or len(encode(metrics)) > 16000:
            raise APIError(400, "Invalid metrics")
        if not isinstance(capabilities, list) or any(x not in ACTIONS for x in capabilities):
            raise APIError(400, "Invalid capabilities")
        db.execute("UPDATE nodes SET seen=?,metrics=?,hostname=?,platform=?,version=?,capabilities=?,offline_alert=0 WHERE id=?",
                   (now, encode(metrics), str(data.get("hostname", ""))[:120],
                    str(data.get("platform", ""))[:120], str(data.get("version", ""))[:30],
                    encode(capabilities), node["id"]))
        if node["offline_alert"]:
            self.event(db, "node.recovered", "%s 已恢复连接" % node["name"], node["id"], True)
        active = data.get("active_job")
        if isinstance(active, dict):
            db.execute("UPDATE jobs SET lease_expires=? WHERE id=? AND node_id=? AND lease=? AND status='running'",
                       (now + 120, active.get("id"), node["id"], active.get("lease")))
        job = None
        if not active and not db.execute("SELECT 1 FROM jobs WHERE node_id=? AND status='running'", (node["id"],)).fetchone():
            row = db.execute("SELECT * FROM jobs WHERE node_id=? AND status='queued' ORDER BY created LIMIT 1",
                             (node["id"],)).fetchone()
            if row:
                lease = secrets.token_urlsafe(24)
                db.execute("UPDATE jobs SET status='running',started=?,lease=?,lease_expires=? WHERE id=?",
                           (now, lease, now + 120, row["id"]))
                job = {"id": row["id"], "action": row["action"], "lease": lease}
        return {"policy": json.loads(node["policy"]), "job": job, "heartbeat_seconds": 15}

    def api(self, method, path, data, headers, client):
        with self.db() as db:
            if path == "/api/session" and method == "GET":
                configured = bool(self.setting(db, "password"))
                try:
                    session = self.session(db, headers.get("Cookie"))
                    return {"configured": configured, "authenticated": True, "csrf": session["csrf"]}
                except APIError:
                    return {"configured": configured, "authenticated": False}
            if path == "/api/agent/enroll" and method == "POST":
                token = data.get("token", "")
                if not isinstance(token, str):
                    raise APIError(400, "Invalid enrollment token")
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM enrollments WHERE token=? AND expires>?", (digest(token), time.time())).fetchone()
                if not row:
                    raise APIError(403, "接入令牌已使用或已过期")
                nid, credential = secrets.token_hex(10), secrets.token_urlsafe(32)
                db.execute("INSERT INTO nodes(id,token,name,created,policy) VALUES (?,?,?,?,?)",
                           (nid, digest(credential), row["name"], time.time(), encode(DEFAULT_POLICY)))
                db.execute("DELETE FROM enrollments WHERE token=?", (digest(token),))
                self.event(db, "node.enrolled", "%s 已接入" % row["name"], nid)
                return {"id": nid, "token": credential}
            if path.startswith("/api/agent/"):
                db.execute("BEGIN IMMEDIATE")
                node = self.agent(db, headers.get("Authorization", ""))
                if path == "/api/agent/heartbeat" and method == "POST":
                    return self.heartbeat(db, node, data)
                if path == "/api/agent/result" and method == "POST":
                    row = db.execute("SELECT * FROM jobs WHERE id=? AND node_id=? AND lease=?",
                                     (data.get("id"), node["id"], data.get("lease"))).fetchone()
                    if not row:
                        raise APIError(404, "Task lease not found")
                    if row["status"] in ("succeeded", "failed"):
                        return {"ok": True, "already_finished": True}
                    if row["status"] != "running":
                        raise APIError(409, "Task is not running")
                    result = data.get("result")
                    if not isinstance(result, dict) or len(encode(result).encode()) > 220000:
                        raise APIError(400, "Invalid result")
                    status = "succeeded" if data.get("ok") is True else "failed"
                    db.execute("UPDATE jobs SET status=?,finished=?,result=? WHERE id=?",
                               (status, time.time(), encode(result), row["id"]))
                    self.event(db, "job." + status, "%s · %s %s" % (node["name"], row["action"],
                               "已完成" if status == "succeeded" else "执行失败"), node["id"], status == "failed")
                    return {"ok": True}
                raise APIError(404, "Unknown agent endpoint")
            session = self.session(db, headers.get("Cookie"))
            if method != "GET":
                if not hmac.compare_digest(headers.get("X-CSRF-Token", ""), session["csrf"]):
                    raise APIError(403, "页面凭证已失效，请刷新页面")
                db.execute("BEGIN IMMEDIATE")
            if path == "/api/logout" and method == "POST":
                db.execute("DELETE FROM sessions WHERE token=?", (session["token"],))
                return {"ok": True}
            if path == "/api/overview" and method == "GET":
                nodes = [self.node_json(r) for r in db.execute("SELECT * FROM nodes WHERE revoked=0 ORDER BY created")]
                jobs = [dict(r) for r in db.execute("SELECT j.id,j.node_id,j.action,j.status,j.created,j.started,j.finished,j.source,n.name AS node_name FROM jobs j LEFT JOIN nodes n ON n.id=j.node_id ORDER BY j.created DESC LIMIT 200")]
                events = [dict(r) for r in db.execute("SELECT id,created,kind,node_id,message FROM events ORDER BY id DESC LIMIT 200")]
                counts = dict(db.execute("SELECT status,COUNT(*) FROM jobs WHERE created>? GROUP BY status", (time.time() - 86400,)).fetchall())
                hours = [0] * 24
                for row in db.execute("SELECT created FROM jobs WHERE created>?", (time.time() - 86400,)):
                    index = 23 - int((time.time() - row[0]) // 3600)
                    if 0 <= index < 24:
                        hours[index] += 1
                pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
                return {"nodes": nodes, "jobs": jobs, "events": events, "counts": counts, "hours": hours, "pending_count": pending,
                        "version": VERSION, "server_time": time.time()}
            if path == "/api/enrollments" and method == "POST":
                name = label(data.get("name"))
                token = secrets.token_urlsafe(24)
                db.execute("INSERT INTO enrollments VALUES (?,?,?)", (digest(token), name, time.time() + 900))
                self.event(db, "enrollment.created", "已为 %s 生成接入令牌（15 分钟有效）" % name)
                return {"token": token, "expires": time.time() + 900, "master_url": self.public_url}
            if path == "/api/regions" and method == "GET":
                return {"regions": self.regions()}
            if path == "/api/settings":
                if method == "GET":
                    return {"telegram_enabled": self.setting(db, "telegram_enabled", False),
                            "telegram_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
                            "public_url": self.public_url, "version": VERSION}
                if method == "POST":
                    enabled = data.get("telegram_enabled")
                    if not isinstance(enabled, bool):
                        raise APIError(400, "无效的通知设置")
                    if enabled and not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
                        raise APIError(400, "请先在主控环境变量中设置 Telegram Token 和 Chat ID")
                    self.set_setting(db, "telegram_enabled", enabled)
                    self.event(db, "settings.updated", "Telegram 通知已%s" % ("开启" if enabled else "关闭"))
                    return {"ok": True}
            if path == "/api/password" and method == "POST":
                saved = self.setting(db, "password")
                old = data.get("current_password", "")
                if not isinstance(old, str) or len(old) > 256 or not hmac.compare_digest(password_hash(old, saved["salt"]), saved["hash"]):
                    raise APIError(403, "当前密码不正确")
                self.set_password(db, data.get("new_password"))
                db.execute("DELETE FROM sessions")
                self.event(db, "admin.password", "管理密码已修改，全部会话已退出")
                return {"ok": True}
            match = re.fullmatch(r"/api/nodes/([a-f0-9]+)/?(jobs)?", path)
            if match:
                node = db.execute("SELECT * FROM nodes WHERE id=? AND revoked=0", (match[1],)).fetchone()
                if not node:
                    raise APIError(404, "节点不存在")
                if match[2] and method == "POST":
                    return {"id": self.enqueue(db, node, data.get("action"))}
                if not match[2] and method == "DELETE":
                    db.execute("UPDATE nodes SET revoked=1 WHERE id=?", (node["id"],))
                    db.execute("UPDATE jobs SET status='failed',finished=?,result=? WHERE node_id=? AND status IN ('queued','running')",
                               (time.time(), encode({"error": "节点已移除，执行凭证已撤销"}), node["id"]))
                    self.event(db, "node.removed", "%s 已移除并撤销凭证" % node["name"], node["id"])
                    return {"ok": True}
                if not match[2] and method == "PATCH":
                    name, region, group = label(data.get("name")), data.get("region", ""), label(data.get("group_name", "默认分组"))
                    if not isinstance(region, str) or len(region) > 80:
                        raise APIError(400, "地区名称过长")
                    policy = data.get("policy", {})
                    if not isinstance(policy, dict) or set(policy) != set(DEFAULT_POLICY):
                        raise APIError(400, "策略字段不完整")
                    if any(not isinstance(policy[k], bool) for k in ("google", "trust")):
                        raise APIError(400, "无效的模块开关")
                    interval = policy["interval_minutes"]
                    if type(interval) is not int or (interval != 0 and not 5 <= interval <= 1440):
                        raise APIError(400, "定时周期应为 5–1440 分钟，0 表示关闭")
                    if policy["scheduled_action"] not in ("snapshot", "network", "google", "trust", "quality"):
                        raise APIError(400, "不支持的定时任务")
                    if interval and (policy["scheduled_action"] not in json.loads(node["capabilities"]) or
                        (policy["scheduled_action"] in ("google", "trust") and not policy[policy["scheduled_action"]])):
                        raise APIError(400, "请先安装并启用定时任务对应的模块")
                    if policy["region_path"] not in {r["path"] for r in self.regions()}:
                        raise APIError(400, "请选择有效的目标地区")
                    db.execute("UPDATE nodes SET name=?,region=?,group_name=?,policy=?,last_scheduled=? WHERE id=?",
                               (name, region, group, encode(policy), time.time(), node["id"]))
                    self.event(db, "node.updated", "%s 的配置已更新，将在下次心跳同步" % name, node["id"])
                    return {"ok": True}
            match = re.fullmatch(r"/api/jobs/([a-f0-9]+)", path)
            if match and method == "GET":
                row = db.execute("SELECT j.*,n.name AS node_name FROM jobs j LEFT JOIN nodes n ON n.id=j.node_id WHERE j.id=?", (match[1],)).fetchone()
                if not row:
                    raise APIError(404, "任务不存在")
                item = dict(row)
                item.pop("lease", None)
                item["result"] = json.loads(item["result"]) if item["result"] else None
                return item
        raise APIError(404, "接口不存在")

    def maintenance(self):
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            db.execute("DELETE FROM enrollments WHERE expires<?", (now,))
            for row in db.execute("SELECT * FROM jobs WHERE status='running' AND lease_expires<?", (now,)).fetchall():
                db.execute("UPDATE jobs SET status='failed',finished=?,result=? WHERE id=?",
                           (now, encode({"error": "Agent 未按时回传结果，任务未自动重试，请检查节点日志"}), row["id"]))
                self.event(db, "job.failed", "%s 任务因 Agent 心跳超时而结束" % row["action"], row["node_id"], True)
            for row in db.execute("SELECT * FROM nodes WHERE revoked=0").fetchall():
                if now - max(row["seen"], row["created"]) > 75 and not row["offline_alert"]:
                    db.execute("UPDATE nodes SET offline_alert=1 WHERE id=?", (row["id"],))
                    self.event(db, "node.offline", "%s 已离线（超过 75 秒未收到心跳）" % row["name"], row["id"], True)
                policy = json.loads(row["policy"])
                if (policy["interval_minutes"] and now - row["seen"] < 75 and
                        now - row["last_scheduled"] >= policy["interval_minutes"] * 60 and
                        not db.execute("SELECT 1 FROM jobs WHERE node_id=? AND status IN ('queued','running')", (row["id"],)).fetchone()):
                    try:
                        self.enqueue(db, row, policy["scheduled_action"], "schedule")
                        db.execute("UPDATE nodes SET last_scheduled=? WHERE id=?", (now, row["id"]))
                    except APIError:
                        pass
            # Bounded operational history; pending jobs are never pruned.
            db.execute("DELETE FROM events WHERE created<? AND notify=0", (now - 30 * 86400,))
            db.execute("DELETE FROM jobs WHERE finished<?", (now - 30 * 86400,))

    def notify_one(self):
        with self.db() as db:
            if not self.setting(db, "telegram_enabled", False):
                db.execute("UPDATE events SET notify=0 WHERE notify=1")
                return
            row = db.execute("SELECT * FROM events WHERE notify=1 AND attempts<3 ORDER BY id LIMIT 1").fetchone()
        if not row:
            return
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
        sent = False
        try:
            body = encode({"chat_id": chat, "text": "IP Sentinel\n" + row["message"]}).encode()
            req = Request("https://api.telegram.org/bot%s/sendMessage" % token, body, {"Content-Type": "application/json"})
            with urlopen(req, timeout=6) as response:
                sent = bool(json.load(response).get("ok"))
        except Exception:
            logging.warning("Telegram notification delivery failed (event %s)", row["id"])
        with self.db() as db:
            db.execute("UPDATE events SET attempts=attempts+1,notify=? WHERE id=?",
                       (0 if sent or row["attempts"] >= 2 else 1, row["id"]))
            if not sent and row["attempts"] >= 2:
                self.event(db, "notification.failed", "Telegram 通知发送失败，请检查凭证与网络")


class Handler(BaseHTTPRequestHandler):
    server_version = "IPSentinel/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        logging.info("%s %s", self.client_address[0], fmt % args)

    def reply(self, status, value, content_type="application/json; charset=utf-8", cookie=None):
        body = value if isinstance(value, bytes) else encode(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def handle_request(self):
        path = urlparse(self.path).path
        store = self.server.store
        try:
            if self.command == "GET" and path == "/healthz":
                return self.reply(200, {"ok": True, "version": VERSION})
            if self.command == "GET" and path.startswith("/download/"):
                assets = {"/download/agent.py": ROOT / "agent.py", "/download/install-agent.sh": ROOT / "install-agent.sh"}
                if path in assets:
                    return self.reply(200, assets[path].read_bytes(), "text/plain; charset=utf-8")
                if path == "/download/modules.tar.gz":
                    stream = io.BytesIO()
                    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                        for name in ("mod_google.sh", "mod_trust.sh", "mod_quality.sh"):
                            archive.add(ROOT.parent / "core" / name, arcname="core/" + name)
                        archive.add(ROOT.parent / "data", arcname="data")
                    return self.reply(200, stream.getvalue(), "application/gzip")
            if path.startswith("/api/"):
                data = {}
                if self.command != "GET":
                    if self.headers.get("Transfer-Encoding"):
                        raise APIError(400, "Transfer-Encoding not supported")
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 256000:
                        raise APIError(413, "请求体过大或为空")
                    if self.headers.get_content_type() != "application/json":
                        raise APIError(415, "Content-Type must be application/json")
                    if not path.startswith("/api/agent/"):
                        origin = self.headers.get("Origin")
                        expected = store.public_url or "http://" + self.headers.get("Host", "")
                        if origin and origin != expected:
                            raise APIError(403, "Cross-origin request denied")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise APIError(400, "JSON object required")
                if path in ("/api/login", "/api/setup") and self.command == "POST":
                    value, token = store.login(data, path == "/api/setup", self.client_address[0])
                    cookie = "sentinel_session=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200" % token
                    if store.public_url:
                        cookie += "; Secure"
                    return self.reply(200, value, cookie=cookie)
                return self.reply(200, store.api(self.command, path, data, self.headers, self.client_address[0]))
            if self.command == "GET":
                assets = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8"),
                          "/favicon.svg": ("favicon.svg", "image/svg+xml")}
                if path in assets:
                    name, mime = assets[path]
                    return self.reply(200, (ROOT / "static" / name).read_bytes(), mime)
            raise APIError(404, "Not found")
        except APIError as error:
            self.close_connection = True
            self.reply(error.status, {"error": str(error)})
        except (ValueError, TypeError, UnicodeError):
            self.close_connection = True
            self.reply(400, {"error": "请求格式不正确"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception("Request failed")
            self.close_connection = True
            self.reply(500, {"error": "服务器处理失败，请检查主控日志"})

    do_GET = do_POST = do_PATCH = do_DELETE = handle_request

    def setup(self):
        super().setup()
        self.connection.settimeout(20)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, store):
        self.store = store
        super().__init__(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SENTINEL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SENTINEL_PORT", "8080")))
    parser.add_argument("--data", default=os.environ.get("SENTINEL_DATA", "./runtime/master"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    store = Store(args.data, os.environ.get("SENTINEL_PUBLIC_URL", ""), os.environ.get("SENTINEL_ADMIN_PASSWORD"))
    with store.db() as db:
        if not store.setting(db, "password"):
            print("首次初始化密钥: " + store.setup_token, flush=True)
    server = Server((args.host, args.port), store)
    stop = threading.Event()
    def background():
        while not stop.wait(10):
            try:
                store.maintenance()
                store.notify_one()
            except Exception:
                logging.exception("Background maintenance failed")
    threading.Thread(target=background, daemon=True).start()
    print("IP Sentinel: http://%s:%s" % (args.host, server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
