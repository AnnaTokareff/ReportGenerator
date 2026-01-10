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

### Prerequisites

- Python 3.11+
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Installation

1. **Clone and setup environment:**
   ```bash
   cd meeting_reporter
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
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

### 2. Upload Audio File
```bash
curl -X POST "http://localhost:8000/meetings/upload" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "title=Team Meeting" \
  -F "language=en" \
  -F "file=@meeting.mp3"
```

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
| `SECRET_KEY` | JWT secret key | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `DB_ENGINE` | Database engine | `sqlite` |
| `DB_NAME` | Database name | `app.db` |

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

## Documentation

For detailed documentation in Russian, see [README_RU.md](README_RU.md)

## Requirements

- Python 3.11+
- OpenAI API key
- (Optional) Docker and Docker Compose

## License

MIT
