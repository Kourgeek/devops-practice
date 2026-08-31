import os
import logging
from datetime import datetime, timezone

import httpx
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("web-ui")

TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://task-service:8000")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:9000")
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))

app = Flask(__name__)


def call_task_service(method, path, json_data=None):
    url = f"{TASK_SERVICE_URL}{path}"
    try:
        with httpx.Client(timeout=10.0) as client:
            if method == "GET":
                resp = client.get(url)
            elif method == "POST":
                resp = client.post(url, json=json_data)
            elif method == "PUT":
                resp = client.put(url, json=json_data)
            elif method == "DELETE":
                resp = client.delete(url)
            else:
                return None, 405
            return resp.json() if resp.content else None, resp.status_code
    except Exception as e:
        logger.error(f"Error calling task service: {e}")
        return {"error": str(e)}, 503


def call_notification_service(method, path, json_data=None):
    url = f"{NOTIFICATION_SERVICE_URL}{path}"
    try:
        with httpx.Client(timeout=10.0) as client:
            if method == "GET":
                resp = client.get(url)
            elif method == "POST":
                resp = client.post(url, json=json_data)
            elif method == "PUT":
                resp = client.put(url, json=json_data)
            elif method == "DELETE":
                resp = client.delete(url)
            else:
                return None, 405
            return resp.json() if resp.content else None, resp.status_code
    except Exception as e:
        logger.error(f"Error calling notification service: {e}")
        return {"error": str(e)}, 503


@app.before_request
def start_health_check():
    pass


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "web-ui",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@app.route("/api/tasks", methods=["GET"])
def api_get_tasks():
    status = request.args.get("status")
    path = "/tasks"
    if status:
        path += f"?status={status}"
    data, code = call_task_service("GET", path)
    return jsonify(data), code


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400
    result, code = call_task_service("POST", "/tasks", data)
    return jsonify(result), code


