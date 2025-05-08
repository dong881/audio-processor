FROM python:3.9

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
RUN pip install --no-cache-dir --upgrade pip --root-user-action=ignore && \
    pip install --no-cache-dir -r requirements.txt --root-user-action=ignore

# 複製其餘的檔案
COPY . .

# 建立並設置所有必要的目錄和權限
RUN mkdir -p /app/credentials \
    && mkdir -p /app/.cache \
    && mkdir -p /app/.cache/huggingface \
    && mkdir -p /app/.cache/torch \
    && mkdir -p /app/.cache/pyannote \
    && mkdir -p /app/app/utils \
    && mkdir -p /app/app/services \
    && mkdir -p /app/app/routes \
    && chmod -R 777 /app/.cache \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /home/appuser

# 切換到非 root 用戶
USER appuser

# 設置環境變數，確保HuggingFace等庫使用正確的cache目錄
ENV HF_HOME=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch
ENV PYANNOTE_CACHE=/app/.cache/pyannote

# 暴露端口
EXPOSE 5000

# 啟動應用 - 使用main.py作為入口點
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "8", "--timeout", "300", "main:app"]
