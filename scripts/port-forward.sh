#!/bin/bash
# Скрипт для проброса всех портов на локальную машину

echo "🚀 Запуск Port-Forwarding для всех сервисов..."

# Очистка старых процессов port-forward
pkill -f "kubectl port-forward" 2>/dev/null
pkill -f "docker-compose" 2>/dev/null

# 1. Инфраструктура (Docker Compose)
docker-compose -f docker-compose.infra.yml up -d
echo "✅ Jenkins: http://localhost:8080"
echo "✅ Vault UI: http://localhost:8200"

# 2. Kubernetes App (Dev, Stage, Prod)
kubectl port-forward -n dev svc/devops-practice-svc 8081:80 &> /dev/null &
kubectl port-forward -n stage svc/devops-practice-svc 8082:80 &> /dev/null &
kubectl port-forward -n prod svc/devops-practice-svc 8083:80 &> /dev/null &

echo "✅ App DEV:  http://localhost:8081"
echo "✅ App STAGE: http://localhost:8082"
echo "✅ App PROD: http://localhost:8083"
echo "🎉 Все сервисы доступны! Для остановки выполни: make stop"
