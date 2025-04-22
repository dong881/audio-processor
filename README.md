# Audio Processing API

This Flask application processes audio files from Google Drive, performs speech-to-text transcription and speaker diarization, attempts to identify speakers, generates a summary and to-do list using Google Gemini, optionally incorporates text from a PDF attachment, and creates a summary page in Notion.

## Features

*   Downloads audio files from Google Drive.
*   Converts various audio formats to WAV (16kHz, mono).
*   Performs speech-to-text using Whisper.
*   Performs speaker diarization using Pyannote Audio.
*   Attempts to identify speaker names (e.g., `SPEAKER_00`) based on conversation context using Google Gemini (`gemini-1.5-flash-latest`).
*   Generates a meeting title, summary, and to-do list using Google Gemini (`gemini-1.5-flash-latest`).
*   Optionally extracts text from a PDF attachment (via Google Drive) to provide more context to Gemini for summarization.
*   Creates a structured page in a specified Notion database with the title, summary, to-dos, and full transcript (without timestamps, using identified speaker names).

## Detailed Workflow

For a detailed step-by-step explanation of the application's internal workflow and function interactions, please see the [**Process Details Document**](./PROCESS_DETAILS.md).

## Prerequisites

*   Python 3.8+ (Python 3.10 used in Dockerfile)
*   Docker & Docker Compose (Version 1.x might require multi-step updates, see below)
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
    Copy `.env.example` to `.env` (if it exists, otherwise create it) and fill in your credentials and IDs:
    ```env
    # Google Drive API
    # Option 1: OAuth (set USE_SERVICE_ACCOUNT=false)
    # GOOGLE_CREDS_JSON_PATH=./credentials.json # Path inside container is /app/credentials/credentials.json
    # Option 2: Service Account (set USE_SERVICE_ACCOUNT=true)
    GOOGLE_SA_JSON_PATH=/app/credentials/service_account.json # Use path inside container
    USE_SERVICE_ACCOUNT=true # Set to true or false

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
    *   Create a `credentials` directory in your project root: `mkdir credentials`
    *   Place your Google credentials file (`credentials.json` or `service_account.json`) inside this `credentials` directory. **Ensure the filename matches the one specified in `.env` (e.g., `service_account.json`).**
4.  **Build and Run with Docker Compose:**
    ```bash
    # Build the image initially
    docker-compose build audio-processor
    # Start the service in detached mode
    docker-compose up -d
    ```
    *(This assumes your service in `docker-compose.yml` is named `audio-processor`)*

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

If you modify the Python code (`app.py` or other dependencies), you need to rebuild the image and restart the container.

**Note:** Due to potential incompatibilities with older `docker-compose` versions (like 1.x), using `docker-compose up -d --build` might result in errors (`KeyError: 'ContainerConfig'`). The safer approach is to explicitly stop, remove, build, and then start the service:

1.  **Stop the currently running service:**
    ```bash
    docker-compose stop audio-processor
    ```
2.  **Remove the stopped container:**
    ```bash
    docker-compose rm -f audio-processor
    ```
3.  **Build the new image:**
    ```bash
    docker-compose build audio-processor
    ```
4.  **Start the service with the new image:**
    ```bash
    docker-compose up -d
    ```

This ensures the old container is fully removed before the new one is created from the updated image.

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

## Cleaning Up Unused Docker Images

Each time you rebuild the image after making changes (`docker-compose build audio-processor`), Docker keeps the old, unused image layers. Over time, these can consume significant disk space.

To remove all dangling (unused and untagged) images, you can use the `docker image prune` command.

```bash
# Remove all dangling images
docker image prune

# To remove dangling images without prompting for confirmation
docker image prune -f
```

**Caution:** This command removes images that are not associated with any container. Ensure you don't have other projects relying on these dangling images before running it. It's generally safe to run if you only use Docker for this project or manage your images carefully.
