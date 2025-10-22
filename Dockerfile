# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# ffmpeg is required for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python packages
RUN mkdir -p /root/.cache/pip && \
    pip install --no-cache-dir -r requirements.txt --cache-dir /root/.cache/pip

# Copy the application code
COPY . .

# Expose port 5000
EXPOSE 5000

# Define environment variables
ENV FLASK_APP=main.py
ENV PORT=5000
ENV FLASK_DEBUG=false

# Cache directories for AI models
ENV HF_HOME=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch
ENV PYANNOTE_CACHE=/app/.cache/pyannote

# Credential path
ENV GOOGLE_SA_JSON_PATH=/app/credentials/service-account.json

# Run the application using Gunicorn
# Increased timeout for long audio processing tasks
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app", "--timeout", "600", "--workers", "2"]
