# Kubernetes Cluster Management Guide

> Task Management System deployed on Minikube across 3 environments.

## 1. Quick Start

```bash
# 1. Start minikube
minikube start

# 2. Set context for dev environment
kubectl config set-context --current --namespace=task-management-dev

# 3. Deploy dev environment
kubectl apply -f k8s/dev/

# 4. Verify pods are running
kubectl get pods -n task-management-dev

# 5. Access web UI
minikube service -n task-management-dev web-ui --url
```

## 2. Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │                  Minikube Cluster              │
                    │                                                 │
  ┌───────────────┐ │ ┌───────────────┐ │ ┌───────────────┐
  │  dev          │ │ │  staging      │ │ │  prod         │
  │  Namespace    │ │ │  Namespace    │ │ │  Namespace    │
  │               │ │ │               │ │ │               │
  │ task-svc:8000 │ │ │ task-svc:8000 │ │ │ task-svc:8000 │
  │ notify-svc:9000│ │ │notify-svc:9000│ │ │notify-svc:9000│
  │ web-ui:5000   │ │ │ web-ui:5000   │ │ │ web-ui:5000   │
  │ db:5432       │ │ │ db:5432       │ │ │ db:5432       │
  └───────────────┘ │ └───────────────┘ │ └───────────────┘
                    │                                                 │
                    └─────────────────────────────────────────────────┘
```

## 3. Environment Details

| Environment | Namespace                  | Replicas (task/notify/web) | CPU Request | Memory Request |
|-------------|----------------------------|----------------------------|-------------|----------------|
| dev         | `task-management-dev`      | 1 / 1 / 1                  | 100m        | 128Mi          |
| staging     | `task-management-staging`  | 2 / 1 / 1                  | 250m        | 256Mi          |
| prod        | `task-management-prod`     | 3 / 2 / 2                  | 500m        | 512Mi          |

> All environments share a PostgreSQL database (single instance).

## 4. Service URLs

All services are exposed via NodePort. Base IP: `192.168.49.2`

| Environment | Service            | Port  | URL                                |
|-------------|--------------------|-------|------------------------------------|
| dev         | web-ui             | 30961 | http://192.168.49.2:30961          |
| dev         | task-service       | 30000 | http://192.168.49.2:30000          |
| dev         | notification-svc   | 30001 | http://192.168.49.2:30001          |
| staging     | web-ui             | 30677 | http://192.168.49.2:30677          |
| staging     | task-service       | 30002 | http://192.168.49.2:30002          |
| staging     | notification-svc   | 30003 | http://192.168.49.2:30003          |
| prod        | web-ui             | 32270 | http://192.168.49.2:32270          |
| prod        | task-service       | 30004 | http://192.168.49.2:30004          |
| prod        | notification-svc   | 30005 | http://192.168.49.2:30005          |

## 5. Common Operations

### Check Status

```bash
# Pods across all environments
kubectl get pods -n task-management-dev
kubectl get pods -n task-management-staging
kubectl get pods -n task-management-prod

# Services and NodePorts
kubectl get svc -n task-management-dev
kubectl get svc -n task-management-staging
kubectl get svc -n task-management-prod

# Minikube node status
minikube status
```

### View Logs

```bash
# All pods in dev
kubectl logs -l app=task-service -n task-management-dev --tail=50
kubectl logs -l app=notification-service -n task-management-dev --tail=50
kubectl logs -l app=web-ui -n task-management-dev --tail=50

# Single pod
kubectl logs <pod-name> -n task-management-dev -f

# Database logs
kubectl logs -l app=db -n task-management-dev --tail=50
```

### Restart

```bash
# Restart a deployment
kubectl rollout restart deployment/task-service -n task-management-dev
kubectl rollout restart deployment/notification-service -n task-management-dev
kubectl rollout restart deployment/web-ui -n task-management-dev

# Restart database
kubectl rollout restart deployment/db -n task-management-dev
```

### Scale

```bash
# Scale task-service in staging
kubectl scale deployment/task-service --replicas=3 -n task-management-staging

# Scale web-ui in prod
kubectl scale deployment/web-ui --replicas=3 -n task-management-prod
```

### Deploy

```bash
# Deploy a specific environment
kubectl apply -f k8s/dev/
kubectl apply -f k8s/staging/
kubectl apply -f k8s/prod/

