# Utility Helper Functions

This document covers utility helper functions used in the Audio Processor.

## Contents

- [format_timestamp](#format_timestamp)
- [init_services](#init_services)

## format_timestamp

Converts a time value in seconds to a readable timestamp format.

### Signature

```python
def format_timestamp(self, seconds: float) -> str:
```

### Parameters

- `seconds` (float): Time in seconds to format

### Returns

- `timestamp` (str): Formatted timestamp string (MM:SS or HH:MM:SS format)

### Description

This function converts a floating-point seconds value into a human-readable timestamp by:
1. Converting seconds to hours, minutes, and seconds
2. Formatting the result as HH:MM:SS if hours > 0, otherwise as MM:SS
3. Using zero-padding to ensure consistent formatting

### Example

```python
# Format a timestamp from seconds
timestamp = processor.format_timestamp(125.5)  # 02:05
timestamp_long = processor.format_timestamp(3725.8)  # 01:02:05

print(f"Segment at {timestamp}")
```

## init_services

Initializes the external services used by the Audio Processor.

### Signature

```python
def init_services(self):
```

### Parameters

None

### Returns

None (initializes services within the instance)

### Description

This function is called during initialization to set up external service connections:
1. Initializes Google Drive API with appropriate credentials
   - Uses Service Account or OAuth credentials based on environment settings
   - Requests proper scopes for read and write access
2. Initializes Google Gemini API with the API key from environment variables

The function handles both authentication methods for Google Drive:
- Service account authentication (for server deployment)
- OAuth authentication (for development/personal use)

### Example

```python
# Normally called during initialization, but can be called again if needed
processor.init_services()
```