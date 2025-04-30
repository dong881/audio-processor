# Audio Processing Functions

This document details the functions responsible for processing audio files in the Audio Processor.

## Contents

- [preprocess_audio](#preprocess_audio)
- [process_audio](#process_audio)
- [convert_to_wav](#convert_to_wav)
- [load_models](#load_models)

## preprocess_audio

Preprocesses audio to improve processing efficiency by removing silence.

### Signature

```python
def preprocess_audio(self, audio_path: str) -> str:
```

### Parameters

- `audio_path` (str): Path to the audio file to be preprocessed

### Returns

- `processed_path` (str): Path to the processed audio file with silence removed

### Description

This function optimizes audio files before transcription by:
1. Loading the audio file using librosa
2. Detecting non-silent intervals using librosa.effects.split
3. Creating a new audio file containing only the non-silent segments
4. Calculating time savings from silence removal

The function will return the original path if:
- Preprocessing fails for any reason
- No non-silent segments are detected
- The resulting processed audio is too short (less than 0.5 seconds)

### Example

```python
# Preprocess an audio file to remove silence
processed_audio_path = processor.preprocess_audio("/path/to/audio/file.wav")

# The processed path can be used for further processing
print(f"Preprocessed audio saved to: {processed_audio_path}")
```

## process_audio

Processes audio for transcription and diarization.

### Signature

```python
def process_audio(self, audio_path: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
```

### Parameters

- `audio_path` (str): Path to the audio file to be processed

### Returns

- `transcript_full` (str): Complete transcript text
- `segments` (List[Dict]): List of transcript segments with speaker information
- `original_speakers` (List[str]): List of uniquely identified speakers

### Description

This function is the main audio processing pipeline:
1. Loads required AI models (Whisper and Pyannote)
2. Converts audio to WAV format if needed
3. Preprocesses audio to remove silence
4. Performs transcription using Whisper
5. Performs speaker diarization using Pyannote
6. Integrates the results to create segments with speaker information

Each segment in the returned list contains:
- speaker: The identified speaker label (e.g., "SPEAKER_00")
- start: Start time of the segment in seconds
- end: End time of the segment in seconds
- text: Transcribed text for the segment

### Example

```python
# Process an audio file for transcription and speaker diarization
transcript, segments, speakers = processor.process_audio("/path/to/audio/file.wav")

# Print the first few segments
for segment in segments[:3]:
    print(f"{segment['speaker']} ({segment['start']:.2f}-{segment['end']:.2f}s): {segment['text']}")
```

## convert_to_wav

Converts an audio file to WAV format (16kHz mono).

### Signature

```python
def convert_to_wav(self, input_path: str) -> str:
```

### Parameters

- `input_path` (str): Path to the input audio file

### Returns

- `output_path` (str): Path to the converted WAV file

### Description

This function standardizes audio files for processing:
1. Creates an output path in the same directory as the input file
2. Uses FFmpeg to convert the file to 16kHz, mono, 16-bit PCM WAV
3. Returns the path to the new WAV file

### Example

```python
# Convert an MP3 file to WAV format
wav_path = processor.convert_to_wav("/path/to/audio/file.mp3")

# The WAV file can now be used for transcription
print(f"Converted audio saved to: {wav_path}")
```

## load_models

Loads the AI models required for audio processing.

### Signature

```python
def load_models(self):
```

### Parameters

None

### Returns

None (updates the instance variables `whisper_model` and `diarization_pipeline`)

### Description

This function lazily loads AI models when they are needed:
1. Loads the Whisper model (medium size) for speech-to-text transcription
2. Loads the Pyannote model for speaker diarization with enhanced error handling:
   - Uses a specific model version (pyannote/speaker-diarization-3.1) for better compatibility
   - Implements a retry mechanism that attempts loading up to 3 times before failing
   - Provides detailed logging during loading attempts

The function only loads models that haven't been loaded already, preventing redundant loading.

### Example

```python
# Load the required AI models
processor.load_models()

# Now the models are ready for processing
print("Models loaded successfully")
```