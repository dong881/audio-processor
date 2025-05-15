# Asynchronous Processing Functions

This document details the functions responsible for the asynchronous processing capability in the Audio Processor.

## Contents

- [process_file_async](#process_file_async)
- [_process_file_job](#_process_file_job)
- [get_job_status](#get_job_status)

## process_file_async

Creates an asynchronous job for file processing and returns a job ID.

### Signature

```python
def process_file_async(self, file_id: str, attachment_file_ids: Optional[List[str]] = None) -> str:
```

### Parameters

- `file_id` (str): Google Drive ID of the audio file to be processed
- `attachment_file_ids` (Optional[List[str]]): A list of Google Drive IDs for optional PDF attachments.

### Returns

- `job_id` (str): A unique identifier for tracking the job

### Description

This function initializes a new asynchronous processing job by:
1. Generating a unique job ID using UUID
2. Creating a job entry with initial "pending" status and storing it in the jobs dictionary
3. Submitting the actual processing function to a thread pool

### Example

```python
# Initialize a new processing job
job_id = processor.process_file_async("1abc2defghijk3lmno4pqrs5tuv", ["6vwx7yz8abcd9efgh0ijkl", "1mnop2qrst3uvwx4yz5abcd"])

# The job_id can be used to check the status later
print(f"Job initiated with ID: {job_id}")
```

## _process_file_job

Background worker function that processes the audio file and updates job status.

### Signature

```python
def _process_file_job(self, job_id: str, file_id: str, attachment_file_ids: Optional[List[str]] = None):
```

### Parameters

- `job_id` (str): The unique identifier for this job
- `file_id` (str): Google Drive ID of the audio file to be processed
- `attachment_file_ids` (Optional[List[str]]): A list of Google Drive IDs for optional PDF attachments.

### Returns

- Result dictionary (not directly returned but stored in job record)

### Description

This function executes the complete audio processing pipeline:
1. Updates job status to "processing" and sets progress to 5%
2. Downloads the audio file and optional attachments (if provided as a list)
3. Processes audio with regular status updates at key milestones
4. Identifies speakers, generates summary, creates Notion page
5. Renames the Google Drive file with the generated title
6. Upon completion, updates job status to "completed" and stores the result
7. If an error occurs, updates job status to "failed" and stores error information
8. Cleans up temporary files regardless of success or failure

This function is designed to be run in a background thread and not called directly.

## get_job_status

Retrieves the current status and details of a processing job.

### Signature

```python
def get_job_status(self, job_id: str) -> Dict[str, Any]:
```

### Parameters

- `job_id` (str): The unique ID of the job to check

### Returns

- Dictionary with job details including status, progress, and results if completed

### Description

This function looks up a job by its ID and returns appropriate information based on job status:
- For completed jobs: returns full result data including Notion page information
- For failed jobs: returns the error information
- For pending/processing jobs: returns current progress percentage

### Example

```python
# Check status of a job
status_info = processor.get_job_status("12345678-1234-5678-1234-567812345678")

if status_info.get('status') == 'completed':
    print(f"Job completed! Notion page: {status_info['result']['notion_page_url']}")
elif status_info.get('status') == 'processing':
    print(f"Job in progress: {status_info['progress']}% complete")
else:
    print(f"Job failed: {status_info.get('error')}")
```