# Audio Processor - Detailed Workflow

This document provides a detailed explanation of the audio processing workflow implemented in `app.py`.

## Overview

The application receives a Google Drive file ID for an audio file (and optionally, a PDF attachment file ID) via an API endpoint. It then performs the following steps:

1.  Downloads the audio file (and attachment if provided).
2.  Extracts text from the PDF attachment (if applicable).
3.  Converts the audio file to a standard WAV format.
4.  Transcribes the audio using Whisper.
5.  Performs speaker diarization using Pyannote.
6.  Attempts to identify speaker names using Google Gemini.
7.  Generates a title, summary, and to-do list using Google Gemini, incorporating the transcript, identified speakers, and optional attachment text.
8.  Creates a new page in a Notion database containing the generated summary, to-dos, and the full transcript with identified speaker names.

## Main Workflow (`process_file` function)

The core logic resides in the `process_file` function. Here's a sequence diagram illustrating the flow:

```mermaid
sequenceDiagram
    participant API as API Endpoint (/process)
    participant PF as process_file
    participant AT as download_and_extract_text
    participant DD as download_from_drive
    participant PA as process_audio
    participant IS as identify_speakers
    participant GS as generate_summary
    participant CNP as create_notion_page

    API->>PF: Start processing(audio_file_id, attachment_file_id?)
    alt Attachment Provided
        PF->>AT: download_and_extract_text(attachment_file_id)
        AT-->>PF: attachment_text, temp_dir
    end
    PF->>DD: download_from_drive(audio_file_id)
    DD-->>PF: audio_path, temp_dir
    PF->>PA: process_audio(audio_path)
    PA-->>PF: segments, original_speakers
    PF->>IS: identify_speakers(segments, original_speakers)
    IS-->>PF: speaker_map
    Note over PF: Update segments with identified names,\nCombine transcript for summary
    PF->>GS: generate_summary(transcript_for_summary, attachment_text?)
    GS-->>PF: summary_data (title, summary, todos)
    PF->>CNP: create_notion_page(title, summary, todos, updated_segments)
    CNP-->>PF: page_id, page_url
    PF-->>API: Success response (page_id, url, title, etc.)
    deactivate PF

    alt Error Occurs
        PF-->>API: Error response
    end

    Note right of PF: Temporary directories are cleaned up in 'finally' block.
```

## Function Details

### `download_from_drive(file_id)`

*   **Purpose:** Downloads a file from Google Drive using its ID.
*   **Input:** `file_id` (string) - The Google Drive file ID.
*   **Process:**
    1.  Creates a unique temporary directory using `tempfile.mkdtemp()`.
    2.  Uses the Google Drive API (`self.drive_service`) to get file metadata (name, MIME type).
    3.  Constructs the local download path within the temporary directory.
    4.  Uses `MediaIoBaseDownload` to download the file content in chunks.
*   **Output:** `(local_path, temp_dir)` (tuple) - The full path to the downloaded file and the path to the temporary directory created.
*   **Error Handling:** Raises exceptions on API errors or download failures; cleans up the temporary directory on failure.

### `download_and_extract_text(file_id)`

*   **Purpose:** Downloads a file (currently only PDF) from Google Drive and extracts its text content.
*   **Input:** `file_id` (string) - The Google Drive file ID of the attachment.
*   **Process:**
    1.  Gets file metadata to check the MIME type.
    2.  If not a PDF or `PyPDF2` is not installed, returns `(None, None)`.
    3.  Calls `download_from_drive` to get the file locally.
    4.  Opens the downloaded PDF using `PyPDF2.PdfReader`.
    5.  Iterates through pages, extracting text using `page.extract_text()`.
    6.  Concatenates text from all pages.
*   **Output:** `(text, temp_dir)` (tuple) - The extracted text content (or `None` if failed/not supported) and the path to the temporary directory used for download.
*   **Error Handling:** Catches exceptions during download or PDF parsing; returns `(None, temp_dir)` or `(None, None)`. The temporary directory is *not* cleaned here; cleanup is handled by `process_file`.

### `convert_to_wav(input_path)`

*   **Purpose:** Converts an audio file to WAV format (16kHz, 16-bit PCM, mono) using FFmpeg. This is required for Whisper and Pyannote.
*   **Input:** `input_path` (string) - Path to the input audio file.
*   **Process:**
    1.  Creates a temporary WAV file path in the same directory as the input.
    2.  Constructs an `ffmpeg` command with the specified conversion parameters (`-acodec pcm_s16le`, `-ar 16000`, `-ac 1`).
    3.  Executes the command using `subprocess.run`.
