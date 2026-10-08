from contextlib import asynccontextmanager
import logging
import threading
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Config, VERSION
from .errors import APIError
from .routes import agents, auth, control
from .security import LoginLimiter
from .service import ControlPlane


class BodyLimitMiddleware:
    def __init__(self, app, limit=262144):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD"):
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                return await JSONResponse({"error": "请求体过大", "code": "body_too_large"}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


def create_app(config=None):
    config = config or Config()
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = ControlPlane(config)
        app.state.limiter = LoginLimiter()
        stop = threading.Event()
        def maintain():
            while not stop.wait(10):
                try:
                    app.state.service.maintenance()
                    app.state.service.notify_one()
                except Exception:
                    logging.exception("Background maintenance failed")
        worker = threading.Thread(target=maintain, daemon=True)
        if config.maintenance:
            worker.start()
        try:
            yield
        finally:
            stop.set()
            if worker.is_alive():
                worker.join(timeout=8)

    app = FastAPI(title="VPS Sentinel API", version=VERSION, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(BodyLimitMiddleware)
    if config.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(config.allowed_origins), allow_credentials=True,
                           allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])

    @app.middleware("http")
    async def request_guards(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            bodyless_delete = request.method == "DELETE" and request.headers.get("content-length", "0") == "0"
            if not bodyless_delete and request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return JSONResponse({"error": "请求需使用 application/json", "code": "invalid_content_type"}, status_code=415)
            if not request.url.path.startswith("/api/agent/"):
                supplied = request.headers.get("origin")
                host = request.headers.get("host", "")
                allowed = {"http://" + host, "https://" + host, *config.allowed_origins}
                if config.public_url:
                    allowed.add(config.public_url)
                if supplied and supplied not in allowed:
                    return JSONResponse({"error": "来源地址不匹配", "code": "invalid_origin"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(APIError)
    async def api_error(request, error):
        return JSONResponse({"error": str(error), "code": error.code}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({"error": "请求参数不正确", "code": "validation_error",
                             "fields": [{"path": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors()]}, status_code=422)

    @app.get("/api/health", tags=["health"])
    def health():
        return {"ok": True, "version": VERSION, "service": "vps-sentinel-api"}

    app.include_router(auth.router)
    app.include_router(control.router)
    app.include_router(agents.router)
    return app


app = create_app()
