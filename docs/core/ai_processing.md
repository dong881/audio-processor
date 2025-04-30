# AI Processing Functions

This document details the functions responsible for AI-powered processing in the Audio Processor.

## Contents

- [identify_speakers](#identify_speakers)
- [generate_summary](#generate_summary)
- [generate_comprehensive_notes](#generate_comprehensive_notes)

## identify_speakers

Uses Google Gemini to identify real speaker names from speaker labels.

### Signature

```python
def identify_speakers(self, segments: List[Dict[str, Any]], original_speakers: List[str]) -> Dict[str, str]:
```

### Parameters

- `segments` (List[Dict]): List of transcript segments with speaker information
- `original_speakers` (List[str]): List of speaker IDs (e.g., "SPEAKER_00", "SPEAKER_01")

### Returns

- Dictionary mapping original speaker IDs to identified names (e.g., `{"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"}`)

### Description

This function attempts to infer the real identity of speakers by:
1. Extracting sample dialogue from the beginning of the transcript
2. Prompting Google Gemini to analyze the conversation and identify likely speaker names
3. Parsing the JSON response to create a mapping from speaker IDs to names

If speaker identification fails, the function returns the original speaker IDs.

### Example

```python
# Identify speakers in a transcript
speaker_map = processor.identify_speakers(segments, ["SPEAKER_00", "SPEAKER_01"])

# Use the mapping to update speaker labels
for segment in segments:
    original_speaker = segment["speaker"]
    identified_speaker = speaker_map.get(original_speaker, original_speaker)
    print(f"{identified_speaker}: {segment['text']}")
```

## generate_summary

Uses Google Gemini to generate a meeting title, summary, and to-do list.

### Signature

```python
def generate_summary(self, transcript: str, attachment_text: Optional[str] = None) -> Dict[str, Any]:
```

### Parameters

- `transcript` (str): Full transcript text with speaker information
- `attachment_text` (Optional[str]): Optional text from a PDF attachment for context

### Returns

- Dictionary containing generated information:
  - `title`: Meeting title
  - `summary`: Meeting summary (200-300 words)
  - `todos`: List of action items identified in the meeting

### Description

This function analyzes the transcript to:
1. Create a concise but descriptive title for the meeting
2. Generate a comprehensive summary of the key points discussed
3. Extract action items and to-do items mentioned in the meeting

The function provides context from the optional attachment text to help Gemini understand any specialized terminology or background information that might be referenced in the meeting.

### Example

```python
# Generate a summary for a meeting transcript
summary_data = processor.generate_summary(transcript_text, pdf_text)

print(f"Meeting Title: {summary_data['title']}")
print(f"Summary: {summary_data['summary']}")
print("Action Items:")
for item in summary_data['todos']:
    print(f"- {item}")
```

## generate_comprehensive_notes

Uses Google Gemini to create structured, readable meeting notes.

### Signature

```python
def generate_comprehensive_notes(self, transcript: str) -> str:
```

### Parameters

- `transcript` (str): Full transcript text with speaker information

### Returns

- `comprehensive_notes` (str): Well-formatted, structured meeting notes

### Description

This function creates professional meeting notes using the latest Gemini 2.5 Pro model:
1. Sends the full transcript to Gemini with a clear, direct prompt
2. Instructs the model to create organized notes with:
   - Clear topic sections prefixed with "主題："
   - Bullet points using "•" symbols
   - Decision items marked with "決策："
   - Appropriate formatting for Notion compatibility

The function uses a straightforward, single-pass approach that produces consistently well-structured notes optimized for readability in Notion.

### Example

```python
# Generate comprehensive meeting notes
detailed_notes = processor.generate_comprehensive_notes(transcript_text)

# The notes can be included in the Notion page
print(detailed_notes)
```