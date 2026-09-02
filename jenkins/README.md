## Jenkins CI/CD — Docker проект

### Структура проекта

```
jenkins/
├── docker-compose.yml          # Основной файл docker-compose
├── docker-compose.override.yml # Dev окружение (debug, volume mounts)
├── .env                        # Переменные окружения
├── jenkins/
│   ├── Dockerfile              # Кастомный образ Jenkins
│   ├── plugins.txt             # Список плагинов для установки
│   ├── jenkins-home/           # Данные Jenkins (монтируются в volume)
│   │   └── .gitkeep
│   └── config/                 # Начальная конфигурация (CASC)
├── .gitkeep
└── README.md
```

### Быстрый старт

#### 1. Запуск

```powershell
# Скопировать файл переменных
Copy-Item .env.example .env   # если есть .env.example

# Собрать образ и запустить
docker compose up -d --build

# Проверить статус
docker compose ps
```

#### 2. Первичная настройка

1. Откройте браузер: http://localhost:8080
2. Получите начальный пароль:
   ```powershell
   docker compose exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
   ```
3. Вставьте пароль в веб-интерфейс
4. Создайте административного пользователя (из .env: `admin` / `admin123`)
5. Установите предложенные плагины или выберите произвольные

#### 3. Остановка

```powershell
# Остановить и сохранить данные
docker compose down

# Остановить и удалить данные (внимание: все данные будут потеряны)
docker compose down -v
```

### Переменные окружения (.env)

| Переменная | Описание | Значение по умолчанию |
|---|---|---|
| `JENKINS_USER` | Имя пользователя администратора | `admin` |
| `JENKINS_PASSWORD` | Пароль администратора | `admin123` |
| `JENKINS_URL` | URL доступа к Jenkins | `http://localhost:8080` |

### Порты

| Порт | Назначение |
|---|---|
| `8080` | Веб-интерфейс Jenkins |
| `50000` | Агент (JNLP) |
| `5005` | Debug (только в dev, из override) |

### Dev окружение

Файл `docker-compose.override.yml` автоматически подключается Docker Compose при запуске. Он:

- Монтирует директорию `jenkins/config/` как `/var/jenkins_home/init.groovy.d` для Groovy-скриптов инициализации
- Включает debug-порт `5005` для удалённой отладки
- Добавляет CSP-заголовки для разработки

```powershell
# Запуск в dev режиме (override применяется автоматически)
docker compose up -d --build
```

### Управление плагинами

Плагины перечислены в `jenkins/plugins.txt`. Для добавления нового плагина:

1. Добавьте имя плагина в `jenkins/plugins.txt`
2. Пересоберите образ:
   ```powershell
   docker compose up -d --build
   ```

### Восстановление доступа

Если забыли пароль:

```powershell
# Сбросить пароль через Groovy скрипт
docker compose exec jenkins groovysh -e '
  def h = jenkins.model.Jenkins.getInstance()
  def hudsonHome = h.getRootDir()
  def user = hudson.security.HudsonPrivateSecurityRealm.getCurrentUser()
  println "Current user: " + (user ? user.getId() : "none")
'

# Или создать нового пользователя через CLI
docker compose exec jenkins java -jar /usr/share/jenkins/jenkins-cli.jar -s http://localhost:8080 create-user admin admin123 admin@example.com
```

### Troubleshooting

**Jenkins не запускается:**
```powershell
# Проверить логи
docker compose logs jenkins

# Проверить права на volume
docker volume inspect jenkins_jenkins-data
```

**Проблема с правами:**
```powershell
# Пересоздать volume с правильными правами
docker compose down -v
docker volume rm jenkins_jenkins-data
docker compose up -d
```

**Конфликт портов:**
```powershell
# Проверить занятые порты
netstat -ano | findstr :8080
netstat -ano | findstr :50000
```

### Безопасность

> ⚠️ **Важно:** Это конфигурация для разработки. Для продакшена:
> - Измените пароль по умолчанию
> - Используйте HTTPS (reverse proxy)
> - Настройте брандмауэр
> - Включите аутентификацию и авторизацию
> - Регулярно делайте бэкапы `jenkins/jenkins-home`
