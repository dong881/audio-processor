FROM python:3.10-slim

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 建立非 root 用戶和群組，並指定 home 目錄
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser -d /home/appuser -m appuser

# 複製 requirements.txt 檔案
COPY requirements.txt ./

# 升級 pip 並安裝 Python 依賴 (忽略 build-time root warning as final container runs non-root)
RUN pip install --no-cache-dir --upgrade pip --root-user-action=ignore
# 明確安裝 OpenAI Whisper 套件
RUN pip install --no-cache-dir openai-whisper --root-user-action=ignore
RUN pip install --no-cache-dir -r requirements.txt --root-user-action=ignore

# 複製其餘的檔案
COPY . .

# 更改 /app 目錄的擁有者為非 root 用戶
# 同時建立 credentials 和 cache 目錄並設定權限
# 確保 /home/appuser 也屬於 appuser
RUN mkdir -p /app/credentials \
    && mkdir -p /app/.cache \
    && mkdir -p /app/.cache/huggingface \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /home/appuser

# 切換到非 root 用戶
USER appuser

# 暴露端口
EXPOSE 5000

# 啟動應用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "8", "--timeout", "300", "app:app"]
