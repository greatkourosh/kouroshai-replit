from fastapi import APIRouter, HTTPException
# from .service import create_task, get_tasks, update_task, delete_task
from .service import create_task, get_tasks
from pydantic import BaseModel

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])

class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    status: str = "pending"

@router.post("/")
async def add_task(task: TaskCreate):
    try:
        task_id = await create_task(task.title, task.description, task.status)
        return {"id": task_id, "message": "Task created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def list_tasks():
    return await get_tasks()