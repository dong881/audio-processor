# Audio Processor Documentation

Welcome to the comprehensive documentation for the Audio Processor project. This documentation provides detailed explanations of all components of the system.

## Table of Contents

### API Documentation
- [API Reference](./api/README.md) - Detailed documentation of all API endpoints

### Core Functionality
- [Asynchronous Processing](./core/async_processing.md) - Job management and asynchronous processing
- [Audio Processing](./core/audio_processing.md) - Audio file handling and processing
- [AI Processing](./core/ai_processing.md) - AI-powered features (speaker identification, summarization)
- [External Integrations](./core/external_integrations.md) - Integration with Google Drive and Notion

### Utility Functions
- [Helper Functions](./utils/helper_functions.md) - Utility functions used throughout the application

## Architecture Overview

The Audio Processor follows a modern asynchronous processing architecture:

1. **API Layer**: Flask endpoints for submitting jobs and checking status
2. **Job Management**: Background thread pool for processing audio files asynchronously 
3. **Audio Processing Pipeline**: Audio conversion, transcription, and speaker diarization
4. **AI Analysis**: Speaker identification, summarization, and notes generation
5. **External Integrations**: Interacting with Google Drive and Notion APIs

This architecture allows for:
- Handling multiple processing jobs simultaneously
- Immediate response to API requests with job IDs
- Progress tracking for long-running operations
- Efficient resource utilization

## Technology Stack

- **Web Framework**: Flask
- **Audio Processing**: Whisper (OpenAI), Pyannote Audio
- **AI Generation**: Google Gemini
- **External Services**: Google Drive API, Notion API
- **Infrastructure**: Docker, Docker Compose

## Getting Started

For setup instructions, configuration details, and usage examples, please refer to the [main README](../README.md) file in the project root.