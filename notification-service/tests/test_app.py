import pytest
from app import app, db, Notification


@pytest.fixture
def client():
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.drop_all()


@pytest.fixture
def app_context():
    with app.app_context():
        db.create_all()
        yield
        db.drop_all()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "notification-service"
    assert "timestamp" in data


def test_create_notification(client, app_context):
    resp = client.post("/notify", json={
        "task_id": 1,
        "type": "task_created",
        "message": "Task #1 created"
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["task_id"] == 1
    assert data["type"] == "task_created"
    assert data["message"] == "Task #1 created"
    assert data["status"] == "sent"
    assert data["id"] is not None


def test_create_notification_missing_fields(client):
    resp = client.post("/notify", json={"task_id": 1})
    assert resp.status_code == 400


def test_create_notification_empty_body(client):
    resp = client.post("/notify", json={})
    assert resp.status_code == 400


def test_get_notifications_empty(client, app_context):
    resp = client.get("/notifications")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_get_notifications(client, app_context):
    with app.app_context():
        n1 = Notification(task_id=1, notif_type="task_created", message="Task 1 created", status="sent")
        n2 = Notification(task_id=2, notif_type="task_completed", message="Task 2 completed", status="sent")
        db.session.add_all([n1, n2])
        db.session.commit()
    resp = client.get("/notifications")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2


def test_get_notification_by_id(client, app_context):
    with app.app_context():
        n = Notification(task_id=1, notif_type="task_created", message="Task 1 created", status="sent")
        db.session.add(n)
        db.session.commit()
        notif_id = n.id
    resp = client.get(f"/notifications/{notif_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["task_id"] == 1
    assert data["type"] == "task_created"


def test_get_notification_not_found(client):
    resp = client.get("/notifications/9999")
    assert resp.status_code == 404


def test_get_notifications_by_task(client, app_context):
    with app.app_context():
        n1 = Notification(task_id=1, notif_type="task_created", message="Task 1 created", status="sent")
        n2 = Notification(task_id=1, notif_type="task_completed", message="Task 1 completed", status="sent")
        n3 = Notification(task_id=2, notif_type="task_created", message="Task 2 created", status="sent")
        db.session.add_all([n1, n2, n3])
        db.session.commit()
    resp = client.get("/notifications/task/1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2
    for notif in data:
        assert notif["task_id"] == 1


def test_get_notification_stats(client, app_context):
    with app.app_context():
        n1 = Notification(task_id=1, notif_type="task_created", message="Task 1 created", status="sent")
        n2 = Notification(task_id=2, notif_type="task_created", message="Task 2 created", status="sent")
        n3 = Notification(task_id=3, notif_type="task_created", message="Task 3 created", status="failed")
        db.session.add_all([n1, n2, n3])
        db.session.commit()
    resp = client.get("/notifications/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 3
    assert data["sent"] == 2
    assert data["failed"] == 1


def test_dashboard(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Notification Service Dashboard" in resp.data.decode()


def test_create_notification_default_type(client, app_context):
    resp = client.post("/notify", json={
        "task_id": 1,
        "message": "Generic notification"
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["type"] == "generic"


def test_create_notification_default_message(client, app_context):
    resp = client.post("/notify", json={
        "task_id": 1,
        "type": "task_created"
    })
    assert resp.status_code == 400


def test_notifications_order(client, app_context):
    with app.app_context():
        n1 = Notification(task_id=1, notif_type="task_created", message="First", status="sent")
        n2 = Notification(task_id=2, notif_type="task_created", message="Second", status="sent")
        n3 = Notification(task_id=3, notif_type="task_created", message="Third", status="sent")
        db.session.add_all([n1, n2, n3])
        db.session.commit()
    resp = client.get("/notifications")
    data = resp.get_json()
    assert len(data) == 3
