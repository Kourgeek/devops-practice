# Secman — Security Manager

Управление секретами с шифрованием, аудитом действий и веб-интерфейсом.

## Быстрый старт

```bash
# Запуск
docker compose up -d

# Проверка
curl http://localhost:9090/health

# Остановка
docker compose down
```

## Режим разработки

```bash
docker compose up -d --build
```

Файлы `secman/` монтируются напрямую в контейнер с автоперезагрузкой.

## Веб-интерфейс

### Доступ

| URL | Описание |
|-----|----------|
| `http://localhost:9090/` | Редирект на страницу входа |
| `http://localhost:9090/login` | Страница входа |
| `http://localhost:9090/register` | Регистрация нового пользователя |
| `http://localhost:9090/dashboard` | Основной дашборд (требует авторизации) |

### Дефолтный пользователь

| Поле | Значение |
|------|----------|
| Логин | `admin` |
| Пароль | `admin123` |

> **Важно:** В продакшене измените `SECMAN_DEFAULT_USER` и `SECMAN_DEFAULT_PASSWORD` в `.env`.

### Возможности UI

- **Список секретов** — таблица с пагинацией, поиском, просмотром/копированием значений
- **Добавление/редактирование** — модальное окно с формой
- **Удаление** — с подтверждением
- **Импорт из Jenkins** — вставка JSON с credentials
- **Журнал аудита** — все действия с фильтрацией по типу
- **Статистика** — общее количество секретов, созданные сегодня, записи аудита

## API

### Аутентификация

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/register` | Регистрация (username, password) |
| POST | `/api/auth/login` | Логин → возвращает JWT token |
| GET | `/api/auth/me` | Текущий пользователь (требует JWT) |

**Пример регистрации:**
```bash
curl -X POST http://localhost:9090/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"mike","password":"secret123"}'
```

**Пример логина:**
```bash
curl -X POST http://localhost:9090/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

**Ответ:**
```json
{
  "message": "Login successful",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "username": "admin"
}
```

### Защита API

Все endpoints кроме `/health`, `/api/auth/*` и UI-маршрутов требуют JWT:

```bash
curl http://localhost:9090/api/secrets \
  -H "Authorization: Bearer <your-token>"
```

Без токена или с неверным → `401 Unauthorized`.

### Secrets CRUD

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/secrets` | Создать секрет |
| GET | `/api/secrets` | Список секретов (`?page=1&per_page=50`) |
| GET | `/api/secrets/{id}` | Получить секрет (зашифрованное значение) |
| PUT | `/api/secrets/{id}` | Обновить секрет |
| DELETE | `/api/secrets/{id}` | Удалить секрет |
| POST | `/api/secrets/import` | Импортировать из Jenkins |
| GET | `/api/audit` | Журнал аудита (`?page=1&per_page=50&action=CREATE`) |

### Health check

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Health check (без авторизации) |

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `POSTGRES_USER` | Пользователь БД | `secman` |
| `POSTGRES_PASSWORD` | Пароль БД | `secman123` |
| `POSTGRES_DB` | Имя БД | `secman_db` |
| `SECMAN_SECRET_KEY` | Ключ шифрования | `dev-secret-key-change-in-prod` |
| `SECMAN_JWT_SECRET` | Ключ JWT-токенов | `jwt-secret-change-in-prod` |
| `SECMAN_DEFAULT_USER` | Дефолтный пользователь | `admin` |
| `SECMAN_DEFAULT_PASSWORD` | Пароль дефолтного пользователя | `admin123` |
| `SECMAN_JENKINS_URL` | URL Jenkins | `http://jenkins:8080` |
| `SECMAN_JENKINS_API_TOKEN` | Токен Jenkins | `dev-token` |

## Структура проекта

```
secman/
├── docker-compose.yml          # Основная конфигурация
├── docker-compose.override.yml # Dev-переопределения
├── .env                        # Переменные окружения
├── .gitignore
├── README.md
└── secman/
    ├── Dockerfile
    ├── app.py                  # Flask приложение (API + UI)
    ├── config.py               # Конфигурация
    ├── requirements.txt        # Зависимости
    ├── templates/              # HTML-шаблоны
    │   ├── login.html          # Страница входа
    │   ├── register.html       # Страница регистрации
    │   └── dashboard.html      # Основной дашборд
    ├── static/                 # Статика
    │   └── app.js              # Фронтенд-логика
    ├── database/               # Данные БД
    └── migrations/             # Миграции
```

## Безопасность

- Секреты шифруются алгоритмом Fernet (AES-128-CBC + HMAC-SHA256)
- Пароли пользователей хешируются через `werkzeug.security` (PBKDF2)
- API защищено JWT-токенами (срок действия: 24 часа)
- Все действия логируются в таблицу `audit_log`
- В продакшене обязательно смените `SECMAN_SECRET_KEY`, `SECMAN_JWT_SECRET` и дефолтный пароль

## Тестирование

### 1. Запуск
```bash
cd secman
docker compose up -d --build
```

### 2. Проверка health
```bash
curl http://localhost:9090/health
```

### 3. Регистрация нового пользователя
```bash
curl -X POST http://localhost:9090/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass123"}'
```

### 4. Логин и получение токена
```bash
curl -X POST http://localhost:9090/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### 5. Использование токена
```bash
TOKEN="<your-token-here>"

# Создать секрет
curl -X POST http://localhost:9090/api/secrets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key_name":"DATABASE_URL","value":"postgres://host:5432/db","description":"Main DB"}'

# Получить список
curl http://localhost:9090/api/secrets \
  -H "Authorization: Bearer $TOKEN"

# Без токена → 401
curl http://localhost:9090/api/secrets
```

### 6. Веб-интерфейс
Откройте в браузере:
- **Вход:** http://localhost:9090/login
- **Регистрация:** http://localhost:9090/register
- **Дашборд:** http://localhost:9090/dashboard

Дефолтный логин: `admin` / `admin123`
