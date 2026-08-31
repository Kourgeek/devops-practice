# DevOps Practice - Task Management System

## Architecture

```
                    ┌──────────────────────────────────────────────────┐
                    │                  Ingress                         │
                    │              task-management.local               │
                    └─────────────────────┬──────────────────────────┘
                                          │
                                    ┌─────▼─────┐
                                    │  Web UI   │  (port 5000)
                                    │  Flask    │
                                    └─────┬─────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                             │               │
              ┌─────▼─────┐               ┌─────▼──────────┐
              │Task Service│               │Notification      │
              │  (port 8000)│               │Service (9000)   │
              │ FastAPI +  │               │ Flask           │
              │asyncpg     │               └─────┬───────────┘
              └─────┬──────┘                     │
                    │                     ┌─────▼───────────┐
                    │                     │  Notification     │
              ┌─────▼─────┐              │  DB (_notification)│
              │  PostgreSQL│              └───────────────────┘
              │  (taskdb)  │
              └────────────┘
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Web UI | 5000 | Flask dashboard with interactive UI |
| Task Service | 8000 | FastAPI REST API for task management |
| Notification Service | 9000 | Flask service for notifications |
| PostgreSQL | 5432 | Database (shared by task-service and notification-service) |
| Adminer | 8080 | Database admin UI (development only) |

## Quick Start

### Run all services (Docker Compose):
```bash
docker-compose up --build
# or in background:
docker-compose up --build -d
```

### Stop services:
```bash
docker-compose down
docker-compose down -v    # Stop and remove volumes
```

### Local development (hot-reload):
```bash
# docker-compose.override.yml is auto-loaded
docker-compose up --build
# Changes to source files are auto-reloaded
```

## Endpoints

### Web UI (http://localhost:5000)
- `GET /` — Dashboard with interactive UI
- `GET /health` — Health check

### Task Service (http://localhost:8000)
- `GET /` — Dashboard
- `GET /health` — Health check
- `POST /tasks` — Create task
- `GET /tasks` — List all tasks (optional: `?status=pending|in_progress|completed`)
- `GET /tasks/{id}` — Get task by ID
- `PUT /tasks/{id}` — Update task status
- `DELETE /tasks/{id}` — Delete task
- `GET /tasks/{id}/complete` — Mark task as completed
- `GET /stats` — Get task statistics
- `POST /tasks/reprocess` — Manually reprocess pending tasks

### Notification Service (http://localhost:9000)
- `GET /` — Dashboard
- `GET /health` — Health check
- `POST /notify` — Send notification
- `GET /notifications` — List all notifications
- `GET /notifications/{id}` — Get notification by ID
- `GET /notifications/task/{task_id}` — Get notifications for a task
- `GET /notifications/stats` — Get notification statistics

### Adminer (http://localhost:8080)
- Database admin UI
- Server: `db`
- Username: `devops`
- Password: `devops123`
- Database: `taskdb` (task-service), `taskdb_notification` (notification-service)

## Task Lifecycle (State Machine)

```
pending ──→ in_progress ──→ completed
   │              │
   │              └──→ failed (on error)
   └──→ (auto-processed by background worker)
```

- **pending**: Task created, waiting to be processed (default)
- **in_progress**: Background worker picked up the task
- **completed**: Task processing finished successfully
- Tasks stay in `pending` for `PROCESSING_TIMEOUT` seconds (default: 30s) before auto-processing
- Use `POST /tasks/reprocess` to manually trigger pending task processing

## Health Checks

Each service performs periodic health checks on other services every `HEALTH_CHECK_INTERVAL` seconds (configurable).

## Testing

### Run tests for all services:
```bash
docker-compose exec task-service pytest tests/ -v
docker-compose exec notification-service pytest tests/ -v
docker-compose exec web-ui pytest tests/ -v
```

### Run tests locally (requires Python installed):
```bash
cd task-service && pip install -r requirements.txt && pytest tests/ -v
cd notification-service && pip install -r requirements.txt && pytest tests/ -v
cd web-ui && pip install -r requirements.txt && pytest tests/ -v
```

## Docker Compose

### Networks
- `devops_network` — Bridge network for inter-service communication

### Volumes
- `pgdata` — Persistent PostgreSQL data

### Environment Variables (.env)
| Variable | Description | Default |
|----------|-------------|---------|
| DB_USER | PostgreSQL username | devops |
| DB_PASSWORD | PostgreSQL password | devops123 |
| DB_NAME | Database name for task-service | taskdb |
| POSTGRES_USER | PostgreSQL user | devops |
| POSTGRES_PASSWORD | PostgreSQL password | devops123 |
| POSTGRES_DB | PostgreSQL database | taskdb |
| HEALTH_CHECK_INTERVAL | Health check interval (seconds) | 30 |
| PROCESSING_TIMEOUT | Pending task timeout (seconds) | 30 |
| TASK_SERVICE_URL | Task Service URL | http://task-service:8000 |
| NOTIFICATION_SERVICE_URL | Notification Service URL | http://notification-service:9000 |

## Kubernetes Deployment

### Prerequisites
- kubectl
- helm (v3+)
- Docker
- 3 kubectl contexts: `k8s-dev`, `k8s-staging`, `k8s-prod`

### Deploy via Helm (recommended)

#### Deploy to all 3 clusters:
```powershell
# PowerShell (Windows)
.\deploy.ps1 all
```

```bash
# Bash (Linux/Mac)
./deploy.sh all
```

#### Deploy to a single cluster:
```powershell
.\deploy.ps1 dev
.\deploy.ps1 staging
.\deploy.ps1 prod
```

```bash
./deploy.sh dev
./deploy.sh staging
./deploy.sh prod
```

#### Clean up:
```powershell
.\deploy.ps1 clean all
.\deploy.ps1 clean dev
```

```bash
./deploy.sh clean all
./deploy.sh clean dev
```

#### Check status:
```powershell
.\deploy.ps1 status
```

```bash
./deploy.sh status
```

### Environment-specific configurations

| Environment | Namespace | Replicas (per service) | Resources | HPA | PDB |
|-------------|-----------|------------------------|-----------|-----|-----|
| dev | `task-management-dev` | 1 | Minimal | No | No |
| staging | `task-management-staging` | 2 | Medium | No | No |
| prod | `task-management-prod` | 3 | Max | Yes (3-10) | Yes (min 2) |

### Kustomize (alternative to Helm)
```bash
# Dev
kubectl kustomize k8s/overlays/dev | kubectl apply -f -

