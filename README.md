# Audio Processing API

This Flask application processes audio files from Google Drive, performs speech-to-text transcription and speaker diarization, attempts to identify speakers, generates a summary and to-do list using Google Gemini, optionally incorporates text from a PDF attachment, and creates a summary page in Notion.

## Features

*   Downloads audio files from Google Drive.
*   Converts various audio formats to WAV (16kHz, mono).
*   Performs speech-to-text using Whisper.
*   Performs speaker diarization using Pyannote Audio.
*   Attempts to identify speaker names (e.g., `SPEAKER_00`) based on conversation context using Google Gemini.
*   Generates a meeting title, summary, and to-do list using Google Gemini.
*   Optionally extracts text from a PDF attachment (via Google Drive) to provide more context to Gemini for summarization.
*   Creates a structured page in a specified Notion database with the title, summary, to-dos, and full transcript (without timestamps, using identified speaker names).

## Prerequisites

*   Python 3.8+
*   Docker & Docker Compose
*   Google Cloud Project with Drive API enabled
    *   OAuth 2.0 Credentials (`credentials.json`) OR Service Account Key (`service_account.json`)
*   Google Gemini API Key
*   Hugging Face Hub Token (for Pyannote)
*   Notion Integration Token and Database ID

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd audio-processor
    ```
2.  **Create `.env` file:**
    Copy `.env.example` to `.env` and fill in your credentials and IDs:
    ```env
    # Google Drive API
    # Option 1: OAuth (set USE_SERVICE_ACCOUNT=false)
    GOOGLE_CREDS_JSON_PATH=./credentials.json
    # Option 2: Service Account (set USE_SERVICE_ACCOUNT=true)
    GOOGLE_SA_JSON_PATH=./service_account.json
    USE_SERVICE_ACCOUNT=false # or true

    # Google Gemini API
    GEMINI_API_KEY=YOUR_GEMINI_API_KEY

    # Hugging Face Hub (for Pyannote)
    HF_TOKEN=YOUR_HUGGINGFACE_TOKEN

    # Notion API
    NOTION_TOKEN=YOUR_NOTION_INTEGRATION_TOKEN
    NOTION_DATABASE_ID=YOUR_NOTION_DATABASE_ID

    # Flask Settings (Optional)
    PORT=5000
    FLASK_DEBUG=false
    ```
3.  **Place Credentials:**
    *   If using OAuth, place your `credentials.json` file in the project root.
    *   If using a Service Account, place your key file (e.g., `service_account.json`) in the project root and update `GOOGLE_SA_JSON_PATH` in `.env`.
4.  **Build and Run with Docker Compose:**
    ```bash
    docker compose build
    docker compose up -d
    ```
    *(This assumes your service in `docker-compose.yml` is named `app` or similar and includes installing dependencies like `PyPDF2`)*

## API Usage

Send a POST request to the `/process` endpoint.

**Endpoint:** `POST /process`

**Headers:**
*   `Content-Type: application/json`

**Body (JSON):**
```json
{
  "file_id": "YOUR_GOOGLE_DRIVE_AUDIO_FILE_ID",
  "attachment_file_id": "OPTIONAL_GOOGLE_DRIVE_PDF_FILE_ID"
}
```
*   `file_id`: (Required) The ID of the audio file in Google Drive.
*   `attachment_file_id`: (Optional) The ID of a PDF file in Google Drive to include as context for summarization.

**Example Request (using curl):**
```bash
curl -X POST http://localhost:5000/process \
-H "Content-Type: application/json" \
-d '{
      "file_id": "YOUR_AUDIO_FILE_ID",
      "attachment_file_id": "YOUR_PDF_FILE_ID"
    }'
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "notion_page_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "notion_page_url": "https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "title": "Generated Meeting Title",
  "summary": "Generated meeting summary...",
  "todos": [
    "Generated Todo 1",
    "Generated Todo 2"
  ],
  "identified_speakers": {
      "SPEAKER_00": "Alice",
      "SPEAKER_01": "Bob"
  }
}
```

**Error Response (4xx or 5xx):**
```json
{
  "success": false,
  "error": "Error message describing the issue"
}
```

## Updating the Application

If you modify the Python code (`app.py` or other dependencies):

1.  **Rebuild the Docker image:**
    ```bash
    docker compose build <service_name>
    ```
    (Replace `<service_name>` with the name of the service defined in your `docker-compose.yml`, e.g., `app`)

2.  **Restart the container:**
    ```bash
    docker compose up -d
    ```
    Docker Compose will detect the updated image and recreate the container.

## Health Check

A simple health check endpoint is available:

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff"
}
```