@app.route("/api/tasks/<int:task_id>", methods=["GET"])
def api_get_task(task_id):
    data, code = call_task_service("GET", f"/tasks/{task_id}")
    return jsonify(data), code


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def api_update_task(task_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    result, code = call_task_service("PUT", f"/tasks/{task_id}", data)
    return jsonify(result), code


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    result, code = call_task_service("DELETE", f"/tasks/{task_id}")
    if code == 204:
        return jsonify({"message": "Task deleted"}), 200
    return jsonify(result), code


@app.route("/api/tasks/<int:task_id>/complete", methods=["GET"])
def api_complete_task(task_id):
    data, code = call_task_service("GET", f"/tasks/{task_id}/complete")
    return jsonify(data), code


@app.route("/api/tasks/stats", methods=["GET"])
def api_get_stats():
    data, code = call_task_service("GET", "/stats")
    return jsonify(data), code


@app.route("/api/tasks/reprocess", methods=["POST"])
def api_reprocess_tasks():
    """Proxy endpoint to reprocess pending tasks."""
    result, code = call_task_service("POST", "/tasks/reprocess", None)
    return jsonify(result), code


@app.route("/api/notifications", methods=["GET"])
def api_get_notifications():
    data, code = call_notification_service("GET", "/notifications")
    return jsonify(data), code


@app.route("/api/notifications/<int:notification_id>", methods=["GET"])
def api_get_notification(notification_id):
    data, code = call_notification_service("GET", f"/notifications/{notification_id}")
    return jsonify(data), code


@app.route("/api/notifications/task/<int:task_id>", methods=["GET"])
def api_get_notifications_by_task(task_id):
    data, code = call_notification_service("GET", f"/notifications/task/{task_id}")
    return jsonify(data), code


@app.route("/api/notifications/stats", methods=["GET"])
def api_get_notification_stats():
    data, code = call_notification_service("GET", "/notifications/stats")
    return jsonify(data), code


@app.route("/api/services/status", methods=["GET"])
def api_services_status():
    ts_data, ts_code = call_task_service("GET", "/health")
    ns_data, ns_code = call_notification_service("GET", "/health")
    return jsonify({
        "task_service": "healthy" if ts_code == 200 else "unhealthy",
        "notification_service": "healthy" if ns_code == 200 else "unhealthy"
    }), 200


@app.route("/", methods=["GET"])
def dashboard():
    html = """<!DOCTYPE html>
<html>
<head>
    <title>DevOps Practice - Task Management</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; background: #f5f5f5; }
        .navbar { background: #2c3e50; color: white; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; }
        .navbar h1 { margin: 0; font-size: 20px; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
        .row { display: flex; gap: 20px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; }
        .card h3 { margin-top: 0; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        button { background: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin: 3px; font-size: 13px; }
        button:hover { background: #2980b9; }
        button.success { background: #27ae60; }
        button.success:hover { background: #219a52; }
        button.danger { background: #e74c3c; }
        button.danger:hover { background: #c0393c; }
        button.warning { background: #f39c12; }
        button.warning:hover { background: #e67e22; }
        button.purple { background: #6f42c1; }
        button.purple:hover { background: #5a32a3; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        input, textarea { width: 100%; padding: 8px; margin: 5px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; font-family: Arial, sans-serif; }
        pre { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 4px; overflow-x: auto; font-size: 12px; max-height: 300px; overflow-y: auto; }
        .status-healthy { color: #27ae60; font-weight: bold; }
        .status-unhealthy { color: #e74c3c; font-weight: bold; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; color: white; margin: 2px; }
        .badge-pending { background: #e67e22; }
        .badge-in_progress { background: #3498db; }
        .badge-completed { background: #27ae60; }
        .badge-failed { background: #e74c3c; }
        .form-group { margin: 10px 0; }
        label { display: block; margin-bottom: 4px; font-weight: bold; color: #555; }
        .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #fff; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 5px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .toast { position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 4px; color: white; z-index: 1000; animation: fadeIn 0.3s; }
        .toast-success { background: #27ae60; }
        .toast-error { background: #e74c3c; }
        .toast-info { background: #3498db; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>DevOps Practice - Task Management System</h1>
        <div>
            <span id="tsStatus" class="status-healthy">Task Service: Checking...</span>
            <span id="nsStatus" class="status-healthy" style="margin-left: 20px;">Notification Service: Checking...</span>
        </div>
    </div>
    <div class="container">
        <div class="row">
            <div class="card">
                <h3>Create Task</h3>
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" id="taskTitle" placeholder="Enter task title">
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="taskDesc" placeholder="Enter description" rows="2"></textarea>
                </div>
                <button class="success" onclick="createTask()">Create Task</button>
            </div>
            <div class="card">
                <h3>Quick Actions</h3>
                <button onclick="loadTasks()">Refresh Tasks</button>
                <button onclick="loadStats()">Load Stats</button>
                <button class="warning" onclick="reprocessTasks()">Reprocess Pending</button>
                <button onclick="loadServicesStatus()">Check Services</button>
                <button onclick="loadNotifications()">Load Notifications</button>
            </div>
        </div>
        <div class="row">
            <div class="card">
                <h3>Tasks</h3>
                <pre id="tasksList">Click Refresh Tasks to load</pre>
            </div>
            <div class="card">
                <h3>Stats</h3>
                <pre id="statsData">Click Load Stats</pre>
            </div>
        </div>
        <div class="row">
            <div class="card">
                <h3>Notifications</h3>
                <pre id="notificationsList">Click Load Notifications</pre>
            </div>
            <div class="card">
                <h3>Health Check</h3>
                <button onclick="loadHealth()">Check Health</button>
                <pre id="healthData">Click Check Health</pre>
            </div>
        </div>
    </div>
    <script>
        function showToast(message, type = 'info') {
            const toast = document.createElement('div');
            toast.className = 'toast toast-' + type;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }

        async function apiCall(url, method = 'GET', body = null) {
            const opts = { method, headers: {} };
            if (body) {
                opts.body = JSON.stringify(body);
                opts.headers['Content-Type'] = 'application/json';
            }
            try {
                const res = await fetch(url, opts);
                const text = await res.text();
                try { return { data: JSON.parse(text), status: res.status }; }
                catch { return { data: text, status: res.status }; }
            } catch (err) {
                return { data: { error: err.message }, status: 0 };
            }
        }

        async function loadTasks() {
            const { data, status } = await apiCall('/api/tasks');
            if (status === 200) {
                document.getElementById('tasksList').textContent = JSON.stringify(data, null, 2);
            } else {
                document.getElementById('tasksList').textContent = 'Error: ' + JSON.stringify(data);
                showToast('Failed to load tasks', 'error');
            }
        }

        async function loadStats() {
            const { data, status } = await apiCall('/api/tasks/stats');
            if (status === 200) {
                document.getElementById('statsData').textContent = JSON.stringify(data, null, 2);
                showToast('Stats loaded: ' + data.total + ' tasks', 'info');
            } else {
                document.getElementById('statsData').textContent = 'Error: ' + JSON.stringify(data);
                showToast('Failed to load stats', 'error');
            }
        }

        async function loadServicesStatus() {
            const { data, status } = await apiCall('/api/services/status');
            if (status === 200) {
                const ts = document.getElementById('tsStatus');
                const ns = document.getElementById('nsStatus');
                ts.textContent = 'Task Service: ' + (data.task_service === 'healthy' ? 'UP' : 'DOWN');
                ts.className = data.task_service === 'healthy' ? 'status-healthy' : 'status-unhealthy';
                ns.textContent = 'Notification Service: ' + (data.notification_service === 'healthy' ? 'UP' : 'DOWN');
                ns.className = data.notification_service === 'healthy' ? 'status-healthy' : 'status-unhealthy';
                showToast('Services status updated', 'info');
            } else {
                showToast('Failed to check services', 'error');
            }
        }

        async function loadNotifications() {
            const { data, status } = await apiCall('/api/notifications');
            if (status === 200) {
                document.getElementById('notificationsList').textContent = JSON.stringify(data, null, 2);
            } else {
                document.getElementById('notificationsList').textContent = 'Error: ' + JSON.stringify(data);
                showToast('Failed to load notifications', 'error');
            }
        }

        async function loadHealth() {
            const { data, status } = await apiCall('/health');
            if (status === 200) {
                document.getElementById('healthData').textContent = JSON.stringify(data, null, 2);
                showToast('Health check passed', 'success');
            } else {
                document.getElementById('healthData').textContent = 'Error: ' + JSON.stringify(data);
                showToast('Health check failed', 'error');
            }
        }

        async function reprocessTasks() {
            const btn = event.target;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Processing...';
            const { data, status } = await apiCall('/api/tasks/reprocess', 'POST');
            btn.disabled = false;
            btn.textContent = 'Reprocess Pending';
            if (status === 200) {
                showToast(data.message, 'success');
                loadTasks();
                loadStats();
            } else {
                showToast('Reprocess failed: ' + JSON.stringify(data), 'error');
            }
        }

        async function createTask() {
            const title = document.getElementById('taskTitle').value;
            const desc = document.getElementById('taskDesc').value;
            if (!title) { alert('Title is required'); return; }
            const { data, status } = await apiCall('/api/tasks', 'POST', { title, description: desc });
            if (status === 201) {
                showToast('Task created: #' + data.id, 'success');
                document.getElementById('taskTitle').value = '';
                document.getElementById('taskDesc').value = '';
                loadTasks();
                loadStats();
            } else {
                showToast('Error: ' + JSON.stringify(data), 'error');
            }
        }

        // Auto-refresh every 30 seconds
        setInterval(() => {
            loadTasks();
            loadServicesStatus();
        }, 30000);

        // Initial load
        loadTasks();
        loadServicesStatus();
    </script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
