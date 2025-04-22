FROM python:3.10-slim

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 建立非 root 用戶和群組
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# 複製 requirements.txt 檔案
COPY requirements.txt ./

# 升級 pip 並安裝 Python 依賴
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 複製其餘的檔案
COPY . .

# 更改 /app 目錄的擁有者為非 root 用戶
# 同時建立 credentials 目錄並設定權限
RUN mkdir -p /app/credentials && chown -R appuser:appuser /app

# 切換到非 root 用戶
USER appuser

# 暴露端口
EXPOSE 5000

# 啟動應用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "app:app"]