# Staging
kubectl kustomize k8s/overlays/staging | kubectl apply -f -

# Prod
kubectl kustomize k8s/overlays/prod | kubectl apply -f -
```

### Helm manual deploy
```bash
# Dev
helm install task-management-dev ./helm -f ./helm/values-dev.yaml --namespace task-management-dev --create-namespace

# Staging
helm install task-management-staging ./helm -f ./helm/values-staging.yaml --namespace task-management-staging --create-namespace

# Prod
helm install task-management-prod ./helm -f ./helm/values-prod.yaml --namespace task-management-prod --create-namespace
```

### Helm upgrade
```bash
helm upgrade task-management-dev ./helm -f ./helm/values-dev.yaml --namespace task-management-dev
helm upgrade task-management-staging ./helm -f ./helm/values-staging.yaml --namespace task-management-staging
helm upgrade task-management-prod ./helm -f ./helm/values-prod.yaml --namespace task-management-prod
```

### Helm uninstall
```bash
helm uninstall task-management-dev -n task-management-dev
helm uninstall task-management-staging -n task-management-staging
helm uninstall task-management-prod -n task-management-prod
```

## Production Features (prod environment)

- **Horizontal Pod Autoscaler (HPA)**: Auto-scales task-service and web-ui from 3 to 10 replicas based on CPU/memory
- **Pod Disruption Budgets (PDB)**: Ensures minimum 2 pods are always available during rolling updates
- **Network Policies**: Restricts ingress/egress traffic
- **TLS**: HTTPS termination via Ingress
- **Health probes**: Liveness, readiness, and startup probes on all services
- **Rolling updates**: Zero-downtime deployments with maxSurge=1, maxUnavailable=0

## Project Structure

```
devops_practice/
├── docker-compose.yml           # Base Docker Compose
├── docker-compose.override.yml  # Dev overrides (hot-reload)
├── .env                         # Environment variables
├── README.md
├── deploy.sh                    # Bash deploy script
├── deploy.ps1                   # PowerShell deploy script
├── deploy.log                   # Deploy log (auto-generated)
├── task-service/
│   ├── Dockerfile
│   ├── app.py                   # FastAPI + async SQLAlchemy + background worker
│   ├── requirements.txt
│   └── tests/
│       ├── __init__.py
│       └── test_app.py
├── notification-service/
│   ├── Dockerfile
│   ├── app.py                   # Flask + SQLAlchemy 2.x
│   ├── dashboard.html
│   ├── requirements.txt
│   └── tests/
│       ├── __init__.py
│       └── test_app.py
├── web-ui/
│   ├── Dockerfile
│   ├── app.py                   # Flask + httpx proxy + improved UI
│   ├── requirements.txt
│   └── tests/
│       ├── __init__.py
│       └── test_app.py
├── k8s/
│   ├── base/
│   │   ├── k8s-base.yaml        # Namespace, ConfigMap, Secret, PVC, Services, Ingress
│   │   └── deployments.yaml     # All Deployments
│   └── overlays/
│       ├── dev/
│       │   └── kustomization.yaml
│       ├── staging/
│       │   └── kustomization.yaml
│       └── prod/
│           ├── kustomization.yaml
│           ├── hpa-task-service.yaml
│           ├── hpa-web-ui.yaml
│           ├── network-policy.yaml
│           ├── pdb-task-service.yaml
│           └── pdb-web-ui.yaml
└── helm/
    ├── Chart.yaml
    ├── values.yaml              # Default values
    ├── values-dev.yaml          # Dev overrides
    ├── values-staging.yaml      # Staging overrides
    ├── values-prod.yaml         # Prod overrides
    ├── .helmignore
    └── templates/
        └── deployments.yaml     # All K8s resource templates
```

## Changelog

### v1.1.0 (2026-08-31)
- **Fixed**: Tasks stuck in `pending` — added background worker with state machine (pending → in_progress → completed)
- **Fixed**: notification-service — deprecated SQLAlchemy 2.x API (`query().get()` → `session.get()`)
- **Added**: `POST /tasks/reprocess` endpoint for manual pending task processing
- **Added**: K8s manifests (base + overlays for dev/staging/prod)
- **Added**: Helm chart with environment-specific values
- **Added**: Deploy scripts (bash + PowerShell) for 3-cluster deployment
- **Added**: docker-compose health checks and resource limits
- **Added**: docker-compose.override.yml for local hot-reload
- **Improved**: web-ui — added toast notifications, auto-refresh, reprocess button, error handling
- **Improved**: Task service dashboard — added "Reprocess Pending" button

### v1.0.0 (previous)
- Initial release
