import os
import tempfile
import shutil
import subprocess
import json
import re
import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import requests
import atexit
import base64

# Google API
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Audio processing
import whisper
from pyannote.audio import Pipeline

# LLM API
import google.generativeai as genai

# PDF processing
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

from app.utils.constants import JOB_STATUS


class AudioProcessor:
    def __init__(self, max_workers=3):
        self.whisper_model = None
        self.diarization_pipeline = None
        self.drive_service = None
        
        # Thread pool
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        atexit.register(self.shutdown_executor)
        
        # Job tracking
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        self.cancelled_jobs = set()
        
        # Initialize services
        self.init_services()

    def init_services(self):
        """Initialize required services"""
        logging.info("🔄 Initializing services...")
        
        # Initialize Google Drive API with service account
        sa_json_path = os.getenv("GOOGLE_SA_JSON_PATH", "credentials/service-account.json")
        
        try:
            if not os.path.isabs(sa_json_path):
                if os.path.exists(sa_json_path):
                    sa_json_path = os.path.abspath(sa_json_path)
                elif os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), sa_json_path)):
                    sa_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), sa_json_path)
                
            if not os.path.exists(sa_json_path):
                alternative_paths = [
                    "/app/credentials/service-account.json",
                    "./credentials/service-account.json"
                ]
                
                for path in alternative_paths:
                    if os.path.exists(path):
                        logging.info(f"✅ Found service account at: {path}")
                        sa_json_path = path
                        break
                else:
                    raise FileNotFoundError(f"Cannot find service account JSON file")
                
            logging.info(f"🔄 Using service account file: {sa_json_path}")
            service_credentials = service_account.Credentials.from_service_account_file(
                sa_json_path,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            self.drive_service = build('drive', 'v3', credentials=service_credentials)
            logging.info("✅ Drive API initialized successfully")
        except Exception as e:
            logging.error(f"❌ Failed to initialize Google Drive API: {str(e)}")
            self.drive_service = None
        
        # Initialize Google Gemini API
        try:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if not gemini_api_key:
                logging.warning("⚠️ GEMINI_API_KEY not set")
            else:
                genai.configure(api_key=gemini_api_key)
                logging.info("✅ Gemini API initialized successfully")
        except Exception as e:
            logging.error(f"❌ Failed to initialize Gemini API: {str(e)}")
        
        logging.info("✅ Service initialization complete")

    def download_file(self, file_id: str, target_dir: str) -> str:
        """Download file from Google Drive"""
        logging.info(f"📥 Downloading file (ID: {file_id})")
        
        try:
            if not self.drive_service:
                raise RuntimeError("Drive API not initialized")
            
            os.makedirs(target_dir, exist_ok=True)
            
            file_meta = self.drive_service.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            
            raw_file_name = file_meta.get('name', f"file_{file_id}")
            safe_file_name = re.sub(r'[\\/*?:"<>|]', "_", raw_file_name)
            local_path = os.path.join(target_dir, safe_file_name)
            
            request_obj = self.drive_service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request_obj)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            logging.info(f"✅ File downloaded: {safe_file_name}")
            return safe_file_name
            
        except Exception as e:
            logging.error(f"❌ Failed to download file: {str(e)}")
            raise

    def download_from_drive(self, file_id: str) -> Tuple[str, str]:
        """Download file from Google Drive to temp directory"""
        logging.info(f"📥 Downloading file (ID: {file_id})")
        
        try:
            if not self.drive_service:
                raise RuntimeError("Drive API not initialized")
            
            temp_dir = tempfile.mkdtemp()
            
            file_meta = self.drive_service.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            
            raw_file_name = file_meta.get('name', f"file_{file_id}")
            safe_file_name = re.sub(r'[\\/*?:"<>|]', "_", raw_file_name)
            local_path = os.path.join(temp_dir, safe_file_name)
            
            request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            logging.info(f"✅ File downloaded: {safe_file_name}")
            return local_path, temp_dir
            
        except Exception as e:
            logging.error(f"❌ Download failed: {str(e)}")
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise

    def convert_to_wav(self, input_path: str) -> str:
        """Convert audio file to WAV format (16kHz mono)"""
        logging.info(f"🔄 Converting to WAV format...")
        
        output_dir = os.path.dirname(input_path)
        output_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}.wav"
        output_path = os.path.join(output_dir, output_filename)
        
        try:
            cmd = [
                "ffmpeg", 
                "-y",
                "-i", input_path,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                output_path
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info(f"✅ Conversion complete")
            
            return output_path
            
        except subprocess.CalledProcessError as e:
            logging.error(f"❌ Conversion failed: {e}")
            raise

    def load_models(self):
        """Load AI models"""
        logging.info("🔄 Loading AI models...")
        
        if self.whisper_model is None:
            try:
                logging.info("- Loading Whisper model (medium)...")
                self.whisper_model = whisper.load_model("medium")
                logging.info("✅ Whisper model loaded")
            except Exception as e:
                logging.error(f"❌ Failed to load Whisper model: {e}")
                raise
        
        if self.diarization_pipeline is None:
            max_retries = 3
            retry_count = 0
            last_error = None
            
            while retry_count < max_retries:
                try:
                    logging.info(f"- Loading speaker diarization model... (attempt {retry_count + 1}/{max_retries})")
                    hf_token = os.getenv("HF_TOKEN")
                    if not hf_token:
                        raise ValueError("Missing HF_TOKEN environment variable")
                    
                    self.diarization_pipeline = Pipeline.from_pretrained(
                        "pyannote/speaker-diarization-3.1",
                        use_auth_token=hf_token
                    )
                    logging.info("✅ Speaker diarization model loaded")
                    break
                except Exception as e:
                    last_error = e
                    logging.error(f"❌ Failed to load diarization model: {e}")
                    retry_count += 1
                    time.sleep(2)
            
            if self.diarization_pipeline is None:
                logging.error(f"❌ Failed to load diarization model after {max_retries} attempts")
                raise last_error or RuntimeError("Failed to load diarization pipeline")

    def try_multiple_gemini_models(self, system_prompt: str, user_content: str, 
                                models: List[str] = None) -> Any:
        """Try generating content using multiple Gemini models"""
        if models is None:
            models = ['gemini-2.0-flash-exp', 'gemini-2.0-flash', 'gemini-1.5-flash']
        
        response = None
        last_error = None

        for model_name in models:
            try:
                logging.info(f"🔄 Using model: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    [system_prompt, user_content]
                )
                logging.info(f"✅ Successfully generated content with {model_name}")
                break
            except Exception as e:
                last_error = e
                if "429" in str(e) or "quota" in str(e).lower():
                    logging.warning(f"⚠️ Model {model_name} quota exceeded")
                    continue
                else:
                    logging.error(f"❌ Error with model {model_name}: {str(e)}")
                    raise

        if response is None:
            logging.error("❌ All models failed")
            raise last_error
        
        return response

    def generate_meeting_notes(self, transcript: str) -> str:
        """Generate structured meeting notes using Gemini"""
        logging.info("🔄 Generating meeting notes...")
        
        try:
            system_prompt = """
            You are an expert in telecommunications and electronic engineering, familiar with technical terms like socket, RIC, gNB, nFAPI, OAI, etc.
            Convert the meeting transcript into well-structured meeting minutes in Markdown format.
            Include:
            - Meeting title
            - Date
            - Participants (if identifiable)
            - Summary
            - Key discussion points
            - Action items
            - Decisions made
            
            Output ONLY the Markdown content, do not wrap it in code blocks.
            """

            response = self.try_multiple_gemini_models(
                system_prompt,
                f"Meeting transcript:\n{transcript}"
            )
            
            meeting_notes = response.text
            logging.info("✅ Meeting notes generated successfully")
            return meeting_notes
            
        except Exception as e:
            logging.error(f"❌ Failed to generate meeting notes: {str(e)}")
            return f"# Meeting Minutes\n\nFailed to generate notes: {str(e)}\n\n## Raw Transcript\n{transcript}"

    def commit_to_github(self, content: str, filename: str) -> Dict[str, Any]:
        """Commit meeting minutes to GitHub repository"""
        logging.info(f"🔄 Committing to GitHub: {filename}")
        
        try:
            github_token = os.getenv("GITHUB_TOKEN")
            github_repo = os.getenv("GITHUB_REPO")  # e.g., "bmw-ece-ntust/ming-note"
            github_path = os.getenv("GITHUB_PATH", "notes/Meeting-Minutes")  # e.g., "notes/Meeting-Minutes"
            
            if not github_token or not github_repo:
                raise ValueError("Missing GITHUB_TOKEN or GITHUB_REPO environment variables")
            
            # GitHub API endpoint
            api_url = f"https://api.github.com/repos/{github_repo}/contents/{github_path}/{filename}"
            
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Check if file exists
            response = requests.get(api_url, headers=headers)
            
            # Prepare request body
            file_content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            data = {
                "message": f"Add meeting minutes: {filename}",
                "content": file_content_base64,
                "branch": os.getenv("GITHUB_BRANCH", "main")
            }
            
            # If file exists, include SHA for update
            if response.status_code == 200:
                existing_file = response.json()
                data["sha"] = existing_file["sha"]
                logging.info(f"📝 File exists, updating: {filename}")
            else:
                logging.info(f"📝 Creating new file: {filename}")
            
            # Create or update file
            result = requests.put(api_url, headers=headers, json=data)
            result.raise_for_status()
            
            response_data = result.json()
            file_url = response_data.get('content', {}).get('html_url', '')
            
            logging.info(f"✅ Successfully committed to GitHub: {file_url}")
            
            return {
                "success": True,
                "url": file_url,
                "filename": filename,
                "path": f"{github_path}/{filename}"
            }
            
        except Exception as e:
            logging.error(f"❌ Failed to commit to GitHub: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def process_audio(self, audio_path: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
        """Process audio: transcribe and perform speaker diarization"""
        logging.info(f"🔄 Processing audio: {os.path.basename(audio_path)}")
        
        self.load_models()
        
        # Convert to WAV if needed
        if not audio_path.lower().endswith('.wav'):
            wav_path = self.convert_to_wav(audio_path)
            os.remove(audio_path)
            audio_path = wav_path
        
        # Transcription
        logging.info("- Performing speech-to-text...")
        asr_result = self.whisper_model.transcribe(
            audio_path, 
            word_timestamps=False,
            verbose=False
        )
        
        # Speaker diarization
        logging.info("- Performing speaker diarization...")
        diarization = self.diarization_pipeline(audio_path)
        
        # Combine results
        logging.info("- Combining results...")
        segments = []
        original_speakers = set()
        
        for i, segment in enumerate(asr_result["segments"]):
            segment_start = segment["start"]
            segment_end = segment["end"]
            text = segment["text"].strip()
            
            # Find main speaker for this segment
            speakers = {}
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                overlap_start = max(segment_start, turn.start)
                overlap_end = min(segment_end, turn.end)
                
                if overlap_end > overlap_start:
                    overlap_duration = overlap_end - overlap_start
                    if speaker in speakers:
                        speakers[speaker] += overlap_duration
                    else:
                        speakers[speaker] = overlap_duration
            
            main_speaker = max(speakers.items(), key=lambda x: x[1])[0] if speakers else "Unknown"
            original_speakers.add(main_speaker)
            
            segment_data = {
                "speaker": main_speaker,
                "start": segment_start,
                "end": segment_end,
                "text": text
            }
            
            segments.append(segment_data)
        
        logging.info(f"✅ Audio processing complete, {len(segments)} segments")
        return "", segments, list(original_speakers)

    def create_job(self, job_id: str, file_id: str) -> Dict[str, Any]:
        """Create a new processing job"""
        job_data = {
            'id': job_id,
            'file_id': file_id,
            'status': JOB_STATUS['PENDING'],
            'progress': 0,
            'message': 'Job created, waiting for processing...',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        with self.jobs_lock:
            self.jobs[job_id] = job_data
            
        logging.info(f"✅ Job created: {job_id}")
        return job_data

    def process_file_async(self, job_id: str, file_id: str):
        """Async file processing"""
        future = self.executor.submit(self._process_file_job, job_id, file_id)
        
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id]['future'] = future
        
        return future

    def _process_file_job(self, job_id: str, file_id: str):
        """Background job for file processing"""
        audio_temp_dir = None

        try:
            logging.info(f"[Job {job_id}] 🎬 Starting processing")
            
            with self.jobs_lock:
                if job_id not in self.jobs:
                    logging.error(f"[Job {job_id}] ❌ Job not found")
                    return
            
            if self._is_job_cancelled(job_id):
                self._handle_job_cancellation(job_id)
                return
            
            # Update status
            self._update_job_progress(job_id, 5, '📥 Downloading file...')
            with self.jobs_lock:
                if job_id in self.jobs:
                    self.jobs[job_id]['status'] = JOB_STATUS['PROCESSING']
            
            # Download audio file
            audio_path, audio_temp_dir = self.download_from_drive(file_id)
            
            # Get original filename
            try:
                file_meta = self.drive_service.files().get(
                    fileId=file_id, fields="name"
                ).execute()
                original_filename = file_meta.get('name', '')
                logging.info(f"[Job {job_id}] 📄 Original filename: {original_filename}")
            except Exception as e:
                logging.error(f"[Job {job_id}] ❌ Failed to get filename: {e}")
                original_filename = ""
            
            # Process audio
            self._update_job_progress(job_id, 15, '🎤 Transcribing audio...')
            if self._is_job_cancelled(job_id):
                self._handle_job_cancellation(job_id)
                return
                
            _, segments, original_speakers = self.process_audio(audio_path)
            
            # Generate transcript
            self._update_job_progress(job_id, 70, '📝 Generating meeting notes...')
            if self._is_job_cancelled(job_id):
                self._handle_job_cancellation(job_id)
                return
            
            transcript = ""
            for seg in segments:
                transcript += f"[{seg['speaker']}]: {seg['text']}\n"
            
            # Generate meeting notes
            meeting_notes = self.generate_meeting_notes(transcript)
            
            # Commit to GitHub
            self._update_job_progress(job_id, 85, '📤 Committing to GitHub...')
            if self._is_job_cancelled(job_id):
                self._handle_job_cancellation(job_id)
                return
            
            # Generate filename
            current_date = datetime.now().strftime('%Y%m%d')
            github_filename = os.getenv("GITHUB_FILENAME_TEMPLATE", f"MM-{current_date}.md")
            # Replace date placeholder if exists
            github_filename = github_filename.replace("YYYYMMDD", current_date).replace("20251022", current_date)
            
            github_result = self.commit_to_github(meeting_notes, github_filename)
            
            # Complete
            result = {
                "success": github_result.get("success", False),
                "github_url": github_result.get("url", ""),
                "filename": github_result.get("filename", ""),
                "path": github_result.get("path", ""),
                "segments_count": len(segments),
                "speakers": list(original_speakers)
            }
            
            self._update_job_progress(job_id, 100, '✅ Processing complete!')
            with self.jobs_lock:
                self.jobs[job_id]['status'] = JOB_STATUS['COMPLETED']
                self.jobs[job_id]['result'] = result
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            logging.info(f"[Job {job_id}] ✅ Processing complete")
            return result

        except Exception as e:
            if self._is_job_cancelled(job_id):
                self._handle_job_cancellation(job_id)
                return
                
            logging.error(f"[Job {job_id}] ❌ Processing failed: {e}", exc_info=True)
            
            error_result = {
                "success": False,
                "error": str(e)
            }
            
            with self.jobs_lock:
                if job_id in self.jobs:
                    self.jobs[job_id]['status'] = JOB_STATUS['FAILED']
                    self.jobs[job_id]['progress'] = 100
                    self.jobs[job_id]['message'] = f'❌ Processing failed: {str(e)}'
                    self.jobs[job_id]['result'] = error_result
                    self.jobs[job_id]['error'] = str(e)
                    self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            return error_result

        finally:
            # Cleanup
            if audio_temp_dir and os.path.exists(audio_temp_dir):
                logging.info(f"[Job {job_id}] 🧹 Cleaning up temp directory")
                shutil.rmtree(audio_temp_dir)

    def _update_job_progress(self, job_id: str, progress: int, message: str):
        """Update job progress"""
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id]['progress'] = progress
                self.jobs[job_id]['message'] = message
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
        logging.info(f"[Job {job_id}] {progress}% - {message}")

    def _is_job_cancelled(self, job_id: str) -> bool:
        """Check if job is cancelled"""
        return job_id in self.cancelled_jobs

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a job"""
        with self.jobs_lock:
            job = self.jobs.get(job_id)
            
        if not job:
            return {'success': False, 'error': 'Job not found'}
        
        current_status = job['status']
        
        if current_status in ['completed', 'failed', 'cancelled']:
            return {'success': False, 'error': f'Job already {current_status}'}
        
        self.cancelled_jobs.add(job_id)
        
        with self.jobs_lock:
            if job_id in self.jobs and 'future' in self.jobs[job_id]:
                future = self.jobs[job_id]['future']
                if future and not future.done():
                    future.cancel()
        
        self._handle_job_cancellation(job_id)
        
        logging.info(f"[Job {job_id}] Job cancelled")
        return {'success': True, 'message': 'Job cancelled successfully'}

    def _handle_job_cancellation(self, job_id: str):
        """Handle job cancellation"""
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id]['status'] = 'cancelled'
                self.jobs[job_id]['progress'] = 100
                self.jobs[job_id]['message'] = 'Job cancelled by user'
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
                
                if 'future' in self.jobs[job_id]:
                    del self.jobs[job_id]['future']
        
        logging.info(f"[Job {job_id}] Job cancelled")

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status"""
        with self.jobs_lock:
            job = self.jobs.get(job_id)
            
        if not job:
            return {'error': 'Job not found'}
        
        result = {
            'id': job['id'],
            'status': job['status'],
            'progress': job['progress'],
            'message': job.get('message', ''),
            'created_at': job['created_at'],
            'updated_at': job['updated_at']
        }
        
        if job['status'] == JOB_STATUS['COMPLETED']:
            result['result'] = job.get('result')
        elif job['status'] == JOB_STATUS['FAILED']:
            result['error'] = job.get('error')
        
        return result

    def shutdown_executor(self):
        """Shutdown thread pool executor"""
        if hasattr(self, 'executor') and self.executor:
            logging.info("🔄 Shutting down executor...")
            try:
                self.executor.shutdown(wait=True)
                logging.info("✅ Executor shutdown complete")
            except Exception as e:
                logging.error(f"❌ Error shutting down executor: {e}")
