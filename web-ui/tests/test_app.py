import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app import app
import httpx


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.mark.asyncio
async def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "web-ui"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_dashboard(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "DevOps Practice" in resp.data.decode()


@pytest.mark.asyncio
async def test_api_get_tasks(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = (
            [{"id": 1, "title": "Test", "description": "", "status": "pending", "created_at": "2024-01-01T00:00:00", "updated_at": "2024-01-01T00:00:00"}],
            200
        )
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["title"] == "Test"


@pytest.mark.asyncio
async def test_api_get_tasks_with_status(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = ([], 200)
        resp = client.get("/api/tasks?status=pending")
        assert resp.status_code == 200
        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert "status=pending" in call_args[0][1]


@pytest.mark.asyncio
async def test_api_create_task(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = (
            {"id": 1, "title": "New Task", "description": "Desc", "status": "pending"},
            201
        )
        resp = client.post("/api/tasks", json={"title": "New Task", "description": "Desc"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] == "New Task"


@pytest.mark.asyncio
async def test_api_create_task_missing_title(client):
    resp = client.post("/api/tasks", json={"description": "No title"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_create_task_empty_body(client):
    resp = client.post("/api/tasks", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_get_task(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = (
            {"id": 1, "title": "Single Task", "description": "Desc", "status": "pending"},
            200
        )
        resp = client.get("/api/tasks/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 1


@pytest.mark.asyncio
async def test_api_update_task(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = (
            {"id": 1, "title": "Updated", "description": "Desc", "status": "in_progress"},
            200
        )
        resp = client.put("/api/tasks/1", json={"status": "in_progress"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "in_progress"


@pytest.mark.asyncio
async def test_api_update_task_empty_body(client):
    resp = client.put("/api/tasks/1", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_delete_task(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = (None, 204)
        resp = client.delete("/api/tasks/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "Task deleted"


@pytest.mark.asyncio
async def test_api_complete_task(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = (
            {"id": 1, "title": "Completed", "description": "", "status": "completed"},
            200
        )
        resp = client.get("/api/tasks/1/complete")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_api_get_stats(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = (
            {"total": 5, "pending": 2, "in_progress": 2, "completed": 1},
            200
        )
        resp = client.get("/api/tasks/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 5


@pytest.mark.asyncio
async def test_api_get_notifications(client):
    with patch("app.call_notification_service") as mock_call:
        mock_call.return_value = ([], 200)
        resp = client.get("/api/notifications")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_get_notification_by_id(client):
    with patch("app.call_notification_service") as mock_call:
        mock_call.return_value = (
            {"id": 1, "task_id": 1, "type": "task_created", "message": "Test", "status": "sent"},
            200
        )
        resp = client.get("/api/notifications/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 1


@pytest.mark.asyncio
async def test_api_get_notifications_by_task(client):
    with patch("app.call_notification_service") as mock_call:
        mock_call.return_value = ([], 200)
        resp = client.get("/api/notifications/task/1")
        assert resp.status_code == 200
        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert "notifications/task/1" in call_args[0][1]


@pytest.mark.asyncio
async def test_api_get_notification_stats(client):
    with patch("app.call_notification_service") as mock_call:
        mock_call.return_value = (
            {"total": 10, "sent": 8, "failed": 2},
            200
        )
        resp = client.get("/api/notifications/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 10


@pytest.mark.asyncio
async def test_api_send_notification(client):
    with patch("app.call_notification_service") as mock_call:
        mock_call.return_value = (
            {"id": 1, "task_id": 1, "type": "manual", "message": "Test", "status": "sent"},
            201
        )
        resp = client.post("/api/notify/1", json={"type": "manual", "message": "Test"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["type"] == "manual"


@pytest.mark.asyncio
async def test_api_send_notification_default_type(client):
    with patch("app.call_notification_service") as mock_call:
        mock_call.return_value = (
            {"id": 1, "task_id": 1, "type": "manual", "message": "Test", "status": "sent"},
            201
        )
        resp = client.post("/api/notify/1", json={"message": "Test"})
        assert resp.status_code == 201
        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert call_args[1]["json"]["type"] == "manual"


@pytest.mark.asyncio
async def test_api_services_status(client):
    with patch("app.check_task_service") as mock_ts, patch("app.check_notification_service") as mock_ns:
        mock_ts.return_value = True
        mock_ns.return_value = True
        resp = client.get("/api/services/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["task_service"] == "healthy"
        assert data["notification_service"] == "healthy"


@pytest.mark.asyncio
async def test_api_services_status_unhealthy(client):
    with patch("app.check_task_service") as mock_ts, patch("app.check_notification_service") as mock_ns:
        mock_ts.return_value = False
        mock_ns.return_value = False
        resp = client.get("/api/services/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["task_service"] == "unhealthy"
        assert data["notification_service"] == "unhealthy"


@pytest.mark.asyncio
async def test_api_get_tasks_service_error(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = ({"error": "Service unavailable"}, 503)
        resp = client.get("/api/tasks")
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_api_create_task_service_error(client):
    with patch("app.call_task_service") as mock_call:
        mock_call.return_value = ({"error": "Service unavailable"}, 503)
        resp = client.post("/api/tasks", json={"title": "Test"})
        assert resp.status_code == 503
