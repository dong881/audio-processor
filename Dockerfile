FROM python:3.10-slim

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 複製需要的檔案
COPY requirements.txt .
COPY app.py .
COPY .env .

# 建立結構目錄
RUN mkdir -p /app/credentials

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 5000

# 啟動應用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "app:app"]
