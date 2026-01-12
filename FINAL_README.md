# Meeting Reporter

A FastAPI application for generating meeting reports from audio files, similar to Noota. The tool can receive audio files via API and generate transcriptions, structured summaries, decisions, and action items. Includes a RAG-based assistant that answers questions based on meeting transcriptions.

## 🚀 Features

- **Audio Transcription**: Convert audio/video files to text using OpenAI Whisper
- **Meeting Analysis**: Extract topics, decisions, and action items using GPT
- **Report Generation**: Generate structured Markdown reports
- **RAG Assistant**: Semantic search-based assistant that answers questions about your meetings
- **JWT Authentication**: Secure user authentication with refresh tokens
- **Async Database**: SQLAlchemy with async operations
- **Docker Support**: Ready-to-use Docker configurations
- **Streamlit UI**: User-friendly web interface (optional)

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Running the Application](#-running-the-application)
- [API Usage](#-api-usage)
- [Streamlit Interface](#-streamlit-interface)
- [Project Structure](#-project-structure)
- [Architecture](#-architecture)
- [Testing](#-testing)
- [Production Deployment](#-production-deployment)

## 🏃 Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (optional, but recommended)
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))
- ffmpeg (for local installation, for audio file processing)

### Option 1: Docker (Recommended) 🐳

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd meeting_reporter
   ```

2. **Create `.env` file:**
   ```env
   SECRET_KEY=your-secret-key-minimum-32-characters-long
   OPENAI_API_KEY=sk-your-openai-api-key
   DB_ENGINE=sqlite
   DB_NAME=app.db
   DEBUG=true
   ```

   Generate a secure SECRET_KEY:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. **Start with Docker:**
   ```bash
   # Development mode (with auto-reload)
   docker compose -f docker-compose.dev.yml up --build
   
   # Or use helper script
   ./docker-run.sh dev
   ```

4. **Access the application:**
   - API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Streamlit UI: See [Streamlit Interface](#-streamlit-interface) section below

### Option 2: Local Installation

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd meeting_reporter
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install ffmpeg:**
   ```bash
   # macOS
   brew install ffmpeg
   
   # Ubuntu/Debian
   sudo apt-get install ffmpeg
   
   # Windows
   # Download from https://ffmpeg.org/download.html
   ```

4. **Create `.env` file:**
   ```env
   DEBUG=true
   SECRET_KEY=your-secret-key-here
   DB_ENGINE=sqlite
   DB_NAME=app.db
   OPENAI_API_KEY=sk-your-openai-api-key
   ```

5. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Start the server:**
   ```bash
   uvicorn main:app --reload
   ```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECRET_KEY` | JWT secret key (min 32 chars) | - | Yes |
| `OPENAI_API_KEY` | OpenAI API key | - | Yes |
| `DB_ENGINE` | Database engine (`sqlite` or `postgresql`) | `sqlite` | No |
| `DB_NAME` | Database name | `app.db` | No |
| `DEBUG` | Debug mode | `true` | No |

### Database Configuration

**SQLite (default):**
```env
DB_ENGINE=sqlite
DB_NAME=app.db
```

**PostgreSQL:**
```env
DB_ENGINE=postgresql
DB_USER=postgres
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=meeting_reporter
```

## 🚀 Running the Application

### Docker

**Development mode (with auto-reload):**
```bash
docker compose -f docker-compose.dev.yml up --build
```

**Production mode:**
```bash
docker compose up --build
```

**Using helper script:**
```bash
./docker-run.sh dev    # Development
./docker-run.sh        # Production
```

### Local

```bash
# Development (with auto-reload)
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Application URLs

- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📡 API Usage

### Authentication

**1. Register a new user:**
```bash
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass123"}'
```

**2. Login (save the access_token):**
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass123"}'
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### Meetings

**3. Upload audio/video file:**
```bash
curl -X POST "http://localhost:8000/meetings/upload" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "title=Team Meeting" \
  -F "file=@meeting.mp3"
```

**Supported formats:**
- Audio: mp3, wav, ogg, m4a, webm
- Video: mp4, mov, avi, webm, mkv, 3gp (Whisper extracts audio automatically)

**4. Check processing status:**
```bash
curl -X GET "http://localhost:8000/meetings/1/status" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**5. List all meetings:**
```bash
curl -X GET "http://localhost:8000/meetings" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**6. Get meeting details:**
```bash
curl -X GET "http://localhost:8000/meetings/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**7. Generate report:**
```bash
curl -X POST "http://localhost:8000/meetings/1/report" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"include_transcription": true, "include_timestamps": false}'
```

**8. Download report:**
```bash
curl -X GET "http://localhost:8000/meetings/1/report/download" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -o report.md
```

**9. Delete meeting:**
```bash
curl -X DELETE "http://localhost:8000/meetings/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### RAG Assistant

**10. Ask a question about your meetings:**
```bash
curl -X POST "http://localhost:8000/support/query" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What decisions were made about the budget?",
    "meeting_ids": [1, 2]
  }'
```

**11. List meetings available for search:**
```bash
curl -X GET "http://localhost:8000/support/meetings" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### API Token Authentication (Alternative)

You can also use API tokens instead of JWT:

**1. Create API token:**
```bash
curl -X POST "http://localhost:8000/auth/api-token" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**2. Use API token:**
```bash
curl -X GET "http://localhost:8000/meetings" \
  -H "X-API-Token: YOUR_API_TOKEN"
```

## 🎨 Streamlit Interface

The project includes an optional Streamlit web interface for easier interaction with the API.

### Running Streamlit

**1. Make sure the API is running:**
```bash
# In one terminal
uvicorn main:app --reload
```

**2. Start Streamlit (in another terminal):**
```bash
# Activate virtual environment if using local installation
source venv/bin/activate

# Install streamlit if not already installed
pip install streamlit

# Run Streamlit
streamlit run streamlit_app.py
```

**3. Access Streamlit UI:**
- Open your browser to: http://localhost:8501

### Using Streamlit Interface

**1. Login:**
   - Enter your username and password
   - Click "Login"
   - Your session will be saved

**2. Upload Meeting:**
   - Go to "Upload" tab
   - Enter meeting title
   - Select audio/video file
   - Click "Upload"
   - Wait for processing to complete

**3. View Meetings:**
   - Go to "My Meetings" tab
   - See list of all your meetings
   - Click on a meeting to view details:
     - Transcription
     - Topics
     - Decisions
     - Action items
   - Generate and download reports

**4. Support Agent:**
   - Go to "Support Agent" tab
   - Enter your question
   - Optionally select specific meetings to search
   - Click "Ask Question"
   - View answer with confidence score and sources

**5. About:**
   - View project information and features

### Streamlit Configuration

If your API is running on a different host/port, edit `streamlit_app.py`:

```python
API_BASE_URL = "http://your-api-host:8000"
```

## 🏗️ Project Structure

```
meeting_reporter/
├── app/
│   ├── api/                  # API endpoints
│   │   ├── auth.py           # Authentication endpoints
│   │   ├── health.py         # Health check
│   │   ├── meetings_api.py   # Meeting management
│   │   └── support_api.py    # RAG assistant
│   ├── core/                 # Core configuration
│   │   ├── config.py         # Settings
│   │   └── security.py       # JWT, password hashing
│   ├── db/                   # Database
│   │   ├── base.py           # Base model
│   │   └── session.py        # Session management
│   ├── models/               # SQLAlchemy models
│   │   ├── meeting_models.py # Meeting, Transcription, etc.
│   │   └── user.py           # User model
│   ├── schemas/              # Pydantic schemas
│   │   ├── meeting_schemas.py
│   │   ├── token.py
│   │   └── user.py
│   ├── services/             # Business logic
│   │   ├── audio/            # Transcription service
│   │   ├── llm/              # GPT analysis service
│   │   ├── analysis/         # Report generation
│   │   └── search/           # Embedding service
│   └── utils/                # Utilities
│       └── file_handler.py   # File management
├── alembic/                  # Database migrations
├── tests/                    # Test files
├── uploads/                  # Uploaded audio files
├── reports/                  # Generated reports
├── main.py                   # FastAPI app entry point
├── streamlit_app.py          # Streamlit UI
├── docker-compose.yml        # Production Docker
├── docker-compose.dev.yml    # Development Docker
├── Dockerfile                # Docker image
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## 🏛️ Architecture

### System Design

```
┌─────────────┐
│   Client    │
│ (Streamlit) │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         FastAPI Application         │
│  ┌───────────────────────────────┐  │
│  │      API Layer (Routers)      │  │
│  │  - Authentication             │  │
│  │  - Meetings                   │  │
│  │  - Support Agent (RAG)        │  │
│  └──────────────┬────────────────┘  │
│                 │                    │
│  ┌──────────────▼────────────────┐  │
│  │    Service Layer              │  │
│  │  - Transcription Service      │  │
│  │  - Analysis Service (GPT)     │  │
│  │  - Report Service             │  │
│  │  - Embedding Service          │  │
│  └──────────────┬────────────────┘  │
│                 │                    │
│  ┌──────────────▼────────────────┐  │
│  │    Data Layer                 │  │
│  │  - SQLAlchemy Models          │  │
│  │  - Database Session           │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│         External Services           │
│  - OpenAI Whisper API               │
│  - OpenAI GPT API                   │
└─────────────────────────────────────┘
```

### Processing Pipeline

1. **Upload**: User uploads audio/video file
2. **Validation**: File type and size validation
3. **Storage**: File saved to disk
4. **Background Task**: Transcription and analysis started
5. **Transcription**: Audio converted to text via Whisper API
6. **Analysis**: GPT extracts topics, decisions, action items
7. **Embedding Cache**: Chunks and embeddings cached for fast search
8. **Completion**: Meeting status updated to COMPLETED

### RAG Assistant Architecture

1. **Query**: User asks a question
2. **Embedding**: Question converted to embedding vector
3. **Semantic Search**: Find relevant chunks using cosine similarity
4. **Context Retrieval**: Top-k chunks retrieved
5. **LLM Generation**: GPT generates answer based on context
6. **Response**: Answer with confidence score and sources

## 🧪 Testing

### Run Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py
```

### Test Coverage

Current test coverage includes:
- Authentication endpoints
- Health check
- Basic API functionality

## 🚢 Production Deployment

### Environment Setup

**1. Set production environment variables:**
```env
DEBUG=false
SECRET_KEY=<strong-random-secret-key>
OPENAI_API_KEY=sk-your-api-key
DB_ENGINE=postgresql
DB_USER=postgres
DB_PASSWORD=<secure-password>
DB_HOST=localhost
DB_PORT=5432
DB_NAME=meeting_reporter
```

**2. Use PostgreSQL for production:**
```bash
# Install PostgreSQL adapter
pip install asyncpg

# Update .env with PostgreSQL credentials
# Run migrations
alembic upgrade head
```

### Docker Production

```bash
docker compose up --build -d
```

### Security Considerations

- Use strong SECRET_KEY (32+ characters)
- Keep OPENAI_API_KEY secure
- Use HTTPS in production
- Set DEBUG=false
- Use PostgreSQL for production database
- Implement rate limiting (recommended)
- Set up proper logging and monitoring

## 📚 Additional Documentation

- [Docker Guide](DOCKER_GUIDE.md) - Detailed Docker instructions
- [Testing Guide](TESTING_GUIDE.md) - Testing instructions
- [Pipeline Guide](PIPELINE_GUIDE.md) - Processing pipeline details
- [Embedding Cache Guide](EMBEDDING_CACHE_GUIDE.md) - RAG optimization
- [Tutorial](TUTORIAL/) - Detailed component documentation

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- OpenAI for Whisper and GPT APIs
- FastAPI for the excellent web framework
- Sentence-transformers for semantic search

## 📧 Support

For issues and questions, please open an issue on GitHub.

---

**Version**: 0.1.0

**Last Updated**: 2024
