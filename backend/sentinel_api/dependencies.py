import hmac
import time
from fastapi import Depends, Request

from .database import Database
from .errors import APIError
from .security import digest


def service(request: Request):
    return request.app.state.service


def session(request: Request, control=Depends(service)):
    token = request.cookies.get("sentinel_session", "")
    with control.database.connect() as db:
        row = db.execute("SELECT * FROM sessions WHERE token=? AND expires>?", (digest(token), time.time())).fetchone() if token else None
        if not row:
            raise APIError(401, "请先登录", "unauthenticated")
        value = dict(row)
        value["must_change_password"] = Database.get(db, "must_change_password", True)
        value["username"] = Database.get(db, "username", "admin")
    if request.method not in ("GET", "HEAD"):
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), value["csrf"]):
            raise APIError(403, "页面凭证已失效，请刷新后重试", "invalid_csrf")
    return value


def administrator(value=Depends(session)):
    if value["must_change_password"]:
        raise APIError(403, "首次登录必须先修改初始密码", "password_change_required")
    return value
