# Audio Meeting Minutes to GitHub

A simplified backend service that processes audio recordings from Google Drive, transcribes them using AI, generates meeting minutes, and automatically commits them to a GitHub repository.

## Core Workflow

```
API Request → Download Audio from Google Drive → Transcribe → Generate Meeting Minutes → Commit to GitHub
```

## Features

- **Audio Transcription**: Uses OpenAI Whisper for accurate speech-to-text
- **Speaker Diarization**: Identifies different speakers using Pyannote
- **AI-Powered Summarization**: Generates structured meeting minutes using Google Gemini
- **GitHub Integration**: Automatically commits meeting minutes to specified repository
- **Asynchronous Processing**: Non-blocking job queue for handling multiple requests
- **Simple Backend API**: Clean REST API with minimal dependencies

## Prerequisites

- Python 3.9+
- Docker & Docker Compose
- Google Cloud Project with Drive API enabled
  - Service Account JSON file
- Google Gemini API Key
- Hugging Face Token (for Pyannote)
- GitHub Personal Access Token

## Setup

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd audio-processor
```

### 2. Configure Environment

Create `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
# Google Drive API
GOOGLE_SA_JSON_PATH=/app/credentials/service-account.json

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Hugging Face
HF_TOKEN=your_hf_token

# GitHub Configuration
GITHUB_TOKEN=your_github_token
GITHUB_REPO=username/repository-name
GITHUB_PATH=notes/Meeting-Minutes
GITHUB_BRANCH=main
GITHUB_FILENAME_TEMPLATE=MM-YYYYMMDD.md
```

### 3. Add Credentials

Place your Google service account JSON file in the `credentials` directory:

```bash
mkdir credentials
# Copy your service-account.json to credentials/
```

### 4. Build and Run

```bash
# Build the Docker image
docker-compose build

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f
```

The service will be available at `http://localhost:5000`

## API Usage

### Submit Processing Job

**Endpoint:** `POST /process`

**Request:**
```bash
curl -X POST http://localhost:5000/process \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "YOUR_GOOGLE_DRIVE_FILE_ID"
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Job submitted for processing",
  "job_id": "abc123-def456-...",
  "job_status": "pending"
}
```

### Check Job Status

**Endpoint:** `GET /job/<job_id>`

**Request:**
```bash
curl http://localhost:5000/job/abc123-def456-...
```

**Response (Processing):**
```json
{
  "success": true,
  "job": {
    "id": "abc123-def456-...",
    "status": "processing",
    "progress": 45,
    "message": "🎤 Transcribing audio...",
    "created_at": "2025-10-22T10:30:00",
    "updated_at": "2025-10-22T10:32:15"
  }
}
```

**Response (Completed):**
```json
{
  "success": true,
  "job": {
    "id": "abc123-def456-...",
    "status": "completed",
    "progress": 100,
    "message": "✅ Processing complete!",
    "result": {
      "success": true,
      "github_url": "https://github.com/user/repo/blob/main/notes/MM-20251022.md",
      "filename": "MM-20251022.md",
      "path": "notes/Meeting-Minutes/MM-20251022.md",
      "segments_count": 45,
      "speakers": ["SPEAKER_00", "SPEAKER_01"]
    }
  }
}
```

### List Jobs

**Endpoint:** `GET /jobs?filter=<filter_type>`

Filter options: `active` (default), `all`, `completed`, `failed`

**Request:**
```bash
curl http://localhost:5000/jobs?filter=all
```

### Cancel Job

**Endpoint:** `POST /job/<job_id>/cancel`

**Request:**
```bash
curl -X POST http://localhost:5000/job/abc123-def456-.../cancel
```

### Health Check

**Endpoint:** `GET /health`

**Request:**
```bash
curl http://localhost:5000/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-22T10:30:00",
  "active_jobs": 2
}
```

## GitHub Configuration

The service automatically commits meeting minutes to your GitHub repository with the following structure:

```
your-repo/
  notes/
    Meeting-Minutes/
      MM-20251022.md
      MM-20251023.md
      ...
```

### Filename Template

Configure the filename template in `.env`:

- `MM-YYYYMMDD.md` - Will create files like `MM-20251022.md`
- `Meeting-YYYYMMDD.md` - Will create files like `Meeting-20251022.md`
- Any custom format (YYYYMMDD will be replaced with current date)

### Required GitHub Permissions

Your GitHub Personal Access Token needs:
- `repo` - Full control of private repositories (or)
- `public_repo` - Access to public repositories

## Progress Logging

The service outputs simple progress logs for easy monitoring:

```
[Job abc123] 🎬 Starting processing
[Job abc123] 5% - 📥 Downloading file...
[Job abc123] 15% - 🎤 Transcribing audio...
[Job abc123] 70% - 📝 Generating meeting notes...
[Job abc123] 85% - 📤 Committing to GitHub...
[Job abc123] 100% - ✅ Processing complete!
```

## Management Commands

### Update Service After Code Changes

```bash
# Stop the service
docker-compose stop

# Rebuild
docker-compose build

# Start again
docker-compose up -d
```

### View Logs

```bash
# Follow logs
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100
```

### Stop Service

```bash
docker-compose down
```

### Clean Up Docker Images

```bash
# Remove unused images
docker image prune

# Remove all stopped containers and unused images
docker system prune -a
```

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /process
       ▼
┌─────────────┐
│  Flask API  │
└──────┬──────┘
       │
       ▼
┌──────────────────────┐
│  AudioProcessor      │
│  (Thread Pool)       │
└──────┬───────────────┘
       │
       ├─► Google Drive API (Download Audio)
       │
       ├─► Whisper (Transcription)
       │
       ├─► Pyannote (Speaker Diarization)
       │
       ├─► Google Gemini (Generate Notes)
       │
       └─► GitHub API (Commit)
```

## Error Handling

The service includes robust error handling:

- Network errors: Automatic retry with exponential backoff
- API quota limits: Tries multiple Gemini models if quota exceeded
- Invalid files: Returns detailed error messages
- Cancellation: Jobs can be cancelled mid-processing

## Dependencies

Core dependencies:
- Flask - Web framework
- Whisper - Speech-to-text
- Pyannote - Speaker diarization
- Google Generative AI - Meeting summary generation
- Google API Client - Google Drive integration
- PyGithub - GitHub API integration

See `requirements.txt` for full list.

## Troubleshooting

### "Drive API not initialized"
- Check that `service-account.json` exists in `credentials/`
- Verify the path in `.env` matches your file location
- Ensure service account has access to the Google Drive files

### "Gemini API quota exceeded"
- The service will automatically try alternative models
- Check your Gemini API quota at Google AI Studio
- Consider upgrading your API plan

### "GitHub commit failed"
- Verify `GITHUB_TOKEN` has correct permissions
- Check that `GITHUB_REPO` format is correct (username/repo)
- Ensure the path exists or create it in your repository first

### Model loading errors
- First run downloads large AI models (can take 10-15 minutes)
- Ensure sufficient disk space (>5GB)
- Check HF_TOKEN is valid

## License

[Your License Here]
