import pytest
import asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from app import (
    app,
    Base,
    TaskModel,
    async_session,
    async_sessionmaker,
    engine,
)


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def test_db():
    test_engine = create_async_engine("sqlite+aiosqlite:///./test_tasks.db")
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    yield test_session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def client(test_db):
    app.state.health_check_task = None
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "task-service"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_create_task(client):
    resp = await client.post("/tasks", json={"title": "Test task", "description": "Test description"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test task"
    assert data["description"] == "Test description"
    assert data["status"] == "pending"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_get_tasks_empty(client):
    resp = await client.get("/tasks")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_tasks(client):
    await client.post("/tasks", json={"title": "Task 1"})
    await client.post("/tasks", json={"title": "Task 2"})
    resp = await client.get("/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_get_task_by_id(client):
    resp = await client.post("/tasks", json={"title": "Single task"})
    task_id = resp.json()["id"]
    resp = await client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Single task"


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    resp = await client.get("/tasks/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_task(client):
    resp = await client.post("/tasks", json={"title": "Update me"})
    task_id = resp.json()["id"]
    resp = await client.put(f"/tasks/{task_id}", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_task_not_found(client):
    resp = await client.put("/tasks/9999", json={"status": "completed"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_task(client):
    resp = await client.post("/tasks", json={"title": "Delete me"})
    task_id = resp.json()["id"]
    resp = await client.delete(f"/tasks/{task_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/tasks/{task_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_not_found(client):
    resp = await client.delete("/tasks/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_task(client):
    resp = await client.post("/tasks", json={"title": "Complete me"})
    task_id = resp.json()["id"]
    resp = await client.get(f"/tasks/{task_id}/complete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_get_stats(client):
    await client.post("/tasks", json={"title": "Task 1"})
    await client.post("/tasks", json={"title": "Task 2"})
    await client.post("/tasks", json={"title": "Task 3"})
    resp = await client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["pending"] == 3
    assert data["in_progress"] == 0
    assert data["completed"] == 0


@pytest.mark.asyncio
async def test_get_tasks_by_status(client):
    await client.post("/tasks", json={"title": "Pending task"})
    await client.post("/tasks", json={"title": "In Progress task"})
    resp = await client.get("/tasks?status=pending")
    assert resp.status_code == 200
    for task in resp.json():
        assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_dashboard(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Task Service Dashboard" in resp.text


@pytest.mark.asyncio
async def test_create_task_missing_title(client):
    resp = await client.post("/tasks", json={"description": "No title"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_task_empty_title(client):
    resp = await client.post("/tasks", json={"title": "", "description": "Empty title"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_stats_after_operations(client):
    await client.post("/tasks", json={"title": "Task A"})
    await client.post("/tasks", json={"title": "Task B"})
    task_a_resp = await client.get("/tasks")
    task_a_id = task_a_resp.json()[0]["id"]
    await client.put(f"/tasks/{task_a_id}", json={"status": "completed"})
    resp = await client.get("/stats")
    data = resp.json()
    assert data["total"] == 2
    assert data["completed"] == 1
    assert data["pending"] == 1
