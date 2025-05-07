# Audio Processor - 音訊會議轉錄與筆記工具 | Audio Meeting Transcription and Note-Taking Tool

[繁體中文](#繁體中文) | [English](#english)

## 繁體中文

### 專案簡介

Audio Processor 是一個專為會議錄音設計的智能處理工具，可以自動完成音訊轉文字、說話人分離、摘要生成、筆記格式化和 Notion 整合功能，讓您的會議記錄更加高效和專業。

### 功能特點

- **音訊處理**：支援各種音訊格式轉換為文字，移除靜音優化處理效率
- **說話人分離**：智能識別不同說話人，可自動標記身份
- **智能摘要**：使用 Google Gemini AI 生成會議摘要、提取關鍵待辦事項
- **格式化筆記**：將逐字稿整理為結構化 Markdown 筆記
- **Notion 整合**：自動生成精美排版的 Notion 頁面
- **Google Drive 整合**：直接處理 Google Drive 中的錄音檔案，支援檔案管理
- **使用者介面**：簡潔易用的 Web 界面，支援工作進度追蹤

### 系統架構

專案採用模組化設計，主要組件包括：

- **API 層 (app.py)**：處理 HTTP 請求，提供 RESTful API
- **音訊處理核心 (core/audio_processor.py)**：負責音訊轉換、預處理和說話人分離
- **筆記處理 (core/note_handler.py)**：處理摘要生成、筆記格式化和 Notion 整合
- **Google 服務 (services/google_service.py)**：處理 Google Drive API 整合
- **認證管理 (services/auth_manager.py)**：處理 OAuth 認證流程
- **格式化工具 (core/notion_formatter.py)**：處理 Markdown 到 Notion 格式的轉換
- **前端介面 (templates/ 和 static/)**：用戶操作界面

### 環境需求

- Python 3.9+
- Docker (推薦使用)
- 需要的 API 金鑰:
  - Google API (Drive API, OAuth)
  - Hugging Face API 金鑰 (pyannote/speaker-diarization)
  - Google Gemini API 金鑰
  - Notion API 金鑰 (選用)

### 快速開始

#### 使用 Docker (推薦)

1. 複製環境變數範本並填入金鑰:
   ```bash
   cp .env.sample .env
   # 編輯 .env 檔案填入您的 API 金鑰
   ```

2. 使用 Docker Compose 啟動服務:
   ```bash
   docker-compose up -d
   ```

3. 訪問 Web 界面:
   ```
   http://localhost:5000
   ```

#### 手動安裝

1. 安裝依賴:
   ```bash
   pip install -r requirements.txt
   ```

2. 設置環境變數:
   ```bash
   cp .env.sample .env
   # 編輯 .env 檔案填入您的 API 金鑰
   ```

3. 啟動服務:
   ```bash
   python app.py
   ```

### 環境變數設置

建立 `.env` 檔案，包含以下配置:

```
# Google API 設定
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/api/auth/google/callback

# Hugging Face 金鑰 (用於說話人分離)
HF_TOKEN=your_huggingface_token

# Gemini API 金鑰 (用於生成摘要)
GEMINI_API_KEY=your_gemini_api_key

# Notion API 設定 (選用)
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_notion_database_id

# 應用設定
FLASK_DEBUG=false
FLASK_SECRET_KEY=random_secret_key
WHISPER_MODEL_SIZE=medium
WHISPER_LANGUAGE=zh
REMOVE_SILENCE=true
```

### API 參考

系統提供以下 API 端點:

- `GET /health`: 健康檢查
- `POST /process`: 處理音頻檔案
- `GET /job/{job_id}`: 獲取工作狀態
- `GET /jobs`: 獲取所有進行中的工作列表
- `GET /api/auth/google`: Google 認證流程
- `GET /drive/files`: 列出 Google Drive 檔案

詳細 API 規格請參考 [API 文檔](docs/api)。

### 使用流程

1. 登入系統 (使用 Google 帳號)
2. 從 Google Drive 選擇音訊檔案
3. 點擊「處理」按鈕，開始自動處理
4. 查看處理進度和結果
5. 完成後，系統會自動生成 Notion 頁面

### 開發貢獻

1. Fork 專案
2. 建立 feature 分支
3. 提交變更
4. 推送到遠端分支
5. 發起 Pull Request

### 許可證

MIT

---

## English

### Project Overview

Audio Processor is an intelligent processing tool designed for meeting recordings. It automatically performs audio-to-text conversion, speaker diarization, summary generation, note formatting, and Notion integration, making your meeting records more efficient and professional.

### Key Features

- **Audio Processing**: Supports conversion of various audio formats to text, removing silence to optimize processing efficiency
- **Speaker Diarization**: Intelligently identifies different speakers, capable of automatically labeling identities
- **Smart Summarization**: Uses Google Gemini AI to generate meeting summaries and extract key action items
- **Formatted Notes**: Organizes transcripts into structured Markdown notes
- **Notion Integration**: Automatically generates beautifully formatted Notion pages
- **Google Drive Integration**: Directly processes recording files from Google Drive, supporting file management
- **User Interface**: Clean, easy-to-use web interface with job progress tracking

### System Architecture

The project adopts a modular design with these main components:

- **API Layer (app.py)**: Handles HTTP requests, provides RESTful API
- **Audio Processing Core (core/audio_processor.py)**: Responsible for audio conversion, preprocessing, and speaker diarization
- **Note Processing (core/note_handler.py)**: Handles summary generation, note formatting, and Notion integration
- **Google Services (services/google_service.py)**: Manages Google Drive API integration
- **Authentication Management (services/auth_manager.py)**: Handles OAuth authentication flow
- **Formatting Tools (core/notion_formatter.py)**: Processes conversion from Markdown to Notion format
- **Frontend Interface (templates/ and static/)**: User operation interface

### Requirements

- Python 3.9+
- Docker (recommended)
- Required API keys:
  - Google API (Drive API, OAuth)
  - Hugging Face API key (pyannote/speaker-diarization)
  - Google Gemini API key
  - Notion API key (optional)

### Quick Start

#### Using Docker (Recommended)

1. Copy the environment variable template and fill in your keys:
   ```bash
   cp .env.sample .env
   # Edit the .env file to fill in your API keys
   ```

2. Start the service using Docker Compose:
   ```bash
   docker-compose up -d
   ```

3. Access the web interface:
   ```
   http://localhost:5000
   ```

#### Manual Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   ```bash
   cp .env.sample .env
   # Edit the .env file to fill in your API keys
   ```

3. Start the service:
   ```bash
   python app.py
   ```

### Environment Variables

Create a `.env` file with the following configurations:

```
# Google API Settings
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:5000/api/auth/google/callback

# Hugging Face Key (for speaker diarization)
HF_TOKEN=your_huggingface_token

# Gemini API Key (for summary generation)
GEMINI_API_KEY=your_gemini_api_key

# Notion API Settings (optional)
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_notion_database_id

# Application Settings
FLASK_DEBUG=false
FLASK_SECRET_KEY=random_secret_key
WHISPER_MODEL_SIZE=medium
WHISPER_LANGUAGE=zh
REMOVE_SILENCE=true
```

### API Reference

The system provides the following API endpoints:

- `GET /health`: Health check
- `POST /process`: Process audio files
- `GET /job/{job_id}`: Get job status
- `GET /jobs`: Get a list of all ongoing jobs
- `GET /api/auth/google`: Google authentication flow
- `GET /drive/files`: List Google Drive files

For detailed API specifications, please refer to the [API Documentation](docs/api).

### Usage Flow

1. Log in to the system (using a Google account)
2. Select an audio file from Google Drive
3. Click the "Process" button to start automatic processing
4. View processing progress and results
5. Upon completion, the system will automatically generate a Notion page

### Contributing

1. Fork the project
2. Create a feature branch
3. Commit your changes
4. Push to the remote branch
5. Submit a Pull Request

### License

MIT
