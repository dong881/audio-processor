# API Reference

This section provides detailed documentation for the Audio Processor API endpoints.

## Contents

- [Process Audio File](#process-audio-file)
- [Check Job Status](#check-job-status) 
- [List Active Jobs](#list-active-jobs)
- [Health Check](#health-check)

## Process Audio File

Initiates asynchronous processing of an audio file stored in Google Drive.

**Endpoint:** `POST /process`

**Headers:**
- `Content-Type: application/json`

**Request Body:**
```json
{
  "file_id": "YOUR_GOOGLE_DRIVE_AUDIO_FILE_ID",
  "attachment_file_id": "OPTIONAL_GOOGLE_DRIVE_PDF_FILE_ID"
}
```

**Parameters:**
- `file_id` (required): Google Drive file ID of the audio file to process
- `attachment_file_id` (optional): Google Drive file ID of a PDF document to provide additional context for summarization

**Response:**
```json
{
  "success": true,
  "message": "Job submitted, processing in background",
  "job_id": "12345678-1234-5678-1234-567812345678"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error message describing what went wrong"
}
```

## Check Job Status

Retrieves the current status of a processing job.

**Endpoint:** `GET /job/{job_id}`

**Parameters:**
- `job_id` (path parameter): The unique identifier of the job to check

**Response (Job in Progress):**
```json
{
  "success": true,
  "job": {
    "id": "12345678-1234-5678-1234-567812345678",
    "status": "processing",
    "progress": 65,
    "created_at": "2023-06-10T12:34:56.789012",
    "updated_at": "2023-06-10T12:35:23.456789"
  }
}
```

**Response (Job Completed):**
```json
{
  "success": true,
  "job": {
    "id": "12345678-1234-5678-1234-567812345678",
    "status": "completed",
    "progress": 100,
    "created_at": "2023-06-10T12:34:56.789012",
    "updated_at": "2023-06-10T12:38:45.123456",
    "result": {
      "success": true,
      "notion_page_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "notion_page_url": "https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "title": "Generated Meeting Title",
      "summary": "Generated meeting summary...",
      "todos": ["Generated Todo 1", "Generated Todo 2"],
      "identified_speakers": {"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"},
      "drive_filename": "[2023-06-10] Generated Meeting Title"
    }
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Job not found"
}
```

## List Active Jobs

Retrieves a list of jobs based on their status.

**Endpoint:** `GET /jobs`

**Query Parameters:**
- `filter` (optional): Filter jobs by status
  - `active` (default): Returns only pending or processing jobs
  - `all`: Returns all jobs regardless of status
  - `completed`: Returns only completed jobs
  - `failed`: Returns only failed jobs

**Example Requests:**
```bash
curl -X GET "https://api.example.com/jobs?filter=completed"
```

**Response:**
```json
{
  "success": true,
  "jobs": {
    "12345678-1234-5678-1234-567812345678": {
      "id": "12345678-1234-5678-1234-567812345678",
      "status": "processing",
      "progress": 65,
      "created_at": "2023-06-10T12:34:56.789012",
      "updated_at": "2023-06-10T12:35:23.456789"
    },
    "87654321-4321-5678-4321-876543210987": {
      "id": "87654321-4321-5678-4321-876543210987",
      "status": "pending",
      "progress": 0,
      "created_at": "2023-06-10T12:38:00.123456",
      "updated_at": "2023-06-10T12:38:00.123456"
    }
  }
}
```

## Health Check

Provides basic service health information and the number of active jobs.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2023-06-10T12:38:00.123456",
  "active_jobs": 2
}
```

**Note:** The API is designed to handle concurrent processing of multiple jobs. However, the processing time for individual jobs may vary based on the size and complexity of the audio file, as well as the current system load.