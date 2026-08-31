import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    select,
    update,
    delete,
    func,
    case,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("task-service")

DB_USER = os.getenv("DB_USER", "devops")
DB_PASSWORD = os.getenv("DB_PASSWORD", "devops123")
DB_NAME = os.getenv("DB_NAME", "taskdb")
DATABASE_URL = os.getenv("DATABASE_URL", f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@db:5432/{DB_NAME}")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:9000")
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
PROCESSING_TIMEOUT = int(os.getenv("PROCESSING_TIMEOUT", "30"))  # seconds before pending -> in_progress

VALID_STATUSES = {"pending", "in_progress", "completed", "failed"}


class Base(DeclarativeBase):
    pass


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TaskCreate(BaseModel):
    title: str
    description: str = ""


class TaskUpdate(BaseModel):
    status: str


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class StatsResponse(BaseModel):
    total: int
    pending: int
    in_progress: int
    completed: int


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_notification_service():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{NOTIFICATION_SERVICE_URL}/health", timeout=5.0)
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Notification service health check failed: {e}")
        return False


async def notify_on_task_create(task_id: int):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{NOTIFICATION_SERVICE_URL}/notify",
                json={"task_id": task_id, "type": "task_created", "message": f"Task #{task_id} created"},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")


async def notify_on_task_status_change(task_id: int, new_status: str):
    """Send notification when task status changes."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{NOTIFICATION_SERVICE_URL}/notify",
                json={"task_id": task_id, "type": "task_status_changed", "message": f"Task #{task_id} -> {new_status}"},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning(f"Failed to send status change notification: {e}")


async def process_pending_tasks():
    """Background worker: transitions pending tasks to in_progress, then to completed."""
    logger.info("Task processor started — monitoring pending tasks")
    while True:
        try:
            async with async_session() as session:
                # Find pending tasks older than PROCESSING_TIMEOUT
                cutoff = datetime.now(timezone.utc) - timedelta(seconds=PROCESSING_TIMEOUT)
                stmt = (
                    select(TaskModel)
                    .where(TaskModel.status == "pending", TaskModel.created_at < cutoff)
                    .order_by(TaskModel.created_at.asc())
                )
                result = await session.execute(stmt)
                pending_tasks = result.scalars().all()

                if pending_tasks:
                    logger.info(f"Found {len(pending_tasks)} pending task(s) to process")

                for task in pending_tasks:
                    # Transition: pending -> in_progress
                    task.status = "in_progress"
                    task.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    await session.refresh(task)
                    logger.info(f"Task #{task.id} -> in_progress")

                    # Simulate processing (in real app: do actual work here)
                    await asyncio.sleep(1)

                    # Transition: in_progress -> completed
                    task.status = "completed"
                    task.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    await session.refresh(task)
                    logger.info(f"Task #{task.id} -> completed")

                    # Notify on status change
                    await notify_on_task_status_change(task.id, "completed")

        except Exception as e:
            logger.error(f"Error in task processor: {e}")

        await asyncio.sleep(5)


async def periodic_health_checks():
    while True:
        ns_healthy = await check_notification_service()
        logger.info(f"Health check - Notification Service: {'UP' if ns_healthy else 'DOWN'}")
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Task Service started with database")
    app.state.health_check_task = asyncio.create_task(periodic_health_checks())
    app.state.task_processor_task = asyncio.create_task(process_pending_tasks())
    yield
    app.state.health_check_task.cancel()
    app.state.task_processor_task.cancel()
    try:
        await app.state.health_check_task
    except asyncio.CancelledError:
        pass
    try:
        await app.state.task_processor_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(title="Task Service", version="1.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="task-service", timestamp=datetime.now(timezone.utc))


@app.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(task_data: TaskCreate):
    async with async_session() as session:
        task = TaskModel(title=task_data.title, description=task_data.description, status="pending")
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id
    # Fire-and-forget notification
    asyncio.create_task(notify_on_task_create(task_id))
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        created_at=task.created_at or datetime.now(timezone.utc),
        updated_at=task.updated_at or datetime.now(timezone.utc),
    )


@app.get("/tasks", response_model=list[TaskResponse])
async def get_tasks(status: str | None = None):
    async with async_session() as session:
        if status:
            stmt = select(TaskModel).where(TaskModel.status == status)
        else:
            stmt = select(TaskModel)
        result = await session.execute(stmt.order_by(TaskModel.created_at.desc()))
        tasks = result.scalars().all()
    return [
        TaskResponse(
            id=t.id,
            title=t.title,
            description=t.description,
            status=t.status,
            created_at=t.created_at or datetime.now(timezone.utc),
            updated_at=t.updated_at or datetime.now(timezone.utc),
        )
        for t in tasks
    ]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    async with async_session() as session:
        result = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskResponse(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            created_at=task.created_at or datetime.now(timezone.utc),
            updated_at=task.updated_at or datetime.now(timezone.utc),
        )


@app.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task_data: TaskUpdate):
    async with async_session() as session:
        result = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        new_status = task_data.status
        if new_status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}. Must be one of {VALID_STATUSES}")

        old_status = task.status
        task.status = new_status
        task.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(task)

        # Notify on status change
        if old_status != new_status:
            asyncio.create_task(notify_on_task_status_change(task.id, new_status))

        return TaskResponse(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            created_at=task.created_at or datetime.now(timezone.utc),
            updated_at=task.updated_at or datetime.now(timezone.utc),
        )


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int):
    async with async_session() as session:
        result = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        await session.delete(task)
        await session.commit()
    return None


@app.get("/tasks/{task_id}/complete", response_model=TaskResponse)
async def complete_task(task_id: int):
    return await update_task(task_id, TaskUpdate(status="completed"))


@app.post("/tasks/reprocess", status_code=200)
async def reprocess_pending_tasks():
    """Manual trigger to reprocess all pending tasks (useful for testing/debugging)."""
    count = 0
    async with async_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=PROCESSING_TIMEOUT)
        stmt = select(TaskModel).where(TaskModel.status == "pending", TaskModel.created_at < cutoff)
        result = await session.execute(stmt)
        tasks = result.scalars().all()

        for task in tasks:
            task.status = "in_progress"
            task.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(task)

            # Simulate processing
            await asyncio.sleep(1)

            task.status = "completed"
            task.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(task)
            count += 1
            logger.info(f"Reprocessed task #{task.id}")

    return {"reprocessed": count, "message": f"{count} task(s) reprocessed"}


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    async with async_session() as session:
        all_tasks = await session.execute(select(TaskModel))
        all_tasks_list = all_tasks.scalars().all()
        total = len(all_tasks_list)
        pending = sum(1 for t in all_tasks_list if t.status == "pending")
        in_progress = sum(1 for t in all_tasks_list if t.status == "in_progress")
        completed = sum(1 for t in all_tasks_list if t.status == "completed")
    return StatsResponse(total=total, pending=pending, in_progress=in_progress, completed=completed)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Task Service</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { color: #333; }
            .card { background: white; padding: 20px; margin: 15px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 5px; }
            button:hover { background: #0056b3; }
            button.danger { background: #dc3545; }
            button.danger:hover { background: #a71d2a; }
            button.success { background: #28a745; }
            button.success:hover { background: #1e7e34; }
            button.warning { background: #f39c12; }
            button.warning:hover { background: #e67e22; }
            input, textarea { width: 100%; padding: 8px; margin: 5px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
            pre { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 4px; overflow-x: auto; }
            .status-pending { color: #e67e22; font-weight: bold; }
            .status-in_progress { color: #3498db; font-weight: bold; }
            .status-completed { color: #27ae60; font-weight: bold; }
            .auto-process { background: #6f42c1; }
            .auto-process:hover { background: #5a32a3; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Task Service Dashboard</h1>
            <div class="card">
                <h3>Create Task</h3>
                <input type="text" id="taskTitle" placeholder="Task title">
                <textarea id="taskDesc" placeholder="Description" rows="3"></textarea>
                <button onclick="createTask()">Create Task</button>
            </div>
            <div class="card">
                <h3>Tasks</h3>
                <button onclick="loadTasks()">Refresh</button>
                <button class="warning" onclick="reprocessTasks()">Reprocess Pending</button>
                <pre id="tasksList">Click Refresh to load tasks</pre>
            </div>
            <div class="card">
                <h3>Stats</h3>
                <button onclick="loadStats()">Load Stats</button>
                <pre id="statsData">Click Load Stats</pre>
            </div>
            <div class="card">
                <h3>Health Check</h3>
                <button onclick="loadHealth()">Check Health</button>
                <pre id="healthData">Click Check Health</pre>
            </div>
        </div>
        <script>
            async function loadTasks() {
                const res = await fetch('/tasks');
                const tasks = await res.json();
                document.getElementById('tasksList').textContent = JSON.stringify(tasks, null, 2);
            }
            async function loadStats() {
                const res = await fetch('/stats');
                const data = await res.json();
                document.getElementById('statsData').textContent = JSON.stringify(data, null, 2);
            }
            async function loadHealth() {
                const res = await fetch('/health');
                const data = await res.json();
                document.getElementById('healthData').textContent = JSON.stringify(data, null, 2);
            }
            async function reprocessTasks() {
                const res = await fetch('/tasks/reprocess', { method: 'POST' });
                const data = await res.json();
                alert(data.message);
                loadTasks();
                loadStats();
            }
            async function createTask() {
                const title = document.getElementById('taskTitle').value;
                const desc = document.getElementById('taskDesc').value;
                if (!title) { alert('Title is required'); return; }
                const res = await fetch('/tasks', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({title, description: desc})
                });
                const task = await res.json();
                loadTasks();
            }
            loadTasks();
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
