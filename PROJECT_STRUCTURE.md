# Simplified Audio to GitHub Project Structure

## Overview
Backend-only API service for processing audio recordings and committing meeting minutes to GitHub.

## File Structure

```
/workspace/
│
├── main.py                          # Application entry point
├── requirements.txt                 # Python dependencies
├── .env.example                     # Configuration template
├── Dockerfile                       # Docker container definition
├── docker-compose.yml               # Docker Compose configuration
├── README.md                        # Project documentation
│
├── app/                             # Application package
│   ├── __init__.py                  # Flask app factory
│   │
│   ├── routes/                      # API endpoints
│   │   ├── __init__.py
│   │   └── api_routes.py            # REST API routes
│   │
│   ├── services/                    # Business logic
│   │   ├── __init__.py
│   │   └── audio_processor.py       # Core processing logic
│   │
│   └── utils/                       # Utilities
│       ├── __init__.py
│       └── constants.py             # Job status constants
│
├── credentials/                     # Credentials directory
│   └── service-account.json         # Google service account (not in git)
│
└── cursor_responses/                # Documentation
    └── cursor_response.md           # Change summary
```

## Core Files

### `main.py`
- Application entry point
- Initializes AudioProcessor
- Creates Flask app
- Runs server

### `app/__init__.py`
- Flask app factory
- Registers API blueprint
- Minimal configuration

### `app/routes/api_routes.py`
- `GET /health` - Health check
- `POST /process` - Submit processing job
- `GET /job/<id>` - Get job status
- `GET /jobs` - List jobs
- `POST /job/<id>/cancel` - Cancel job

### `app/services/audio_processor.py`
Main processing logic:
- `download_from_drive()` - Download audio from Google Drive
- `convert_to_wav()` - Convert audio format
- `process_audio()` - Transcribe and diarize
- `generate_meeting_notes()` - AI-powered note generation
- `commit_to_github()` - Commit to GitHub repo
- Job queue management

### `app/utils/constants.py`
- Job status constants
- Shared configuration

## Configuration Files

### `.env`
Required environment variables:
```env
GOOGLE_SA_JSON_PATH=/app/credentials/service-account.json
GEMINI_API_KEY=your_key
HF_TOKEN=your_token
GITHUB_TOKEN=your_token
GITHUB_REPO=username/repo
GITHUB_PATH=notes/Meeting-Minutes
```

### `Dockerfile`
- Python 3.9 slim base
- FFmpeg for audio processing
- AI model caching
- Gunicorn WSGI server

### `docker-compose.yml`
- Single service configuration
- Volume mounts for credentials and cache
- Environment variable injection

## Dependencies

### Core
- `flask` - Web framework
- `gunicorn` - WSGI server
- `requests` - HTTP client

### Google Services
- `google-api-python-client` - Drive API
- `google-auth` - Authentication
- `google-generativeai` - Gemini AI

### Audio Processing
- `whisper` - Speech-to-text
- `pyannote.audio` - Speaker diarization
- `librosa` - Audio preprocessing
- `soundfile` - Audio I/O

### Optional
- `PyPDF2` - PDF processing

## Removed Components

### Deleted Files
- `/templates/*` - All HTML templates
- `/static/*` - All CSS/JS files
- `app/routes/auth_routes.py` - OAuth routes
- `app/routes/drive_routes.py` - Drive UI routes
- `app/routes/main_routes.py` - Homepage routes
- `app/utils/notion_formatter.py` - Notion formatting
- `app/services/credential_manager.py` - OAuth credential management

### Removed Dependencies
- Redis (job queue now in-memory)
- google-auth-oauthlib (no OAuth)
- Notion SDK (no Notion integration)

## Data Flow

```
1. Client sends POST /process with file_id
   ↓
2. AudioProcessor creates job and downloads file from Drive
   ↓
3. Convert audio to WAV format
   ↓
4. Whisper transcribes audio
   ↓
5. Pyannote identifies speakers
   ↓
6. Gemini generates meeting notes
   ↓
7. Commit notes to GitHub
   ↓
8. Return GitHub URL to client
```

## Logging

Simple progress-focused logging:
```
[Job abc123] 🎬 Starting processing
[Job abc123] 5% - 📥 Downloading file...
[Job abc123] 15% - 🎤 Transcribing audio...
[Job abc123] 70% - 📝 Generating meeting notes...
[Job abc123] 85% - 📤 Committing to GitHub...
[Job abc123] 100% - ✅ Processing complete!
```

## GitHub Output

Meeting minutes committed as Markdown files:
```markdown
# Meeting Title

## Date
October 22, 2025

## Participants
- Speaker 1
- Speaker 2

## Summary
Brief meeting summary...

## Key Discussion Points
- Point 1
- Point 2

## Action Items
- [ ] Action 1
- [ ] Action 2

## Decisions Made
- Decision 1
- Decision 2
```

## Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
```

### Docker Development
```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Rebuild after changes
docker-compose build
docker-compose up -d
```

### Testing API
```bash
# Health check
curl http://localhost:5000/health

# Submit job
curl -X POST http://localhost:5000/process \
  -H "Content-Type: application/json" \
  -d '{"file_id": "YOUR_FILE_ID"}'

# Check status
curl http://localhost:5000/job/JOB_ID
```

## Security Notes

1. **Service Account**: Use service account with minimal Drive permissions
2. **GitHub Token**: Use fine-grained token with repo-only access
3. **Environment Variables**: Never commit `.env` to git
4. **Credentials**: Keep `credentials/` in `.gitignore`

## Performance

- **Concurrent Jobs**: 3 workers by default (configurable)
- **Job Queue**: In-memory, survives container restart
- **Model Caching**: AI models cached to volume
- **Timeout**: 600 seconds per request (for long audio files)

## Limitations

1. Service account must have access to Drive files
2. Audio files must be accessible via Drive API
3. GitHub repo must exist before first commit
4. Maximum audio length depends on available memory
5. First run downloads large AI models (~2-3GB)

---

Last Updated: 2025-10-22
