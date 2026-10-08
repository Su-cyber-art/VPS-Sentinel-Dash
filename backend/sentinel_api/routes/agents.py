import io
import tarfile
from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import FileResponse

from ..dependencies import service
from ..models import AgentEnrollment, Heartbeat, TaskResult

router = APIRouter(tags=["agents"])


@router.post("/api/agent/enroll")
def enroll(data: AgentEnrollment, control=Depends(service)):
    return control.register_agent(data.token)


@router.post("/api/agent/heartbeat")
def heartbeat(data: Heartbeat, authorization: str = Header(default=""), control=Depends(service)):
    return control.heartbeat(authorization, data)


@router.post("/api/agent/result")
def result(data: TaskResult, authorization: str = Header(default=""), control=Depends(service)):
    return control.complete_task(authorization, data)


@router.get("/downloads/agent.py")
def download_agent(control=Depends(service)):
    return FileResponse(control.config.root / "agent/sentinel_agent.py", media_type="text/x-python", filename="sentinel_agent.py")


@router.get("/downloads/install.sh")
def download_installer(control=Depends(service)):
    return FileResponse(control.config.root / "install.sh", media_type="text/plain", filename="install.sh")


@router.get("/downloads/modules.tar.gz")
def modules(control=Depends(service)):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name in ("mod_google.sh", "mod_trust.sh", "mod_quality.sh", "runner.sh"):
            archive.add(control.config.root / "core" / name, arcname="core/" + name)
        archive.add(control.config.root / "data", arcname="data")
    return Response(stream.getvalue(), media_type="application/gzip")
