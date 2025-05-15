# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed
# ffmpeg is commonly used for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
# Using a persistent cache directory for pip that will be a volume, matching docker-compose.yml
RUN mkdir -p /root/.cache/pip && \
    pip install --no-cache-dir -r requirements.txt --cache-dir /root/.cache/pip

# Copy the rest of the application code into the container at /app
# This includes main.py, the app/ directory, etc.
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variables (can be overridden by docker-compose)
ENV FLASK_APP=main.py
ENV PORT=5000
ENV FLASK_DEBUG=false
# Cache directories for models, etc. (matches docker-compose volumes)
ENV HF_HOME=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch
ENV PYANNOTE_CACHE=/app/.cache/pyannote
# Credential paths (matches docker-compose volumes and env vars)
ENV GOOGLE_SA_JSON_PATH=/app/credentials/service-account.json
ENV GOOGLE_CLIENT_SECRET_PATH=/app/credentials/client_secret.json

# Run main.py when the container launches using Gunicorn
# Gunicorn is specified in requirements.txt
# Bind to 0.0.0.0 to be accessible from outside the container
# Number of workers can be adjusted. Timeout increased for potentially long audio tasks.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app", "--timeout", "300", "--workers", "3"] 