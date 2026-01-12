# Meeting Reporter - Report Generator + Support Agent

A FastAPI application for generating meeting reports from audio files, similar to Noota. The tool can receive audio files via API and generate transcriptions, structured summaries, decisions, and action items. Includes a simple support agent that can answer questions based on meeting transcriptions.

## Features

- **Audio Transcription**: Convert audio files to text using OpenAI Whisper
- **Meeting Analysis**: Extract topics, decisions, and action items using GPT
- **Report Generation**: Generate structured Markdown reports
- **Support Agent**: Simple agent that answers questions based on meeting transcriptions
- **JWT Authentication**: Secure user authentication
- **Async Database**: SQLAlchemy with async operations
- **Docker Support**: Ready-to-use Docker configurations

## Quick Start

### Option 1: Docker (Recommended) 🐳

**Самый простой способ запуска:**

1. **Установите Docker** (если еще не установлен):
   - macOS: `brew install --cask docker`
   - Linux: `curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh`
   - См. подробности: [DOCKER_INSTALL.md](DOCKER_INSTALL.md)

2. **Создайте `.env` файл:**
   ```env
   SECRET_KEY=your-secret-key-minimum-32-characters-long
   OPENAI_API_KEY=sk-your-openai-api-key
   DB_ENGINE=sqlite
   DB_NAME=app.db
   ```

3. **Запустите Docker:**
   
   **Простой способ (скрипт-помощник):**
   ```bash
   ./docker-run.sh dev  # Режим разработки
   # или
   ./docker-run.sh      # Production режим
   ```
   
   **Или вручную:**
   ```bash
   # Новая версия Docker (рекомендуется)
   docker compose -f docker-compose.dev.yml up --build
   
   # Старая версия (если docker compose не работает)
   docker-compose -f docker-compose.dev.yml up --build
   ```

4. **Откройте в браузере:**
   - API: http://localhost:8000
   - Документация: http://localhost:8000/docs

**Подробная инструкция:** См. [DOCKER_GUIDE.md](DOCKER_GUIDE.md) или [QUICK_START_DOCKER.md](QUICK_START_DOCKER.md)

### Option 2: Local Installation

### Prerequisites

- Python 3.11+
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))
- ffmpeg (для работы с аудио файлами)

### Installation

1. **Clone and setup environment:**
   ```bash
   cd meeting_reporter
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   
   **Note:** If you see `ModuleNotFoundError: No module named 'openai'`, install missing packages:
   ```bash
   pip install openai pydub sentence-transformers numpy
   ```

3. **Create `.env` file:**
   ```env
   DEBUG=true
   SECRET_KEY=your-secret-key-here
   DB_ENGINE=sqlite
   DB_NAME=app.db
   OPENAI_API_KEY=sk-your-openai-api-key
   ```

4. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

5. **Start the server:**
   ```bash
   uvicorn main:app --reload
   ```

6. **Access API documentation:**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /auth/signup` - Register new user
- `POST /auth/login` - Login and get access token

### Meetings
- `POST /meetings/upload` - Upload audio file and create meeting
- `GET /meetings` - List all user's meetings
- `GET /meetings/{id}` - Get meeting details
- `GET /meetings/{id}/status` - Check processing status
- `POST /meetings/{id}/report` - Generate Markdown report
- `DELETE /meetings/{id}` - Delete meeting

### Support Agent (with Semantic Search)
- `POST /support/query` - Ask a question using semantic search (CPU-based, no GPU needed)
- `GET /support/meetings` - List meetings available for search

### System
- `GET /health` - Health check

## Usage Example

### 1. Register and Login
```bash
# Register
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass123"}'

# Login (save the access_token)
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass123"}'
```

### 2. Upload Audio or Video File
```bash
# Audio file
curl -X POST "http://localhost:8000/meetings/upload" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "title=Team Meeting" \
  -F "file=@meeting.mp3"

# Video file (Whisper automatically extracts audio)
curl -X POST "http://localhost:8000/meetings/upload" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "title=Video Meeting" \
  -F "file=@meeting.mp4"
```

**Note:** 
- Language is automatically detected by Whisper API. Supports any language that Whisper can detect.
- Video files are supported (mp4, mov, avi, webm, mkv, 3gp). Whisper API automatically extracts audio from video - no conversion needed!

