.PHONY: clean infra deploy-app forward stop validate all

# 1. Очистка проекта от мусора
clean:
	@echo "🧹 Удаляем ненужные файлы и кэш..."
	find . -type d -name "node_modules" -exec rm -rf {} +
	find . -type d -name ".terraform" -exec rm -rf {} +
	rm -rf *.log .cache

# 2. Подъем инфраструктуры (Jenkins + Vault)
infra:
	@echo "🏗 Поднимаем Jenkins и Vault..."
	docker-compose -f docker-compose.infra.yml up -d

# 3. Деплой приложения в Куб (Dev, Stage, Prod)
deploy-app:
	@echo "🚀 Деплой в Kubernetes..."
	kubectl create namespace dev --dry-run=client -o yaml | kubectl apply -f -
	kubectl create namespace stage --dry-run=client -o yaml | kubectl apply -f -
	kubectl create namespace prod --dry-run=client -o yaml | kubectl apply -f -
	@echo "⚠️ Замени эту строку на реальный деплой манифестов/Helm!"

# 4. Проброс портов
forward:
	chmod +x scripts/port-forward.sh
	./scripts/port-forward.sh

# 5. Валидация
validate:
	@echo "🔍 Проверяем доступность сервисов..."
	@curl -s -o /dev/null -w "Jenkins: %{http_code}\n" http://localhost:8080/login
	@curl -s -o /dev/null -w "Vault: %{http_code}\n" http://localhost:8200/ui/
	@curl -s -o /dev/null -w "App Dev: %{http_code}\n" http://localhost:8081 || echo "Dev: Pending"
	@kubectl get pods -A | grep devops-practice

# 6. Остановка всего
stop:
	pkill -f "kubectl port-forward"
	docker-compose -f docker-compose.infra.yml down

# Полный цикл
all: clean infra deploy-app forward validate
