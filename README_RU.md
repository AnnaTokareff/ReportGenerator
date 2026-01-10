# Meeting Reporter - Генератор отчетов из аудио встреч

## 📋 Описание проекта

Этот проект представляет собой API для автоматической генерации отчетов из аудиофайлов встреч. Проект реализует:

1. **Генератор отчетов (Report Generator)** - основная функциональность:
   - Автоматическая транскрипция аудиофайлов в текст
   - Извлечение структурированной информации (темы, решения, задачи)
   - Эффективная генерация отчетов в формате Markdown (быстро и бесплатно)

2. **Support Agent** - простой агент поддержки:
   - Поиск информации в транскриптах встреч пользователя
   - Ответы на вопросы на основе данных из базы

## 🏗️ Архитектура проекта

### Структура папок

```
meeting_reporter/
├── app/                          # Основное приложение
│   ├── api/                      # API endpoints (роутеры)
│   │   ├── auth.py              # Аутентификация (регистрация, вход)
│   │   ├── health.py            # Проверка здоровья API
│   │   ├── meetings_api.py       # API для работы с встречами
│   │   └── support_api.py       # API для support агента
│   ├── core/                     # Основные настройки
│   │   ├── config.py            # Конфигурация приложения
│   │   └── security.py          # JWT токены, хеширование паролей
│   ├── db/                       # Работа с базой данных
│   │   ├── base.py              # Базовый класс для моделей
│   │   └── session.py           # Управление сессиями БД
│   ├── models/                   # Модели базы данных (SQLAlchemy)
│   │   ├── user.py              # Модель пользователя
│   │   └── meeting_models.py    # Модели встреч, транскриптов, решений, задач
│   ├── schemas/                  # Pydantic схемы (валидация данных)
│   │   ├── user.py              # Схемы для пользователей
│   │   ├── meeting_schemas.py   # Схемы для встреч
│   │   └── token.py             # Схемы для токенов
│   ├── services/                 # Бизнес-логика
│   │   ├── audio/               # Обработка аудио
│   │   │   └── transcription_service.py  # Транскрипция через OpenAI Whisper
│   │   ├── llm/                 # Работа с LLM
│   │   │   └── analysis_service.py       # Анализ транскриптов через GPT
│   │   └── analysis/             # Генерация отчетов
│   │       └── report_service.py  # Создание Markdown отчетов
│   └── utils/                    # Вспомогательные функции
│       └── file_handler.py       # Работа с файлами (сохранение, удаление)
├── alembic/                      # Миграции базы данных
├── main.py                       # Точка входа приложения
├── requirements.txt              # Зависимости Python
├── pyproject.toml               # Конфигурация проекта
└── .env                         # Переменные окружения (создать вручную)
```

## 🔧 Как работает код

### 1. Точка входа: `main.py`

Это главный файл, который запускает FastAPI приложение.

**Что делает:**
- Создает экземпляр FastAPI приложения
- Настраивает CORS (разрешает запросы с других доменов)
- Подключает все роутеры (auth, meetings, support)
- Управляет жизненным циклом (запуск/остановка)

**Ключевые части:**
```python
app = FastAPI(...)  # Создание приложения
app.include_router(...)  # Подключение роутеров
```

### 2. Модели базы данных: `app/models/`

**`user.py`** - модель пользователя:
- `id` - уникальный идентификатор
- `username` - имя пользователя
- `hashed_password` - хешированный пароль
- `meetings` - связь с встречами пользователя

**`meeting_models.py`** - модели для встреч:

- **`Meeting`** - основная модель встречи:
  - `id`, `user_id`, `title`
  - `audio_file_path` - путь к аудиофайлу
  - `status` - статус обработки (pending, processing, completed, failed)
  - `language` - язык встречи
  - Связи: transcription, topics, decisions, action_items

- **`Transcription`** - транскрипт встречи:
  - `full_text` - полный текст транскрипции
  - `summary` - краткое резюме
  - `language` - язык
  - `segments` - сегменты с временными метками (JSON)

- **`MeetingTopic`** - темы обсуждения:
  - `topic_name` - название темы
  - `relevance_score` - релевантность (0.0-1.0)

- **`Decision`** - принятые решения:
  - `decision_text` - текст решения
  - `context` - контекст
  - `participants` - участники (JSON массив)

- **`ActionItem`** - задачи из встречи:
  - `task_description` - описание задачи
  - `assignee` - ответственный
  - `due_date` - срок выполнения
  - `priority` - приоритет (low, medium, high, urgent)
  - `status` - статус (todo, in_progress, completed, cancelled)

