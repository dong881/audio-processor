# External Integration Functions

This document details the functions responsible for integrating with external services in the Audio Processor.

## Contents

- [download_from_drive](#download_from_drive)
- [download_and_extract_text](#download_and_extract_text)
- [rename_drive_file](#rename_drive_file)
- [create_notion_page](#create_notion_page)
- [_split_transcript_into_blocks](#_split_transcript_into_blocks)

## download_from_drive

Downloads a file from Google Drive to a temporary directory.

### Signature

```python
def download_from_drive(self, file_id: str) -> Tuple[str, str]:
```

### Parameters

- `file_id` (str): Google Drive file ID to download

### Returns

- `local_path` (str): Path to the downloaded file
- `temp_dir` (str): Path to the temporary directory containing the file

### Description

This function performs the following steps:
1. Creates a temporary directory to store the downloaded file
2. Retrieves file metadata from Google Drive, including file name
3. Downloads the file using Google Drive API
4. Returns both the path to the downloaded file and the temporary directory

The temporary directory should be cleaned up by the caller after use.

### Example

```python
# Download a file from Google Drive
local_file_path, temp_directory = processor.download_from_drive("1abc2defghijk3lmno4pqrs5tuv")

# Use the file
with open(local_file_path, 'r') as file:
    content = file.read()

# Clean up when done
import shutil
shutil.rmtree(temp_directory)
```

## download_and_extract_text

Downloads a PDF file from Google Drive and extracts its text content.

### Signature

```python
def download_and_extract_text(self, file_id: str) -> Tuple[Optional[str], Optional[str]]:
```

### Parameters

- `file_id` (str): Google Drive file ID of the PDF to download

### Returns

- `text` (Optional[str]): Extracted text from PDF or None if extraction failed
- `temp_dir` (Optional[str]): Path to the temporary directory or None if failed

### Description

This function:
1. Verifies the file is a PDF using Google Drive API
2. Downloads the PDF file to a temporary directory
3. Extracts text content from all pages of the PDF using PyPDF2
4. Returns the extracted text and the path to the temporary directory

The function will return (None, None) if:
- The file is not a PDF
- PyPDF2 is not installed
- An error occurs during download or text extraction

### Example

```python
# Extract text from a PDF stored in Google Drive
pdf_text, temp_directory = processor.download_and_extract_text("1abc2defghijk3lmno4pqrs5tuv")

if pdf_text:
    print(f"Extracted {len(pdf_text)} characters of text from PDF")
else:
    print("Failed to extract text from PDF")

# Clean up when done
if temp_directory:
    import shutil
    shutil.rmtree(temp_directory)
```

## rename_drive_file

Renames a file in Google Drive using the Drive API.

### Signature

```python
def rename_drive_file(self, file_id: str, new_name: str) -> bool:
```

### Parameters

- `file_id` (str): Google Drive file ID to rename
- `new_name` (str): New filename to apply

### Returns

- `success` (bool): True if renaming succeeded, False if it failed

### Description

This function:
1. Calls the Google Drive API's files().update method with the new name
2. Logs success or failure of the operation
3. Returns a boolean indicating success or failure

### Example

```python
# Rename a file in Google Drive
success = processor.rename_drive_file("1abc2defghijk3lmno4pqrs5tuv", "[2023-04-30] Meeting Minutes")

if success:
    print("File renamed successfully")
else:
    print("Failed to rename file")
```

## create_notion_page

Creates a new page in a Notion database with meeting information.

### Signature

```python
def create_notion_page(self, title: str, summary: str, todos: List[str], segments: List[Dict[str, Any]], speaker_map: Dict[str, str], file_id: str = None) -> Tuple[str, str]:
```

### Parameters

- `title` (str): Title for the meeting
- `summary` (str): Summary text of the meeting
- `todos` (List[str]): List of action items from the meeting
- `segments` (List[Dict]): List of transcript segments with speaker information
- `speaker_map` (Dict[str, str]): Mapping of speaker IDs to names
- `file_id` (str, optional): Google Drive file ID for linking to the audio file

### Returns

- `page_id` (str): Notion page ID of the created page
- `page_url` (str): URL to access the created Notion page

### Description

This function creates a structured Notion page by:
1. Retrieving Notion API credentials from environment variables
2. Adding a link to the source audio file (if file_id is provided)
3. Creating a list of participants based on the speaker_map
4. Adding meeting summary and to-do items
5. Adding comprehensive meeting notes
6. Adding a toggleable transcript with all dialogue
7. Using batch processing to handle Notion API's 100-block limit per request

The function includes error handling for API rate limits and other potential issues when working with the Notion API.

### Example

```python
# Create a new Notion page with meeting information
page_id, page_url = processor.create_notion_page(
    title="Weekly Team Sync",
    summary="Discussion of Q2 goals and project timeline",
    todos=["Update project roadmap", "Schedule follow-up meeting"],
    segments=transcript_segments,
    speaker_map={"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"},
    file_id="1abc2defghijk3lmno4pqrs5tuv"
)

print(f"Created Notion page: {page_url}")
```

## _split_transcript_into_blocks

Helper function that splits a transcript into smaller blocks for Notion API.

### Signature

```python
def _split_transcript_into_blocks(self, transcript: str, max_length: int = 2000) -> List[str]:
```

### Parameters

- `transcript` (str): Full transcript text to split
- `max_length` (int, default=2000): Maximum character length per block

### Returns

- List of transcript segments, each below the max_length limit

### Description

This function:
1. Splits the transcript into lines
2. Groups lines together until reaching the max_length limit
3. Creates a new paragraph when max_length would be exceeded
4. Returns an array of paragraphs that can be safely added to Notion

The function is necessary because Notion API has a limit on block content length. By breaking 
the transcript into smaller chunks, we can avoid API errors when creating pages with long transcripts.

### Example

```python
# Split a long transcript into manageable blocks
transcript_blocks = processor._split_transcript_into_blocks(full_transcript, max_length=1500)

print(f"Split transcript into {len(transcript_blocks)} blocks")
```