### 3. Check Status
```bash
curl -X GET "http://localhost:8000/meetings/1/status" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 4. Generate Report (Markdown only)
```bash
curl -X POST "http://localhost:8000/meetings/1/report" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"include_transcription": true, "include_timestamps": false}'
```

**Note:** Reports are generated only in Markdown format. PDF and JSON formats are not supported.

### 5. Query Support Agent
```bash
curl -X POST "http://localhost:8000/support/query" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What decisions were made about the budget?"}'
```

## Project Structure

```
meeting_reporter/
├── app/
│   ├── api/              # API endpoints
│   │   ├── auth.py       # Authentication
│   │   ├── meetings_api.py  # Meeting management
│   │   └── support_api.py   # Support agent
│   ├── core/             # Configuration and security
│   ├── db/               # Database session management
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   │   ├── audio/        # Transcription service
│   │   ├── llm/          # Analysis service
│   │   └── analysis/     # Report generation
│   └── utils/            # Utilities
├── alembic/              # Database migrations
├── main.py               # Application entry point
└── .env                  # Environment variables
```

## Configuration

Environment variables (`.env` file):

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Debug mode | `true` |
| `SECRET_KEY` | JWT secret key (any random string, min 32 chars recommended) | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `DB_ENGINE` | Database engine | `sqlite` |
| `DB_NAME` | Database name | `app.db` |

**About SECRET_KEY:**
- Used to sign JWT authentication tokens
- Can be any random string (recommended: 32+ characters)
- Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- **Important:** Keep it secret in production!

**File Size Limit:**
- Maximum file size: **25 MB** (Whisper API limitation)
- For longer files (e.g., 1-hour meeting), compress the file first
- See [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) for compression instructions

For PostgreSQL:
```
DB_ENGINE=postgresql
DB_USER=postgres
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=meeting_reporter
```

## Docker

### Development
```bash
docker-compose -f docker-compose.dev.yml up --build
```

### Production
```bash
docker-compose up --build
```

## Database Migrations

Create new migration:
```bash
alembic revision --autogenerate -m "Description"
```

Apply migrations:
```bash
alembic upgrade head
```

## Testing

```bash
pytest
pytest --cov=app
```

## Quick Pipeline Execution

**Easiest way** - use the automated Python script:

```bash
# Install httpx if needed
pip install httpx

# Run full pipeline
python run_pipeline.py --file meeting.mp3 --title "Team Meeting"
```

The script automatically handles: registration, login, upload, processing wait, results retrieval, and report generation.

See [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) for detailed instructions.

## Web Interface (Streamlit)

**Optional but recommended** - A simple web interface for easy use:

```bash
# Install Streamlit (if not already installed)
pip install streamlit

# Start API server (in one terminal)
uvicorn main:app --reload

# Start Streamlit interface (in another terminal)
streamlit run streamlit_app.py
```

The interface will open at `http://localhost:8501` and provides:
- 📤 **File Upload** - Drag-and-drop interface for audio/video files
- 📋 **My Meetings** - View all your meetings with details
- 🤖 **Support Agent** - Ask questions about your meetings
- 📄 **Report Generation** - Generate and download Markdown reports

**Note:** Streamlit is optional. You can also use:
- API directly (curl, httpx)
- `run_pipeline.py` script
- Swagger UI at `http://localhost:8000/docs`

See [STREAMLIT_GUIDE.md](STREAMLIT_GUIDE.md) for detailed instructions.

## Documentation

- **Detailed Russian documentation**: [README_RU.md](README_RU.md)
- **Testing guide**: [TESTING_GUIDE.md](TESTING_GUIDE.md) - Step-by-step guide to test the project
- **Complete Pipeline guide**: [PIPELINE_GUIDE.md](PIPELINE_GUIDE.md) - Full end-to-end pipeline execution guide
- **Streamlit Interface guide**: [STREAMLIT_GUIDE.md](STREAMLIT_GUIDE.md) - Web interface usage guide
- **Code Tutorial**: [TUTORIAL/README.md](TUTORIAL/README.md) - Detailed explanations of all code files

## Requirements

- Python 3.11+
- OpenAI API key
- (Optional) Docker and Docker Compose

## License

MIT