### 3. API Endpoints: `app/api/`

#### `meetings_api.py` - работа с встречами

**POST `/meetings/upload`** - загрузка аудиофайла:
1. Принимает файл, название встречи, язык
2. Валидирует файл (тип, размер)
3. Сохраняет файл на диск
4. Создает запись Meeting в БД со статусом PENDING
5. Запускает фоновую задачу для обработки
6. Возвращает информацию о встрече

**GET `/meetings`** - список всех встреч пользователя

**GET `/meetings/{id}`** - детали встречи:
- Возвращает встречу со всеми связанными данными (транскрипт, темы, решения, задачи)

**GET `/meetings/{id}/status`** - статус обработки:
- Позволяет проверить, завершена ли транскрипция
- Возвращает прогресс (0%, 50%, 100%)

**POST `/meetings/{id}/report`** - генерация отчета:
- Создает Markdown отчет из данных встречи
- Можно включить/исключить транскрипт, временные метки

**DELETE `/meetings/{id}`** - удаление встречи:
- Удаляет запись из БД и аудиофайл с диска

**Фоновая задача `process_meeting_transcript`:**
1. Меняет статус на PROCESSING
2. Вызывает OpenAI Whisper API для транскрипции
3. Сохраняет транскрипт в БД
4. Вызывает GPT для анализа (извлечение тем, решений, задач)
5. Сохраняет результаты анализа
6. Меняет статус на COMPLETED

#### `support_api.py` - support агент с semantic search

**POST `/support/query`** - задать вопрос:
1. Принимает вопрос пользователя
2. Использует semantic search (sentence-transformers на CPU) для поиска в транскриптах
3. Находит наиболее релевантные фрагменты текста по смыслу (не только по ключевым словам)
4. Формирует ответ на основе найденных данных
5. Возвращает ответ с оценкой уверенности (confidence)

**Как работает semantic search:**
- Использует модель `all-MiniLM-L6-v2` (легкая, работает на CPU без GPU)
- Разбивает транскрипты на чанки (фрагменты по ~500 символов)
- Создает векторные представления (embeddings) для вопроса и всех чанков
- Находит наиболее похожие чанки по cosine similarity
- Работает бесплатно, не требует GPU, но медленнее чем keyword search

**GET `/support/meetings`** - список встреч для поиска

### 4. Сервисы: `app/services/`

#### `audio/transcription_service.py` - транскрипция

**Класс `TranscriptionService`:**
- Использует OpenAI Whisper API
- Метод `transcribe_audio()`:
  - Принимает путь к аудиофайлу и язык
  - Отправляет файл в OpenAI
  - Получает текст, язык, сегменты с временными метками
  - Возвращает структурированный результат

#### `llm/analysis_service.py` - анализ транскриптов

**Класс `MeetingAnalysisService`:**
- Использует GPT-4o-mini для анализа
- Метод `analyze_transcription()`:
  - Принимает текст транскрипции
  - Отправляет промпт в GPT с инструкцией извлечь:
    - Резюме (summary)
    - Темы (topics) с релевантностью
    - Решения (decisions) с контекстом
    - Задачи (action_items) с приоритетами и сроками
  - Парсит JSON ответ
  - Возвращает структурированные данные

#### `analysis/report_service.py` - генерация отчетов

**Класс `ReportService`:**
- Использует эффективный шаблонный подход для генерации отчетов
- **Преимущества:**
  - Мгновенная генерация (нет задержки на API)
  - Бесплатно (не тратит токены OpenAI)
  - Предсказуемый и стабильный формат
  - Идеально для MVP и массовой генерации

- Метод `generate_markdown()`:
  - Принимает объект Meeting со всеми данными
  - Форматирует данные в Markdown:
    - Заголовок с метаданными
    - Резюме
    - Список тем
    - Список решений
    - Список задач
    - Полный транскрипт (опционально)
  - Возвращает строку Markdown

### 5. Утилиты: `app/utils/`

#### `file_handler.py` - работа с файлами

**Класс `FileHandler`:**
- `save_audio_file()` - сохранение аудиофайла:
  - Валидация типа файла (mp3, wav, ogg, m4a, mp4)
  - Валидация размера (макс 25MB)
  - Генерация уникального имени файла
  - Сохранение в папку `uploads/`
  - Извлечение метаданных (длительность через pydub)
  
