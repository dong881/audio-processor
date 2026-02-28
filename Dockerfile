# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed
# ffmpeg is commonly used for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file first (for better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN mkdir -p /root/.cache/pip && \
    pip install --no-cache-dir -r requirements.txt --cache-dir /root/.cache/pip

# Copy the rest of the application code into the container
COPY . .

# Create necessary directories
RUN mkdir -p /app/credentials /app/.cache

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variables (can be overridden by docker-compose)
ENV FLASK_APP=main.py \
    PORT=5000 \
    FLASK_DEBUG=false \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch \
    PYANNOTE_CACHE=/app/.cache/pyannote \
    GOOGLE_SA_JSON_PATH=/app/credentials/service-account.json \
    GOOGLE_CLIENT_SECRET_PATH=/app/credentials/client_secret.json

# Run main.py when the container launches using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app", "--timeout", "600", "--workers", "2"] 