*   **Output:** `output_path` (string) - Path to the converted WAV file.
*   **Error Handling:** Raises `RuntimeError` if `ffmpeg` fails, logging stderr.

### `process_audio(audio_path)`

*   **Purpose:** Orchestrates audio-to-text transcription and speaker diarization.
*   **Input:** `audio_path` (string) - Path to the audio file (preferably WAV).
*   **Process:**
    1.  Calls `load_models()` to ensure Whisper and Pyannote models are loaded.
    2.  If the input is not WAV, calls `convert_to_wav()` and updates `audio_path`.
    3.  **Transcription:** Calls `self.whisper_model.transcribe()` on the audio path.
    4.  **Diarization:** Calls `self.diarization_pipeline()` on the audio path.
    5.  **Integration:**
        *   Iterates through text segments from Whisper.
        *   For each segment, determines the dominant speaker by finding which speaker label from Pyannote's output overlaps the most with the segment's timeframe.
        *   Stores segment data (speaker label, start, end, text).
        *   Collects unique original speaker labels (e.g., `SPEAKER_00`, `SPEAKER_01`).
*   **Output:** `(transcript_full, segments, original_speakers)` (tuple) - `transcript_full` (currently unused string), `segments` (list of dictionaries), `original_speakers` (list of unique speaker labels found).

### `identify_speakers(segments, original_speakers)`

*   **Purpose:** Attempts to map generic speaker labels (e.g., `SPEAKER_00`) to actual names mentioned in the conversation using Google Gemini.
*   **Input:** `segments` (list), `original_speakers` (list).
*   **Process:**
    1.  Checks if identification is possible (skips if no speakers or '未知' is present).
    2.  Constructs a prompt for Gemini, including the conversation transcript (with original speaker labels) and instructions to return a JSON mapping.
    3.  Calls the Gemini API (`genai.GenerativeModel('gemini-1.5-flash-latest').generate_content()`).
    4.  Parses the response, expecting a JSON object like `{"SPEAKER_00": "Alice", "SPEAKER_01": "SPEAKER_01"}`.
    5.  Validates the response format and ensures all original speakers are present in the map (uses original label if missing or invalid).
*   **Output:** `speaker_map` (dict) - A dictionary mapping original labels to identified names (or original labels if identification failed).
*   **Error Handling:** Catches API errors or JSON parsing errors; returns the original labels mapped to themselves on failure.

### `generate_summary(transcript, attachment_text=None)`

*   **Purpose:** Generates a meeting title, summary, and to-do list using Google Gemini, based on the transcript and optional attachment text.
*   **Input:** `transcript` (string - with identified speaker names), `attachment_text` (optional string).
*   **Process:**
    1.  Checks if the transcript is valid.
    2.  Constructs a detailed prompt for Gemini, including the transcript, optional attachment text, and strict instructions to return *only* a JSON object with `title`, `summary`, and `todos` keys.
    3.  **Retry Loop (up to 3 attempts):**
        *   Calls the Gemini API (`genai.GenerativeModel('gemini-1.5-flash-latest').generate_content()`).
        *   Logs the raw API response.
        *   Attempts to parse the response as JSON (handling potential markdown wrappers ` ```json ... ``` `).
        *   Validates the presence and types of required keys (`title`, `summary`, `todos`).
        *   If successful, returns the parsed data.
        *   If an error occurs (API error, JSON parsing, validation), logs the error and retries after a short delay.
*   **Output:** `summary_data` (dict) - A dictionary containing `title`, `summary`, and `todos`. If all attempts fail, returns a fallback dictionary indicating failure.
*   **Error Handling:** Includes retries, robust JSON parsing, validation, and returns a fallback dictionary on persistent failure.

### `create_notion_page(title, summary, todos, segments)`

*   **Purpose:** Creates a new page in a pre-configured Notion database.
*   **Input:** `title` (string), `summary` (string), `todos` (list of strings), `segments` (list of dictionaries with *identified* speaker names).
*   **Process:**
    1.  Retrieves Notion API token and Database ID from environment variables.
    2.  Constructs the Notion page content as a list of blocks (headings, paragraphs, to-do items) using the Notion API block structure.
        *   Summary and To-Do sections are created.
        *   A "完整記錄" section is added.
        *   Each segment from the input `segments` is added as a paragraph block formatted as `[Speaker Name]: Text`. Timestamps are omitted.
    3.  Constructs the API request payload, including the parent database ID, page title (with current date), and the children blocks.
    4.  Sends a POST request to the Notion API (`https://api.notion.com/v1/pages`).
*   **Output:** `(page_id, page_url)` (tuple) - The ID and URL of the newly created Notion page.
*   **Error Handling:** Raises exceptions on Notion API errors, logging response details.