- `delete_file()` - удаление файла

### 6. Конфигурация: `app/core/`

#### `config.py` - настройки приложения

**Класс `Settings`:**
- Читает переменные окружения из `.env`
- Настройки JWT (секретный ключ, время жизни токенов)
- Настройки БД (SQLite по умолчанию, можно PostgreSQL)
- CORS настройки

#### `security.py` - безопасность

- `hash_password()` - хеширование паролей (bcrypt)
- `verify_password()` - проверка пароля
- `create_access_token()` - создание JWT токена
- `get_current_user()` - получение текущего пользователя из токена

### 7. База данных: `app/db/`

#### `session.py` - управление сессиями

**Класс `DatabaseSessionManager`:**
- Создает асинхронный движок SQLAlchemy
- Управляет сессиями БД
- Метод `session()` - контекстный менеджер для работы с БД

**Функция `get_db()`:**
- Dependency для FastAPI
- Создает сессию для каждого запроса
- Автоматически закрывает после запроса

## 🚀 Установка и запуск

### Требования

- Python 3.11+
- OpenAI API ключ (для транскрипции и анализа)
- (Опционально) Docker и Docker Compose

### Шаг 1: Клонирование и настройка окружения

```bash
# Перейти в папку проекта
cd meeting_reporter

# Создать виртуальное окружение
python -m venv venv

# Активировать виртуальное окружение
# На macOS/Linux:
source venv/bin/activate
# На Windows:
# venv\Scripts\activate
```

### Шаг 2: Установка зависимостей

```bash
# Установить зависимости
pip install -e ".[dev]"

# Или если используете requirements.txt:
pip install -r requirements.txt
```

### Шаг 3: Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
# Режим отладки
DEBUG=true

# Секретный ключ для JWT (сгенерируйте случайную строку)
SECRET_KEY=your-super-secret-key-change-this-in-production

# Алгоритм JWT
ALGORITHM=HS256

# Время жизни токенов
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS (разрешенные домены, * = все)
CORS_ORIGINS=["*"]

# База данных (SQLite по умолчанию)
DB_ENGINE=sqlite
DB_NAME=app.db

# Для PostgreSQL (если нужно):
# DB_ENGINE=postgresql
# DB_USER=postgres
# DB_PASSWORD=your_password
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=meeting_reporter

# OpenAI API ключ (ОБЯЗАТЕЛЬНО!)
OPENAI_API_KEY=sk-your-openai-api-key-here
```

**Важно:** Получите OpenAI API ключ на https://platform.openai.com/api-keys

### Шаг 4: Настройка базы данных

```bash
# Применить миграции (создать таблицы в БД)
alembic upgrade head
```

Если нужно создать новую миграцию после изменения моделей:
```bash
alembic revision --autogenerate -m "описание изменений"
alembic upgrade head
```

### Шаг 5: Запуск приложения

**Вариант 1: Локальный запуск**

```bash
# Запустить сервер разработки
uvicorn main:app --reload

# Или через Python
python main.py
```

Приложение будет доступно по адресу: http://localhost:8000

**Вариант 2: Через Docker**

```bash
# Сборка и запуск
docker-compose up --build

# Или для разработки (с hot-reload):
docker-compose -f docker-compose.dev.yml up --build
```

### Шаг 6: Проверка работы

1. **Откройте документацию API:**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

2. **Проверьте health endpoint:**
   ```bash
   curl http://localhost:8000/health
   ```

## 📝 Использование API

### 1. Регистрация и аутентификация

**Регистрация:**
```bash
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpassword123"
  }'
```

**Вход:**
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpassword123"
  }'
```

Ответ содержит `access_token` - используйте его для авторизованных запросов.

### 2. Загрузка аудиофайла

```bash
curl -X POST "http://localhost:8000/meetings/upload" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "title=Team Meeting" \
  -F "language=en" \
  -F "file=@/path/to/your/audio.mp3"
```

**Параметры:**
- `title` (обязательно) - название встречи
- `language` (опционально) - язык (en, fr, ru и т.д.), по умолчанию "en"
- `file` (обязательно) - аудиофайл (mp3, wav, ogg, m4a, mp4)

**Ответ:**
```json
{
  "id": 1,
  "title": "Team Meeting",
  "status": "pending",
  "audio_file_path": "uploads/abc123.mp3",
  "created_at": "2025-01-20T10:00:00",
  "message": "Meeting uploaded successfully. Transcription is in progress..."
}
```

