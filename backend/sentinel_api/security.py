import hashlib
import hmac
import secrets
import threading
import time

from .database import Database
from .errors import APIError


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()


def set_password(db, password, *, must_change):
    if not 12 <= len(password) <= 256:
        raise APIError(400, "密码需要 12–256 个字符")
    salt = secrets.token_hex(16)
    Database.set(db, "password", {"salt": salt, "hash": password_hash(password, salt)})
    Database.set(db, "must_change_password", must_change)


def verify_password(password, saved):
    return bool(saved and len(password) <= 256 and hmac.compare_digest(saved["hash"], password_hash(password, saved["salt"])))


def create_session(db):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), csrf, time.time() + 43200))
    return token, {"authenticated": True, "configured": True, "csrf": csrf,
                   "username": Database.get(db, "username", "admin"),
                   "must_change_password": Database.get(db, "must_change_password", True)}


class LoginLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.attempts = {}

    def check(self, client):
        now = time.time()
        with self.lock:
            self.attempts = {k: v for k, v in self.attempts.items() if now - v[-1] < 60}
            attempts = [t for t in self.attempts.get(client, []) if now - t < 60]
            if len(attempts) >= 8:
                raise APIError(429, "登录尝试过多，请一分钟后重试", "rate_limited")
            self.attempts[client] = attempts + [now]
