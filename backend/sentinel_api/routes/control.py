from fastapi import APIRouter, Depends

from ..dependencies import administrator, service
from ..models import BatchTasks, Enrollment, NodeUpdate, NotificationSettings, TaskCreate

router = APIRouter(prefix="/api", tags=["control plane"], dependencies=[Depends(administrator)])


@router.get("/overview")
def overview(control=Depends(service)):
    return control.overview()


@router.get("/nodes")
def nodes(control=Depends(service)):
    return {"nodes": control.overview()["nodes"]}


@router.post("/enrollments", status_code=201)
def enrollment(data: Enrollment, control=Depends(service)):
    return control.enrollment(data.name)


@router.get("/regions")
def regions(control=Depends(service)):
    return {"regions": control.regions()}


@router.patch("/nodes/{node_id}")
def update_node(node_id: str, data: NodeUpdate, control=Depends(service)):
    return control.update_node(node_id, data)


@router.delete("/nodes/{node_id}")
def remove_node(node_id: str, control=Depends(service)):
    return control.remove_node(node_id)


@router.post("/nodes/{node_id}/jobs", status_code=202)
def create_task(node_id: str, data: TaskCreate, control=Depends(service)):
    return control.create_task(node_id, data.action)


@router.post("/jobs/batch", status_code=202)
def batch_tasks(data: BatchTasks, control=Depends(service)):
    return control.batch_tasks(data.node_ids, data.action)


@router.get("/jobs/{task_id}")
def task(task_id: str, control=Depends(service)):
    return control.task(task_id)


@router.post("/jobs/{task_id}/cancel")
def cancel_task(task_id: str, control=Depends(service)):
    return control.cancel_task(task_id)


@router.get("/settings")
def settings(control=Depends(service)):
    return control.settings()


@router.put("/settings")
def update_settings(data: NotificationSettings, control=Depends(service)):
    return control.update_settings(data.telegram_enabled)
