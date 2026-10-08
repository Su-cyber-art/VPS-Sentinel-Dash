import hmac
import time
from fastapi import APIRouter, Depends, Request, Response

from ..database import Database
from ..dependencies import service, session
from ..errors import APIError
from ..models import Login, PasswordChange
from ..security import create_session, digest, set_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def cookie(response, token, secure):
    response.set_cookie("sentinel_session", token, max_age=43200, httponly=True, secure=secure, samesite="strict", path="/")


@router.get("/session")
def current_session(request: Request, control=Depends(service)):
    with control.database.connect() as db:
        configured = bool(Database.get(db, "password"))
        token = request.cookies.get("sentinel_session", "")
        row = db.execute("SELECT * FROM sessions WHERE token=? AND expires>?", (digest(token), time.time())).fetchone() if token else None
        if not row:
            return {"configured": configured, "authenticated": False, "must_change_password": False}
        return {"configured": configured, "authenticated": True, "csrf": row["csrf"],
                "username": Database.get(db, "username", "admin"),
                "must_change_password": Database.get(db, "must_change_password", True)}


@router.post("/login")
def login(data: Login, request: Request, response: Response, control=Depends(service)):
    request.app.state.limiter.check(request.client.host if request.client else "unknown")
    with control.database.connect(write=True) as db:
        saved = Database.get(db, "password")
        if not saved:
            raise APIError(503, "管理员尚未初始化，请先运行安装脚本", "not_initialized")
        valid_password = verify_password(data.password, saved)
        if not (hmac.compare_digest(data.username.encode(), Database.get(db, "username", "admin").encode()) and valid_password):
            raise APIError(401, "用户名或密码不正确", "invalid_credentials")
        token, result = create_session(db)
        control.event(db, "admin.login", "管理员已登录")
    cookie(response, token, control.config.secure_cookie)
    return result


@router.post("/logout")
def logout(response: Response, value=Depends(session), control=Depends(service)):
    with control.database.connect(write=True) as db:
        db.execute("DELETE FROM sessions WHERE token=?", (value["token"],))
    response.delete_cookie("sentinel_session", path="/")
    return {"ok": True}


@router.post("/password")
def change_password(data: PasswordChange, response: Response, value=Depends(session), control=Depends(service)):
    with control.database.connect(write=True) as db:
        saved = Database.get(db, "password")
        if not verify_password(data.current_password, saved):
            raise APIError(403, "当前密码不正确", "invalid_password")
        if verify_password(data.new_password, saved):
            raise APIError(400, "新密码不能与初始或当前密码相同", "password_unchanged")
        set_password(db, data.new_password, must_change=False)
        db.execute("DELETE FROM sessions")
        token, result = create_session(db)
        control.event(db, "admin.password", "管理员已修改密码，旧会话全部失效")
    cookie(response, token, control.config.secure_cookie)
    return result
