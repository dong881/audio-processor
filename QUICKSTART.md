# Quick Start Guide

Get the audio-to-GitHub service running in 5 minutes.

## Prerequisites

- Docker & Docker Compose installed
- Google service account JSON file
- Google Gemini API key
- Hugging Face token
- GitHub personal access token

## Step 1: Clone and Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd audio-processor

# Copy environment template
cp .env.example .env
```

## Step 2: Configure Environment

Edit `.env` file:

```env
# Google Drive API
GOOGLE_SA_JSON_PATH=/app/credentials/service-account.json

# Google Gemini API (Get from https://makersuite.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# Hugging Face (Get from https://huggingface.co/settings/tokens)
HF_TOKEN=your_huggingface_token_here

# GitHub Configuration (Get from https://github.com/settings/tokens)
GITHUB_TOKEN=ghp_your_github_token_here
GITHUB_REPO=your-username/your-repo-name
GITHUB_PATH=notes/Meeting-Minutes
GITHUB_BRANCH=main
GITHUB_FILENAME_TEMPLATE=MM-YYYYMMDD.md
```

## Step 3: Add Credentials

```bash
# Create credentials directory
mkdir credentials

# Copy your Google service account JSON
# (Download from Google Cloud Console)
cp /path/to/your/service-account.json credentials/
```

## Step 4: Start Service

```bash
# Build and start
docker-compose up -d

# Check logs
docker-compose logs -f
```

First startup will take 10-15 minutes to download AI models.

## Step 5: Test the API

```bash
# Health check
curl http://localhost:5000/health

# Should return:
# {"status": "healthy", "timestamp": "...", "active_jobs": 0}
```

## Step 6: Process Your First Audio

### Get Google Drive File ID

1. Upload an audio file to Google Drive
2. Right-click → Get link
3. Extract file ID from URL:
   ```
   https://drive.google.com/file/d/1abc123def456ghi789/view
                                    ^^^^^^^^^^^^^^^^
                                    This is the file_id
   ```

### Submit Processing Job

```bash
curl -X POST http://localhost:5000/process \
  -H "Content-Type: application/json" \
  -d '{"file_id": "1abc123def456ghi789"}'
```

Response:
```json
{
  "success": true,
  "message": "Job submitted for processing",
  "job_id": "abc123-def456-...",
  "job_status": "pending"
}
```

### Check Job Status

```bash
# Replace with your actual job_id
curl http://localhost:5000/job/abc123-def456-...
```

Response (processing):
```json
{
  "success": true,
  "job": {
    "id": "abc123-def456-...",
    "status": "processing",
    "progress": 45,
    "message": "🎤 Transcribing audio...",
    "created_at": "2025-10-22T10:30:00",
    "updated_at": "2025-10-22T10:32:15"
  }
}
```

Response (completed):
```json
{
  "success": true,
  "job": {
    "id": "abc123-def456-...",
    "status": "completed",
    "progress": 100,
    "message": "✅ Processing complete!",
    "result": {
      "success": true,
      "github_url": "https://github.com/user/repo/blob/main/notes/MM-20251022.md",
      "filename": "MM-20251022.md",
      "segments_count": 45
    }
  }
}
```

### View Meeting Minutes

Open the GitHub URL from the result to see your meeting minutes!

## Common Issues

### "Drive API not initialized"

**Problem:** Service account not found or invalid.

**Solution:**
1. Verify `credentials/service-account.json` exists
2. Check path in `.env` matches
3. Ensure service account has Drive API enabled

### "Gemini API quota exceeded"

**Problem:** API quota limit reached.

**Solution:**
1. Service automatically tries alternative models
2. Wait for quota reset
3. Upgrade API plan at Google AI Studio

### "GitHub commit failed"

**Problem:** GitHub token lacks permissions.

**Solution:**
1. Create new token with `repo` scope
2. Verify repository name format: `username/repo`
3. Create the path in GitHub first if it doesn't exist

### Models downloading slowly

**Problem:** First-time model download.

**Solution:**
- Be patient, this is normal
- Models are ~2-3GB total
- Only happens on first run
- Models are cached for future use

## Monitoring

### View Logs

```bash
# Follow logs in real-time
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100

# Filter by service
docker-compose logs audio-processor
```

### Check Active Jobs

```bash
# List all active jobs
curl http://localhost:5000/jobs?filter=active

# List all jobs
curl http://localhost:5000/jobs?filter=all

# List completed jobs
curl http://localhost:5000/jobs?filter=completed
```

### Cancel a Job

```bash
curl -X POST http://localhost:5000/job/abc123-def456-.../cancel
```

## Updating

After making code changes:

```bash
# Stop service
docker-compose stop

# Rebuild
docker-compose build

# Start again
docker-compose up -d

# Check logs
docker-compose logs -f
```

## Production Tips

1. **Use HTTPS**: Deploy behind reverse proxy (nginx/traefik)
2. **Set Secret Key**: Generate strong `FLASK_SECRET_KEY`
3. **Enable Auth**: Add API key authentication if needed
4. **Monitor**: Set up logging aggregation
5. **Backup**: GitHub has your data, but backup credentials
6. **Scale**: Increase `max_workers` for high load
7. **Resource Limits**: Set Docker memory/CPU limits

## Next Steps

- Set up GitHub Actions for CI/CD
- Add webhook for automated processing
- Configure monitoring alerts
- Set up automated backups
- Add rate limiting for production

## Support

For issues or questions:
1. Check logs first: `docker-compose logs -f`
2. Review README.md for detailed documentation
3. Check PROJECT_STRUCTURE.md for architecture
4. Review cursor_responses/cursor_response.md for changes

---

Ready to process your meeting recordings! 🎤➡️📝➡️📤