### 3. Проверка статуса обработки

```bash
curl -X GET "http://localhost:8000/meetings/1/status" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Ответ:**
```json
{
  "id": 1,
  "status": "processing",
  "progress_percentage": 50,
  "error_message": null,
  "transcription_ready": false
}
```

Статусы:
- `pending` - ожидает обработки
- `processing` - обрабатывается
- `completed` - завершено
- `failed` - ошибка

### 4. Получение деталей встречи

```bash
curl -X GET "http://localhost:8000/meetings/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Ответ содержит:**
- Информацию о встрече
- Полный транскрипт
- Извлеченные темы
- Принятые решения
- Задачи (action items)

### 5. Генерация отчета

```bash
curl -X POST "http://localhost:8000/meetings/1/report" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "include_transcription": true,
    "include_timestamps": false
  }'
```

**Примечание:** Отчеты генерируются только в формате Markdown. PDF и JSON форматы не поддерживаются.

**Параметры:**
- `include_transcription` - включить полный транскрипт в отчет
- `include_timestamps` - включить временные метки в транскрипт

**Ответ:**
```json
{
  "meeting_id": 1,
  "format": "markdown",
  "file_url": null,
  "content": "# Meeting Report: Team Meeting\n\n...",
  "generated_at": "2025-01-20T10:30:00"
}
```

### 6. Использование Support Agent

**Задать вопрос:**
```bash
curl -X POST "http://localhost:8000/support/query" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What decisions were made about the budget?",
    "meeting_ids": [1, 2]
  }'
```

**Параметры:**
- `question` (обязательно) - ваш вопрос
- `meeting_ids` (опционально) - список ID встреч для поиска (если не указано, ищет во всех)

**Ответ:**
```json
{
  "answer": "Based on your meeting 'Team Meeting' (2025-01-20):\n\nThe budget was increased by 20%...",
  "confidence": 0.85,
  "sources": [
    {
      "meeting_id": 1,
      "meeting_title": "Team Meeting",
      "meeting_date": "2025-01-20T10:00:00",
      "relevance": 0.85
    }
  ],
  "needs_human": false
}
```

**Получить список встреч для поиска:**
```bash
curl -X GET "http://localhost:8000/support/meetings" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 7. Список всех встреч

```bash
curl -X GET "http://localhost:8000/meetings" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 8. Удаление встречи

```bash
curl -X DELETE "http://localhost:8000/meetings/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 🧪 Тестирование

```bash
# Запустить все тесты
pytest

# С покрытием кода
pytest --cov=app

# Конкретный тест
pytest tests/test_auth.py
```

## 🔍 Отладка

### Проблемы с транскрипцией

1. Проверьте, что `OPENAI_API_KEY` установлен в `.env`
2. Проверьте баланс на OpenAI аккаунте
3. Убедитесь, что файл не превышает 25MB
4. Проверьте логи приложения

### Проблемы с базой данных

1. Убедитесь, что миграции применены: `alembic upgrade head`
2. Проверьте путь к БД в `.env`
3. Для SQLite убедитесь, что есть права на запись

### Проблемы с файлами

1. Убедитесь, что папка `uploads/` создана и доступна для записи
2. Проверьте формат аудиофайла (поддерживаются: mp3, wav, ogg, m4a, mp4)

## 📦 Зависимости

Основные библиотеки:
- **FastAPI** - веб-фреймворк
- **SQLAlchemy** - ORM для работы с БД
- **Alembic** - миграции БД
- **OpenAI** - API для транскрипции и анализа
- **Pydantic** - валидация данных
- **python-jose** - JWT токены
- **passlib** - хеширование паролей
- **pydub** - обработка аудиофайлов

## 🎯 Что можно улучшить в будущем

1. **Support Agent:**
   - Использовать semantic search вместо keyword matching
   - Добавить векторную базу данных (например, ChromaDB)
   - Улучшить промпты для более точных ответов

2. **Транскрипция:**
   - Поддержка разделения спикеров
   - Поддержка больше форматов аудио
   - Обработка больших файлов (chunking)

3. **Отчеты:**
   - Генерация PDF отчетов
   - Экспорт в другие форматы (DOCX, HTML)
   - Кастомизация шаблонов отчетов

4. **Производительность:**
   - Кэширование транскриптов
   - Очередь задач (Celery, RQ)
   - Асинхронная обработка больших файлов

## 📄 Лицензия

MIT

## 👤 Автор

Проект создан как тестовое задание.