# Apply a single resource
kubectl apply -f k8s/dev/deployment-task.yaml -n task-management-dev

# Full deploy pipeline
kubectl apply -f k8s/common/
kubectl apply -f k8s/dev/
kubectl apply -f k8s/staging/
kubectl apply -f k8s/prod/
```

## 6. Troubleshooting

### Pod Stuck in Pending

```bash
# Check events
kubectl describe pod <pod-name> -n task-management-dev

# Check node resources
kubectl describe node

# Check if minikube has enough resources
minikube config get memory
minikube config get cpus

# Restart minikube with more resources
minikube stop
minikube start --memory=8192 --cpus=4
```

### Pod CrashLoopBackOff

```bash
# Check container logs
kubectl logs <pod-name> -n task-management-dev --previous

# Check environment variables
kubectl exec <pod-name> -n task-management-dev -- env

# Check configmaps and secrets
kubectl get configmaps -n task-management-dev
kubectl get secrets -n task-management-dev
```

### ImagePullBackOff

```bash
# Verify image exists
docker pull <image-name>

# Check image name in deployment
kubectl get deployment <name> -n task-management-dev -o yaml | grep image

# If using local images, ensure they're in minikube
minikube image load <image-name>

# Or load all local images
minikube image load $(docker images --format '{{.Repository}}:{{.Tag}}' | grep task-management)
```

### Database Connection Refused

```bash
# Verify database pod is running
kubectl get pods -l app=db -n task-management-dev

# Test connectivity from another pod
kubectl run -it --rm debug --image=postgres --restart=Never -n task-management-dev -- psql -h <db-service> -U <user> -d <dbname>

# Check database logs
kubectl logs -l app=db -n task-management-dev --tail=100

# Check service DNS
kubectl run -it --rm dns-test --image=busybox --restart=Never -n task-management-dev -- nslookup <db-service>
```

### Port Already in Use

```bash
# Stop minikube
minikube stop

# Remove stale state
minikube delete

# Start fresh
minikube start
```

## 7. Backup & Restore

### Backup

```bash
# Backup all namespaces
kubectl get all --all-namespaces -o yaml > backup/all-resources.yaml

# Backup persistent volumes
kubectl get pv -o yaml > backup/all-pv.yaml

# Backup etcd snapshot (if using etcd storage)
minikube ssh -- sudo docker exec etcd etcdctl snapshot save /tmp/etcd-snapshot.db

# Backup database directly
kubectl exec -it <db-pod-name> -n task-management-dev -- pg_dump -U <user> <dbname> > backup/db-dump.sql
```

### Restore

```bash
# Restore all resources
kubectl apply -f backup/all-resources.yaml

# Restore persistent volumes
kubectl apply -f backup/all-pv.yaml

# Restore database
kubectl exec -i <db-pod-name> -n task-management-dev -- psql -U <user> <dbname> < backup/db-dump.sql
```

### Automated Backup (CronJob)

```bash
# Create a cronjob for daily DB backups
kubectl create cronjob db-backup \
  --image=postgres:15 \
  --schedule="0 2 * * *" \
  -- kubectl exec -i <db-pod> -n task-management-dev -- pg_dump -U <user> <dbname> > /backups/db-$(date +\%F).sql
```

## 8. Cleanup

### Remove a Single Environment

```bash
# Delete all resources in dev
kubectl delete namespace task-management-dev

# Delete all resources in staging
kubectl delete namespace task-management-staging

# Delete all resources in prod
kubectl delete namespace task-management-prod
```

### Remove All Environments

```bash
kubectl delete namespace task-management-dev task-management-staging task-management-prod
```

### Full Minikube Reset

```bash
# Stop and delete minikube
minikube stop
minikube delete

# Start fresh
minikube start
```

### Remove All Deployed Resources (Keep Minikube Running)

```bash
kubectl delete -f k8s/dev/ --ignore-not-found
kubectl delete -f k8s/staging/ --ignore-not-found
kubectl delete -f k8s/prod/ --ignore-not-found
kubectl delete -f k8s/common/ --ignore-not-found
kubectl delete pvc --all -A --ignore-not-found
```
