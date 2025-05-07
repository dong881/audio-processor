import os
import sys
import tempfile
import shutil
import subprocess
import logging
import uuid
import threading
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# 語音處理相關
import whisper
from pyannote.audio import Pipeline
import numpy as np
import soundfile as sf
import librosa

# 導入專用模組
from .google_service import GoogleService
from note_handler import NoteHandler

class AudioProcessor:
    """
    音頻處理核心類別，負責音頻轉換、處理、識別及工作流程協調
    採用單例模式確保全應用統一處理狀態
    """
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """單例模式獲取實例"""
        if cls._instance is None:
            # 確保相依的類別存在
            from notion_formatter import NotionFormatter
            note_handler = NoteHandler(NotionFormatter())
            cls._instance = AudioProcessor(note_handler=note_handler)
        return cls._instance
    
    def __init__(self, note_handler, max_workers=3):
        """
        初始化處理器
        
        Args:
            note_handler: 處理摘要、筆記和 Notion 整合的處理器
            max_workers: 同時處理的最大工作數
        """
        # 存儲單例實例
        AudioProcessor._instance = self
        
        # 模型實例
        self.whisper_model = None
        self.diarization_pipeline = None
        
        # 工作管理相關
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        
        # 依賴的服務
        self.note_handler = note_handler
        self.google_service = GoogleService()
        
        # 工作狀態常量
        self.JOB_STATUS = {
            'PENDING': 'pending',      # 等待處理
            'PROCESSING': 'processing', # 處理中
            'COMPLETED': 'completed',   # 處理完成
            'FAILED': 'failed'         # 處理失敗
        }
        
    def load_models(self):
        """載入 AI 模型，包括語音轉文字和說話人分離"""
        try:
            logging.info("🔄 載入語音處理模型...")
            
            # 載入 Whisper 模型
            if self.whisper_model is None:
                model_size = os.getenv("WHISPER_MODEL_SIZE", "medium")
                logging.info(f"- 載入 Whisper {model_size} 模型...")
                self.whisper_model = whisper.load_model(model_size)
                logging.info("✅ Whisper 模型載入完成")
            
            # 載入說話人分離模型
            if self.diarization_pipeline is None:
                hf_token = os.getenv("HF_TOKEN")
                if not hf_token:
                    raise ValueError("未設置 HF_TOKEN 環境變數，無法載入說話人分離模型")
                
                # 添加重試邏輯，避免網路問題
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        logging.info(f"- 載入說話人分離模型 (嘗試 {attempt + 1}/{max_retries})...")
                        self.diarization_pipeline = Pipeline.from_pretrained(
                            "pyannote/speaker-diarization-3.1",
                            use_auth_token=hf_token
                        )
                        logging.info("✅ 說話人分離模型載入完成")
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logging.warning(f"⚠️ 載入說話人分離模型失敗，將重試: {str(e)}")
                            time.sleep(2)  # 等待後重試
                        else:
                            logging.error(f"❌ 載入說話人分離模型失敗: {str(e)}")
                            raise
                            
            logging.info("✅ 所有模型載入完成")
            return True
            
        except Exception as e:
            logging.error(f"❌ 載入模型失敗: {str(e)}", exc_info=True)
            raise
    
    def convert_to_wav(self, input_path: str) -> str:
        """
        將音檔轉換為 WAV 格式 (16kHz, 單聲道)
        
        Args:
            input_path: 輸入檔案路徑
            
        Returns:
            轉換後 WAV 檔案的路徑
        """
        # 如果已經是 WAV 檔案，直接返回
        if input_path.lower().endswith(".wav"):
            return input_path
            
        logging.info(f"🔄 轉換音頻格式: {os.path.basename(input_path)}")
        
        # 創建臨時目錄
        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, "converted.wav")
        
        try:
            # 使用 FFmpeg 轉換
            cmd = [
                "ffmpeg",
                "-y",                   # 覆蓋輸出檔案
                "-i", input_path,       # 輸入檔案
                "-ar", "16000",         # 取樣率：16kHz
                "-ac", "1",             # 聲道數：1 (單聲道)
                "-c:a", "pcm_s16le",    # 編碼：16-bit PCM
                output_path             # 輸出檔案
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                logging.error(f"❌ FFmpeg 轉換失敗: {result.stderr}")
                raise RuntimeError(f"FFmpeg 轉換失敗: {result.stderr}")
            
            logging.info("✅ 格式轉換完成")
            return output_path
            
        except Exception as e:
            logging.error(f"❌ 檔案轉換失敗: {str(e)}", exc_info=True)
            # 清理臨時目錄
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
            raise
    
    def remove_silence(self, audio_path: str) -> str:
        """
        移除音檔中的靜音部分，優化處理效率
        
        Args:
            audio_path: 輸入音頻檔案路徑
            
        Returns:
            處理後檔案路徑
        """
        logging.info(f"🔄 移除音檔中的靜音: {os.path.basename(audio_path)}")
        
        try:
            # 載入音頻
            y, sr = librosa.load(audio_path, sr=None)
            
            # 檢測非靜音部分
            non_silent_intervals = librosa.effects.split(
                y, top_db=30, frame_length=2048, hop_length=512
            )
            
            if len(non_silent_intervals) == 0:
                logging.warning("⚠️ 找不到非靜音部分，返回原始檔案")
                return audio_path
            
            # 合併非靜音部分
            y_trimmed = np.concatenate([y[start:end] for start, end in non_silent_intervals])
            
            # 生成輸出路徑
            output_dir = os.path.dirname(audio_path)
            output_path = os.path.join(output_dir, "trimmed.wav")
            
            # 儲存處理後的檔案
            sf.write(output_path, y_trimmed, sr)
            
            # 計算縮減比例
            reduction = (1 - len(y_trimmed) / len(y)) * 100
            logging.info(f"✅ 靜音移除完成，檔案縮減 {reduction:.1f}%")
            
            return output_path
            
        except Exception as e:
            logging.error(f"❌ 移除靜音失敗: {str(e)}", exc_info=True)
            return audio_path  # 錯誤時返回原始檔案
    
    def process_audio(self, audio_path: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
        """
        處理音頻檔案，執行轉錄與說話人分離
        
        Args:
            audio_path: 音頻檔案路徑
            
        Returns:
            Tuple[str, List[Dict], List[str]]: 包含完整文本、分段內容與說話人列表的元組
        """
        logging.info(f"🔄 處理音頻檔案: {os.path.basename(audio_path)}")
        
        # 確保模型已載入
        if not self.whisper_model or not self.diarization_pipeline:
            self.load_models()
        
        # 檢查文件是否存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"找不到音頻檔案: {audio_path}")
            
        try:
            # 預處理音頻
            if not audio_path.lower().endswith('.wav'):
                wav_path = self.convert_to_wav(audio_path)
                # 處理完成後移除原始檔案以節省空間
                if wav_path != audio_path and os.path.exists(audio_path):
                    os.unlink(audio_path)
                audio_path = wav_path
            
            # 移除靜音（可選）
            if os.getenv("REMOVE_SILENCE", "true").lower() == "true":
                audio_path = self.remove_silence(audio_path)
            
            # 語音轉文字
            logging.info("- 執行語音轉文字...")
            transcription = self.whisper_model.transcribe(
                audio_path, 
                language=os.getenv("WHISPER_LANGUAGE", None),
                verbose=False
            )
            
            # 說話人分離
            logging.info("- 執行說話人分離...")
            diarization = self.diarization_pipeline(audio_path)
            
            # 整合結果
            segments = []
            full_transcript = ""
            speaker_set = set()
            
            # 處理每個段落
            for i, segment in enumerate(transcription["segments"]):
                segment_start = segment["start"]
                segment_end = segment["end"]
                text = segment["text"].strip()
                
                # 找出此段落的主要說話人
                speakers = {}
                for turn, _, speaker in diarization.itertracks(yield_label=True):
                    # 計算重疊時間
                    overlap_start = max(segment_start, turn.start)
                    overlap_end = min(segment_end, turn.end)
                    
                    if overlap_end > overlap_start:  # 有重疊
                        overlap_duration = overlap_end - overlap_start
                        speakers[speaker] = speakers.get(speaker, 0) + overlap_duration
                
                # 找出主要說話人
                main_speaker = max(speakers.items(), key=lambda x: x[1])[0] if speakers else "未知"
                speaker_set.add(main_speaker)
                
                # 添加到結果
                segments.append({
                    "speaker": main_speaker,
                    "start": segment_start,
                    "end": segment_end,
                    "text": text,
                    "timestamp": self.format_timestamp(segment_start)
                })
                
                full_transcript += f"[{main_speaker}]: {text}\n"
            
            logging.info(f"✅ 音頻處理完成: {len(segments)} 個段落，{len(speaker_set)} 位說話人")
            return full_transcript, segments, list(speaker_set)
            
        except Exception as e:
            logging.error(f"❌ 音頻處理失敗: {str(e)}", exc_info=True)
            raise
    
    def process_file_async(self, file_id: str, attachment_file_id: Optional[str] = None) -> str:
        """
        非同步處理檔案，返回工作 ID
        
        Args:
            file_id: Google Drive 檔案 ID
            attachment_file_id: 可選的附件檔案 ID (如 PDF)
            
        Returns:
            工作 ID
        """
        # 生成唯一工作 ID
        job_id = str(uuid.uuid4())
        
        # 初始化工作資訊
        with self.jobs_lock:
            self.jobs[job_id] = {
                'id': job_id,
                'file_id': file_id,
                'attachment_file_id': attachment_file_id,
                'status': self.JOB_STATUS['PENDING'],
                'progress': 0,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'result': None,
                'error': None,
                'message': '工作已加入隊列，等待處理'
            }
        
        # 提交工作到執行緒池
        self.executor.submit(
            self._process_file_job, job_id, file_id, attachment_file_id
        )
        
        return job_id
    
    def _process_file_job(self, job_id: str, file_id: str, attachment_file_id: Optional[str] = None):
        """
        處理檔案的背景工作
        
        Args:
            job_id: 工作ID
            file_id: Google Drive 檔案ID
            attachment_file_id: 附件檔案ID (如 PDF)
        """
        audio_temp_dir = None
        attachment_temp_dir = None
        attachment_text = None
        
        # 更新工作狀態
        self._update_job_status(job_id, status=self.JOB_STATUS['PROCESSING'], 
                               progress=5, message="開始處理檔案")
        
        try:
            logging.info(f"[Job {job_id}] 開始處理檔案，ID: {file_id}")
            
            # 獲取檔案資訊
            try:
                file_details = self.google_service.get_file_details(file_id)
                file_name = file_details.get('name', f"file_{file_id}")
                
                self._update_job_status(job_id, progress=10, 
                                       message=f"處理檔案: {file_name}")
            except Exception as e:
                logging.error(f"[Job {job_id}] ❌ 獲取檔案資訊失敗: {str(e)}")
                self._update_job_status(job_id, message=f"獲取檔案資訊失敗: {str(e)}")
                file_name = f"file_{file_id}"
            
            # 處