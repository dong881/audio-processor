# 語音處理系統安裝指南

本指南將幫助你在 GCP VM (或其他雲端服務) 上設置語音處理系統。

## 前置需求

- Ubuntu Server (推薦 20.04 LTS)
- 足夠的儲存空間 (至少 10GB)
- 至少 4GB RAM

## 安裝步驟

### 1. 安裝基本依賴

```bash
# 更新套件管理器
sudo apt update
sudo apt upgrade -y

# 安裝必要系統套件
sudo apt install -y \
    python3-pip \
    python3-venv \
    ffmpeg \
    git \
    curl \
    docker.io \
    docker-compose

# 啟用 Docker 服務
sudo systemctl enable docker
sudo systemctl start docker

# 將當前使用者加入 docker 群組 (需登出再登入生效)
sudo usermod -aG docker $USER
```

### 2. 下載專案

```bash
# 建立專案目錄
mkdir -p ~/audio-processor
cd ~/audio-processor

# 下載專案檔案 (替換成實際的下載方式)
# 例如: 從 GitHub 複製
# git clone https://github.com/yourusername/audio-processor.git .

# 或手動建立文件
# 將 app.py, requirements.txt, Dockerfile, docker-compose.yml 複製到此目錄
```

### 3. 設定認證

```bash
# 建立認證目錄
mkdir -p credentials

# 準備必要的認證檔案
# 1. Google API 服務帳號金鑰 (service-account.json)
# 2. Google OAuth 認證 (oauth-credentials.json)
# 3. 其他必要的 API 金鑰

# 編輯 .env 檔案，填入你的 API 金鑰
nano .env
```

### 4. 取得必要的 API 認證

#### Google 服務帳號 (Google Drive API)

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立專案或選擇現有專案
3. 啟用 Google Drive API
4. 建立服務帳號並下載金鑰 (JSON 格式)
5. 將金鑰移至 `credentials/service-account.json`

#### Hugging Face 權杖 (pyannote.audio)

1. 註冊/登入 [Hugging Face](https://huggingface.co/)
2. 前往個人設定頁面，建立新的 API 權杖
3. 將權杖複製到 `.env` 檔案中的 `HF_TOKEN` 欄位

#### Gemini API 金鑰

1. 前往 [Google AI Studio](https://makersuite.google.com/)
2. 取得 API 金鑰
3. 將金鑰複製到 `.env` 檔案中的 `GEMINI_API_KEY` 欄位

#### Notion API 整合

1. 前往 [Notion Integrations](https://www.notion.so/my-integrations)
2. 建立新的整合
3. 將整合權杖複製到 `.env` 檔案中的 `NOTION_TOKEN` 欄位
4. 在 Notion 中建立資料庫，並將資料庫 ID 複製到 `NOTION_DATABASE_ID` 欄位
5. 記得將你的 Notion 整合添加到資料庫的共享設定中

### 5. 使用 Docker 啟動服務

```bash
# 建置和啟動 Docker 容器
docker-compose up -d

# 檢查服務日誌
docker-compose logs -f
```

### 6. 測試 API

```bash
# 健康檢查
curl http://localhost:5000/health

# 處理音檔 (替換成實際的 Google Drive 檔案 ID)
curl -X POST http://localhost:5000/process \
  -H "Content-Type: application/json" \
  -d '{"file_id": "YOUR_GOOGLE_DRIVE_FILE_ID"}'
```

## 生產環境建議

1. **設定 HTTPS**: 使用 Nginx 或 Cloudflare 代理流量並啟用 SSL
2. **設定防火牆**: 僅開放必要的端口 (如 80, 443)
3. **監控**: 設定基本的系統監控 (如 Prometheus + Grafana)
4. **自動重啟**: 確保服務在重新啟動後自動執行

## 疑難排解

### FFmpeg 錯誤
如果看到 FFmpeg 相關錯誤，確認已正確安裝:
```bash
sudo apt install -y ffmpeg
ffmpeg -version
```

### 記憶體不足
如果收到記憶體錯誤，增加虛擬記憶體:
```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### GPU 相關問題
注意: 本系統設計為在 CPU 環境運行。如需使用 GPU，必須修改 `requirements.txt` 中的 torch 版本，並調整 Dockerfile。
