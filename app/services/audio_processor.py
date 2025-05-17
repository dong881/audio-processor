import os
import sys
import tempfile
import shutil
import subprocess
import io
import json
import re
import time
import logging
import uuid
import threading
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import requests
import atexit

# Google API 相關
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 語音處理相關
import whisper
from pyannote.audio import Pipeline
import numpy as np
import soundfile as sf
import librosa

# LLM API 相關
import google.generativeai as genai

# 添加導入 NotionFormatter
from ..utils.notion_formatter import NotionFormatter

# PDF 處理 (需要 pip install PyPDF2)
try:
    import PyPDF2
except ImportError:
    print("⚠️ PyPDF2 未安裝，無法處理 PDF 附件。請執行 'pip install PyPDF2'")
    PyPDF2 = None

# 導入工作狀態常數
from app.utils.constants import JOB_STATUS


class AudioProcessor:
    def __init__(self, max_workers=3):
        self.whisper_model = None
        self.diarization_pipeline = None
        self.drive_service = None
        self.oauth_drive_service = None  # 專門用於OAuth認證的Drive服務
        
        # 初始化執行緒池
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        # 註冊 executor 關閉函數
        atexit.register(self.shutdown_executor)
        # 工作狀態追蹤
        self.jobs = {}
        # 確保線程安全的鎖
        self.jobs_lock = threading.Lock()
        # 初始化 Notion 格式化工具
        self.notion_formatter = NotionFormatter()
        # 初始化服務
        self.init_services()

    def init_services(self):
        """初始化所有需要的服務"""
        logging.info("🔄 初始化服務中...")
        
        # 獲取服務帳號路徑
        sa_json_path = os.getenv("GOOGLE_SA_JSON_PATH", "credentials/service-account.json")
        client_secret_path = os.getenv("GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json")
        
        # 初始化服務帳號認證的Drive API (用於下載檔案)
        try:
            # 檢查服務帳號文件路徑
            if not os.path.isabs(sa_json_path):
                # 如果是相對路徑，先嘗試相對於當前工作目錄
                if os.path.exists(sa_json_path):
                    sa_json_path = os.path.abspath(sa_json_path)
                # 再嘗試相對於應用根目錄
                elif os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), sa_json_path)):
                    sa_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), sa_json_path)
                
            # 確認服務帳號文件存在
            if not os.path.exists(sa_json_path):
                logging.error(f"❌ 找不到服務帳號文件: {sa_json_path}")
                # 嘗試使用預設路徑
                alternative_paths = [
                    "/app/credentials/service-account.json",
                    "./credentials/service-account.json",
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "credentials/service-account.json")
                ]
                
                for path in alternative_paths:
                    if os.path.exists(path):
                        logging.info(f"✅ 找到替代服務帳號路徑: {path}")
                        sa_json_path = path
                        break
                else:
                    raise FileNotFoundError(f"無法找到服務帳號JSON檔案，已嘗試的路徑: {sa_json_path} 和 {alternative_paths}")
                
            # 使用服務帳號
            logging.info(f"🔄 正在使用服務帳號文件: {sa_json_path}")
            service_credentials = service_account.Credentials.from_service_account_file(
                sa_json_path,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            self.drive_service = build('drive', 'v3', credentials=service_credentials)
            logging.info("✅ 使用服務帳號初始化 Drive API 成功")
        except Exception as e:
            logging.error(f"❌ 初始化服務帳號 Google Drive API 失敗: {str(e)}")
            self.drive_service = None
        
        # 初始化 Google Gemini API
        try:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if not gemini_api_key:
                logging.warning("⚠️ 未設置GEMINI_API_KEY環境變量，某些功能將無法使用")
            else:
                genai.configure(api_key=gemini_api_key)
                logging.info("✅ 初始化 Gemini API 成功")
        except Exception as e:
            logging.error(f"❌ 初始化 Gemini API 失敗: {str(e)}")
        
        logging.info("✅ 服務初始化完成")
    
    def set_oauth_credentials(self, credentials):
        """設置OAuth憑證並初始化Drive服務，但不寫入文件"""
        try:
            # 直接使用提供的憑證來建立oauth_drive_service
            # 不再寫入憑證到文件系統
            self.oauth_drive_service = build('drive', 'v3', credentials=credentials)
            logging.info("✅ 使用OAuth憑證初始化Drive API成功")
            
            # 記錄憑證的有效期限
            if hasattr(credentials, 'expiry'):
                expiry_time = credentials.expiry.strftime('%Y-%m-%d %H:%M:%S') if credentials.expiry else "未知"
                logging.info(f"📝 OAuth憑證有效期至: {expiry_time}")
                
            return True
        except Exception as e:
            logging.error(f"❌ 使用OAuth憑證初始化Drive API失敗: {str(e)}")
            self.oauth_drive_service = None
            return False

    def download_file(self, file_id: str, target_dir: str) -> str: # Returns filename
        """從 Google Drive 下載檔案到指定的目標目錄 (使用服務帳號)"""
        logging.info(f"🔄 從 Google Drive 下載檔案 (ID: {file_id}) 到目錄 {target_dir}")
        
        try:
            if not self.drive_service:
                raise RuntimeError("服務帳號 Drive API 未初始化，無法下載檔案")
            
            # Ensure target_dir exists
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
                    # logging.debug(f"下載進度: {int(status.progress() * 100)}%") # Can be verbose
            
            logging.info(f"✅ 檔案下載完成: {safe_file_name} (儲存於 {target_dir})")
            return safe_file_name # Return just the filename
            
        except Exception as e:
            logging.error(f"❌ 下載檔案 ID {file_id} 到 {target_dir} 失敗: {str(e)}")
            raise

    def download_from_drive(self, file_id: str) -> Tuple[str, str]:
        """從 Google Drive 下載檔案到臨時目錄 (使用服務帳號)"""
        logging.info(f"🔄 從 Google Drive 下載檔案 (ID: {file_id})")
        
        try:
            # 確保服務帳號已經初始化
            if not self.drive_service:
                raise RuntimeError("服務帳號 Drive API 未初始化，無法下載檔案")
            
            # 建立臨時目錄
            temp_dir = tempfile.mkdtemp()
            
            # 獲取文件資訊
            file_meta = self.drive_service.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            
            # 獲取檔案名稱並清理不安全的字元
            raw_file_name = file_meta.get('name', f"file_{file_id}")
            # 移除斜線等不安全字元，避免路徑問題
            safe_file_name = re.sub(r'[\\/*?:"<>|]', "_", raw_file_name)
            local_path = os.path.join(temp_dir, safe_file_name)
            
            # 下載檔案
            request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    logging.debug(f"下載進度: {int(status.progress() * 100)}%")
            
            logging.info(f"✅ 檔案下載完成: {safe_file_name} (儲存於 {temp_dir})")
            return local_path, temp_dir
            
        except Exception as e:
            logging.error(f"❌ 下載檔案失敗: {str(e)}")
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise
    
    def list_drive_files(self, query="trashed = false and (mimeType contains 'audio/' or mimeType = 'application/pdf')"):
        """列出Google Drive檔案 (使用OAuth認證)"""
        logging.info(f"🔄 使用OAuth憑證列出Google Drive檔案")

        if not self.oauth_drive_service:
            logging.error("❌ OAuth Drive服務未初始化，無法取得檔案列表")
            return []

        try:
            # 執行查詢，取得檔案 ID、名稱、MIME 類型、大小與父資料夾
            results = self.oauth_drive_service.files().list(
                q=query,
                spaces='drive',
                fields="files(id, name, mimeType, size, parents)",
                orderBy="modifiedTime desc"
            ).execute()

            files = results.get('files', [])
            logging.info(f"✅ 已成功獲取 {len(files)} 個檔案")
            return files
        except Exception as e:
            logging.error(f"❌ 列出Google Drive檔案失敗: {str(e)}")
            return []

    def find_folder_id_by_path(self, folder_path: str) -> Optional[str]:
        """
        根據多層資料夾名稱（如 'WearNote_Recordings/Documents'）遞迴查找最終資料夾ID。
        """
        if not self.oauth_drive_service:
            return None
        names = folder_path.strip('/').split('/')
        parent_id = 'root'
        for name in names:
            results = self.oauth_drive_service.files().list(
                q=f"trashed = false and mimeType = 'application/vnd.google-apps.folder' and name = '{name}' and '{parent_id}' in parents",
                spaces='drive',
                fields="files(id, name)",
                pageSize=10
            ).execute()
            folders = results.get('files', [])
            if not folders:
                return None
            parent_id = folders[0]['id']
        return parent_id

    def download_and_extract_text(self, file_id: str) -> Tuple[Optional[str], Optional[str]]:
        """下載並提取 PDF 文字內容 (使用服務帳號)"""
        try:
            # 獲取文件資訊
            file_meta = self.drive_service.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            
            mime_type = file_meta.get('mimeType', '')
            
            # 目前僅支持 PDF
            if mime_type != 'application/pdf' or PyPDF2 is None:
                return None, None
            
            # 下載文件
            local_path, temp_dir = self.download_from_drive(file_id)
            
            # 提取 PDF 文字
            text = ""
            with open(local_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text()
            
            return text, temp_dir
        except Exception as e:
            logging.error(f"❌ 提取PDF文字失敗: {str(e)}")
            if 'temp_dir' in locals() and temp_dir:
                return None, temp_dir
            return None, None

    def preprocess_audio(self, audio_path: str) -> str:
        """預處理音頻 (僅確保格式正確)"""
        logging.info(f"🔄 預處理音頻: {os.path.basename(audio_path)}")
        
        # 確保檔案為 WAV 格式
        if not audio_path.lower().endswith('.wav'):
            audio_path = self.convert_to_wav(audio_path)
        
        logging.info(f"✅ 音頻預處理完成")
        return audio_path

    def rename_drive_file(self, file_id: str, new_name: str) -> bool:
        """根據處理結果重命名 Google Drive 上的檔案 (使用服務帳號)"""
        try:
            if not self.drive_service:
                raise RuntimeError("服務帳號 Drive API 未初始化，無法重命名檔案")
                
            self.drive_service.files().update(
                fileId=file_id,
                body={'name': new_name}
            ).execute()
            logging.info(f"✅ 成功重命名 Google Drive 檔案: {new_name}")
            return True
        except Exception as e:
            logging.error(f"❌ 重命名 Google Drive 檔案失敗: {str(e)}")
            return False
        
    def format_timestamp(self, seconds: float) -> str:
            """將秒數轉換為可讀時間戳記"""
            minutes, seconds = divmod(int(seconds), 60)
            hours, minutes = divmod(minutes, 60)
            
            if hours > 0:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                return f"{minutes:02d}:{seconds:02d}"
            
    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """從檔案名稱中提取日期，支援多種格式"""
        # 嘗試匹配 REC_YYYYMMDD_HHMMSS 格式
        pattern1 = r'REC_(\d{8})_\d+'
        match1 = re.search(pattern1, filename)
        if match1:
            date_str = match1.group(1)
            try:
                # 將 YYYYMMDD 轉換為 YYYY-MM-DD
                date_obj = datetime.strptime(date_str, '%Y%m%d')
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        # 嘗試匹配已有的 [YYYY-MM-DD] 格式
        pattern2 = r'\[(\d{4}-\d{2}-\d{2})\]'
        match2 = re.search(pattern2, filename)
        if match2:
            return match2.group(1)
            
        # 嘗試匹配其他可能的日期格式 (YYYY-MM-DD)
        pattern3 = r'(\d{4}-\d{2}-\d{2})'
        match3 = re.search(pattern3, filename)
        if match3:
            return match3.group(1)
            
        # 如果都無法匹配，返回 None
        return None

    def get_file_folder_path(self, file_id):
        """獲取檔案所在的完整資料夾路徑"""
        try:
            if not self.oauth_drive_service:
                logging.error("未初始化 Drive 服務，無法獲取資料夾路徑")
                return ""
            
            # 獲取檔案元數據以找到父資料夾ID
            file = self.oauth_drive_service.files().get(
                fileId=file_id, 
                fields="parents"
            ).execute()
            
            if not file.get('parents'):
                return "root"
            
            # 構建資料夾路徑
            path = []
            parent_id = file['parents'][0]
            
            # 向上尋找父資料夾直到根目錄
            max_depth = 10  # 防止無限循環
            depth = 0
            
            while parent_id and depth < max_depth:
                try:
                    parent = self.oauth_drive_service.files().get(
                        fileId=parent_id,
                        fields="id,name,parents"
                    ).execute()
                    
                    path.insert(0, parent.get('name', 'unknown'))
                    
                    # 檢查是否有父資料夾
                    if 'parents' in parent and parent['parents']:
                        parent_id = parent['parents'][0]
                    else:
                        break
                        
                    depth += 1
                    
                except Exception as e:
                    logging.error(f"獲取父資料夾資訊失敗: {e}")
                    break
            
            # 返回由 / 連接的資料夾路徑
            return "/".join(path)
            
        except Exception as e:
            logging.error(f"獲取檔案資料夾路徑失敗: {e}")
            return ""

    def try_multiple_gemini_models(self, system_prompt: str, user_content: str, 
                                models: List[str] = None) -> Any:
        """Try generating content using multiple Gemini models until one succeeds.
        
        Args:
            system_prompt: The system instructions for the model
            user_content: The user content to process
            models: List of model names to try in order (uses default list if None)
            
        Returns:
            The successful generation response
            
        Raises:
            Exception: If all models fail
        """
        # Default models list if none provided
        if models is None:
            models = ['gemini-2.5-pro-exp-03-25', 'gemini-2.5-flash-preview-04-17',
                        'gemini-1.5-pro', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.0-flash-lite']
        
        response = None
        last_error = None

        # Try different models until successful
        for model_name in models:
            try:
                logging.info(f"🔄 使用模型: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    [system_prompt, user_content]
                )
                # If successful, break the loop
                logging.info(f"✅ 成功使用模型 {model_name} 生成筆記")
                break
            except Exception as e:
                last_error = e
                # Check if quota error
                if "429" in str(e) or "quota" in str(e).lower():
                    # Extract and log the quota documentation URL
                    url_match = re.search(r'https?://\S+', str(e))
                    logging.warning(f"⚠️ 模型 {model_name} 配額已用盡: {url_match.group(0)}")
                    # Continue to next model
                    continue
                else:
                    # Raise other errors
                    logging.error(f"❌ 使用模型 {model_name} 時發生錯誤: {str(e)}")
                    raise

        # Check if all models failed
        if response is None:
            logging.error("❌ 所有模型都失敗了")
            raise last_error
        
        return response

    def generate_comprehensive_notes(self, transcript: str) -> str:
        """使用 Gemini API 生成結構化的筆記"""
        logging.info("🔄 生成筆記...")
        
        try:
            # 使用更詳細的Markdown格式指示
            system_prompt = """
            你具備電子工程通訊相關背景，能夠理解技術性內容(包括一些常聽到的socket, RIC, gNB, nFAPI, OAI等術語)。
            將錄音逐字稿整理成筆記內容，請使用Markdown格式直接輸出筆記內容:
            避免使用```markdown```，直接輸出Markdown格式的筆記內容。
            """

            # Use the function in generate_comprehensive_notes
            response = self.try_multiple_gemini_models(
                system_prompt,
                f"會議逐字稿：\n{transcript}"
            )
            
            comprehensive_notes = response.text
            logging.info("✅ 筆記生成成功")
            return comprehensive_notes
            
        except Exception as e:
            logging.error(f"❌ 筆記生成失敗: {str(e)}")
            return "筆記生成失敗，請參考會議摘要和完整記錄。"

    def create_notion_page(self, title: str, summary: str, todos: List[str], segments: List[Dict[str, Any]], speaker_map: Dict[str, str], file_id: str = None) -> Tuple[str, str]:
        """建立單一 Notion 頁面，包含標題、日期、參與者、摘要、待辦事項、完整筆記與內嵌的逐字稿"""
        logging.info("🔄 建立 Notion 頁面...")

        notion_token = os.getenv("NOTION_TOKEN")
        database_id = os.getenv("NOTION_DATABASE_ID")

        if not notion_token or not database_id:
            raise ValueError("缺少 Notion API 設定")

        # --- 準備頁面內容區塊 ---
        blocks = []
        
        # 從檔案名稱提取日期或使用當前日期
        current_date = datetime.now()
        current_date_str = current_date.strftime("%Y-%m-%d")
        
        # 嘗試從檔案ID獲取檔案名稱並提取日期
        file_date = None
        if file_id:
            try:
                file_meta = self.drive_service.files().get(
                    fileId=file_id, fields="name"
                ).execute()
                filename = file_meta.get('name', '')
                if filename:
                    file_date = self.extract_date_from_filename(filename)
            except Exception as e:
                logging.error(f"❌ 獲取檔案日期失敗: {str(e)}")
        
        # 使用檔案日期或當前日期
        date_str = file_date if file_date else current_date_str
        formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y年%m月%d日")

        # --- 標題區塊 (使用日期+錄音檔案名稱) ---
        page_title = f"{formatted_date} {title}"

        # --- 日期區塊 ---
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "📅 日期"}}]
            }
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": formatted_date}}]
            }
        })

        blocks.append({"object": "block", "type": "divider", "divider": {}})
        # --- 參與者區塊 ---
        participants = list(set(speaker_map.values()))  # 獲取唯一識別的名稱
        if participants:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "👥 參與者"}}]
                }
            })
            participant_text = ", ".join(participants)
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": participant_text}}]
                }
            })
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # --- 摘要區塊 ---
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📝 摘要"}}]
            }
        })
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": summary}}],
                "icon": {"emoji": "💡"}
            }
        })
        blocks.append({"object": "block", "type": "divider", "divider": {}})

        # --- 待辦事項區塊 ---
        if todos:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "✅ 待辦事項"}}]
                }
            })
            
            # 使用 todo list 呈現待辦事項
            todo_blocks = []
            for todo in todos:
                todo_blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": todo}}],
                        "checked": False
                    }
                })
            
            blocks.extend(todo_blocks)
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # --- 處理完整逐字稿 (無時間戳記) ---
        full_transcript = ""
        
        for segment in segments:
            speaker = segment["speaker"]
            text = segment["text"]
            content = f"{speaker}: {text}"
            full_transcript += f"{content}\n"

        # --- 生成完整筆記 ---
        comprehensive_notes = self.generate_comprehensive_notes(full_transcript)
        
        # --- 完整筆記區塊 ---
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📊 詳細筆記"}}]
            }
        })
        
        # Notion API 限制：每次請求最多 100 個區塊
        MAX_BLOCKS_PER_REQUEST = 90  # 使用 90 作為安全界限
        
        # 使用 NotionFormatter 來處理筆記
        note_blocks = self.notion_formatter.process_note_format_for_notion(comprehensive_notes)
        
        # 計算已有區塊數
        base_blocks_count = len(blocks)
        available_slots = MAX_BLOCKS_PER_REQUEST - base_blocks_count
        
        # 如果筆記區塊太多，僅添加能容納的部分
        if len(note_blocks) > available_slots:
            blocks.extend(note_blocks[:available_slots])
            remaining_note_blocks = note_blocks[available_slots:]
        else:
            blocks.extend(note_blocks)
            remaining_note_blocks = []
        
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

        try:
            # 建立主頁面 (包含所有基本信息)
            data = {
                "parent": {"database_id": database_id},
                "properties": {
                    "title": {
                        "title": [{"text": {"content": page_title}}]
                    }
                },
                "children": blocks
            }
            
            logging.info(f"- 建立 Notion 頁面 (包含 {len(blocks)} 個區塊，限制為 100)")
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            result = response.json()
            page_id = result["id"]
            page_url = result.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")
            
            # 將逐字稿分成多個段落 (因為 Notion API 有字符限制)
            remaining_note_blocks.append({"object": "block", "type": "divider", "divider": {}})

            # --- 內嵌完整逐字稿區塊 (使用 toggle 區塊) ---
            remaining_note_blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "🎙️ 完整逐字稿"}}]
                }
            })
            
            # 使用 NotionFormatter 的 split_transcript_into_blocks 獲取逐字稿區塊
            transcript_blocks = self.notion_formatter.split_transcript_into_blocks(full_transcript)
            
            # 建立音頻檔案連結區塊
            audio_link_blocks = []
            if file_id:
                try:
                    file_info = self.drive_service.files().get(
                        fileId=file_id, fields="name,webViewLink"
                    ).execute()
                    file_name = file_info.get('name', '音頻檔案')
                    file_link = file_info.get('webViewLink', f"https://drive.google.com/file/d/{file_id}/view")
                    
                    audio_link_blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": "📁 錄音檔案: "}},
                                {"type": "text", "text": {"content": file_name, "link": {"url": file_link}}}
                            ]
                        }
                    })
                    audio_link_blocks.append({"object": "block", "type": "divider", "divider": {}})
                except Exception as e:
                    logging.error(f"❌ 獲取檔案連結失敗: {str(e)}")
            
            # 添加檔案連結到 remaining_note_blocks
            remaining_note_blocks.extend(audio_link_blocks)
            
            # 計算每個 toggle 區塊最多可以包含的 transcript_blocks 數量 (最大100個)
            MAX_TOGGLE_CHILDREN = 90  # 保留一些空間給其他元素
            
            # 分割 transcript_blocks 為多個 toggle 區塊
            for i in range(0, len(transcript_blocks), MAX_TOGGLE_CHILDREN):
                toggle_children = []
                end_idx = min(i + MAX_TOGGLE_CHILDREN, len(transcript_blocks))
                
                # 只在第一個 toggle 區塊添加說明文字
                if i == 0:
                    toggle_children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": "此區塊包含完整逐字稿內容"}}]
                        }
                    })
                    toggle_children.append({
                        "object": "block",
                        "type": "divider",
                        "divider": {}
                    })
                
                # 添加本批次的 transcript_blocks
                toggle_children.extend(transcript_blocks[i:end_idx])
                
                # 建立目前批次的 toggle 區塊
                toggle_title = "點擊展開完整逐字稿"
                if i > 0:  # 如果不是第一個 toggle，添加序號
                    part_num = (i // MAX_TOGGLE_CHILDREN) + 1
                    total_parts = (len(transcript_blocks) + MAX_TOGGLE_CHILDREN - 1) // MAX_TOGGLE_CHILDREN
                    toggle_title = f"點擊展開完整逐字稿 (第 {part_num}/{total_parts} 部分)"
                
                remaining_note_blocks.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": toggle_title}}],
                        "children": toggle_children
                    }
                })
            
            total_batches = (len(remaining_note_blocks) + MAX_BLOCKS_PER_REQUEST - 1) // MAX_BLOCKS_PER_REQUEST
            logging.info(f"- 開始分批添加逐字稿內容 (共 {len(remaining_note_blocks)} 段，分 {total_batches} 批)")

            # Validate Notion token before making requests
            if not notion_token or notion_token.strip() == "":
                raise ValueError("無效的 Notion API Token")

            # Add retry logic for batch additions
            for i in range(0, len(remaining_note_blocks), MAX_BLOCKS_PER_REQUEST):
                end_idx = min(i + MAX_BLOCKS_PER_REQUEST, len(remaining_note_blocks))
                batch_num = i // MAX_BLOCKS_PER_REQUEST + 1
                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        logging.info(f"- 添加第 {batch_num}/{total_batches} 批逐字稿內容 (第 {retry_count + 1} 次嘗試)")
                        transcript_blocks_response = requests.patch(
                            f"https://api.notion.com/v1/blocks/{page_id}/children",
                            headers=headers,
                            json={"children": remaining_note_blocks[i:end_idx]},
                            timeout=30  # Add timeout to prevent hanging requests
                        )
                        
                        if transcript_blocks_response.status_code in [401, 403]:
                            logging.error(f"❌ 認證錯誤 (狀態碼: {transcript_blocks_response.status_code}): 請確認 Notion API Token 有效")
                            try:
                                error_details = transcript_blocks_response.json()
                                logging.error(f"   詳細錯誤: {json.dumps(error_details, indent=2, ensure_ascii=False)}")
                            except:
                                logging.error(f"   回應內容: {transcript_blocks_response.text}")
                            break  # Authentication errors won't be fixed by retrying
                            
                        transcript_blocks_response.raise_for_status()
                        logging.info(f"✅ 第 {batch_num}/{total_batches} 批逐字稿內容添加成功")
                        break  # Success - exit retry loop
                        
                    except requests.exceptions.RequestException as e:
                        retry_count += 1
                        logging.warning(f"⚠️ 第 {batch_num}/{total_batches} 批逐字稿添加失敗 (嘗試 {retry_count}/{max_retries}): {e}")
                        
                        # Check specific error types
                        if hasattr(e, 'response') and e.response is not None:
                            try:
                                err_details = e.response.json()
                                logging.error(f"   錯誤詳情: {json.dumps(err_details, indent=2, ensure_ascii=False)}")
                                
                                # Check for specific Notion API errors
                                if 'message' in err_details and 'block contents are invalid' in err_details['message'].lower():
                                    logging.error("   可能存在無效的區塊內容，嘗試簡化處理...")
                                    # Simplify blocks if needed in future iterations
                                
                            except json.JSONDecodeError:
                                logging.error(f"   響應內容 (非 JSON): {e.response.text}")
                        
                        if retry_count < max_retries:
                            wait_time = 2 ** retry_count  # Exponential backoff
                            logging.info(f"   等待 {wait_time} 秒後重試...")
                            time.sleep(wait_time)
                        else:
                            logging.error(f"❌ 第 {batch_num}/{total_batches} 批逐字稿添加失敗，已達最大重試次數")
                
                # Add a small delay between batches to avoid rate limiting
                if i + MAX_BLOCKS_PER_REQUEST < len(remaining_note_blocks) and retry_count < max_retries:
                    time.sleep(1)
            
            logging.info(f"✅ Notion 頁面建立成功 (ID: {page_id}, URL: {page_url})")
            return page_id, page_url
            
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Notion API 請求失敗: {e}", exc_info=True)
            if e.response is not None:
                try:
                    err_details = e.response.json()
                    logging.error(f"   錯誤碼: {e.response.status_code}, 訊息: {json.dumps(err_details, indent=2, ensure_ascii=False)}")
                except json.JSONDecodeError:
                    logging.error(f"   響應內容 (非 JSON): {e.response.text}")
            raise
        except Exception as e:
            logging.error(f"❌ Notion 頁面建立時發生未知錯誤: {e}", exc_info=True)
            raise

    def load_models(self):
        """載入所需的 AI 模型"""
        logging.info("🔄 載入 AI 模型...")
        
        # 載入 Whisper 模型 (如果尚未載入)
        if self.whisper_model is None:
            try:
                logging.info("- 載入 Whisper 模型 (medium)...")
                self.whisper_model = whisper.load_model("medium")
                logging.info("✅ Whisper 模型載入成功")
            except Exception as e:
                logging.error(f"❌ Whisper 模型載入失敗: {e}")
                raise
        
        # 載入 Pyannote 模型 (如果尚未載入)
        if self.diarization_pipeline is None:
            # 增加重試機制
            max_retries = 3
            retry_count = 0
            last_error = None
            
            while retry_count < max_retries:
                try:
                    logging.info(f"- 載入說話人分離模型... (嘗試 {retry_count + 1}/{max_retries})")
                    # Make sure we have the HF_TOKEN
                    hf_token = os.getenv("HF_TOKEN")
                    if not hf_token:
                        raise ValueError("Missing HF_TOKEN environment variable")
                    
                    # Using a specific version instead of latest
                    self.diarization_pipeline = Pipeline.from_pretrained(
                        "pyannote/speaker-diarization-3.1",  # Use specific version
                        use_auth_token=hf_token
                    )
                    logging.info("✅ 說話人分離模型載入成功")
                    break
                except Exception as e:
                    last_error = e
                    logging.error(f"❌ 說話人分離模型載入失敗: {e}")
                    retry_count += 1
                    time.sleep(2)  # 重試前等待2秒
            
            if self.diarization_pipeline is None:
                logging.error(f"❌ 說話人分離模型在 {max_retries} 次嘗試後仍然載入失敗")
                raise last_error or RuntimeError("Failed to load diarization pipeline")
    
    def convert_to_wav(self, input_path: str) -> str:
        """轉換檔案為 WAV 格式 (16kHz 單聲道)"""
        logging.info(f"🔄 轉換檔案格式為 WAV: {os.path.basename(input_path)}")
        
        # 目標路徑 (與原始檔案相同目錄，但副檔名改為 .wav)
        output_dir = os.path.dirname(input_path)
        output_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}.wav"
        output_path = os.path.join(output_dir, output_filename)
        
        # 使用 FFmpeg 轉換
        try:
            cmd = [
                "ffmpeg", 
                "-y",                # 覆蓋現有檔案
                "-i", input_path,    # 輸入檔案
                "-ar", "16000",      # 採樣率 16kHz
                "-ac", "1",          # 單聲道
                "-c:a", "pcm_s16le", # 16-bit PCM
                output_path          # 輸出檔案
            ]
            
            # 執行命令
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info(f"✅ 檔案轉換完成: {output_filename}")
            
            return output_path
            
        except subprocess.CalledProcessError as e:
            logging.error(f"❌ 檔案轉換失敗: {e}")
            raise
    
    def identify_speakers(self, segments: List[Dict[str, Any]], original_speakers: List[str]) -> Dict[str, str]:
        """使用 Gemini 辨識說話人的真實身份"""
        logging.info(f"🔄 識別說話人身份...")
        
        if not segments:
            logging.warning("⚠️ 沒有語音段落，無法識別說話人")
            return {}
        
        # 準備範例對話
        sample_dialogue = ""
        for i, segment in enumerate(segments[:20]):  # 最多使用前 20 個段落
            speaker = segment["speaker"]
            text = segment["text"]
            sample_dialogue += f"{speaker}: {text}\n"
        
        # 提示 Gemini 識別說話人
        try:
            system_prompt = """
            你是一位文字處理專家，專門根據對話內容辨識真實說話人。
            請分析以下對話內容，辨識出各個說話人代碼（如 SPEAKER_00）對應的最可能真實姓名或職稱。
            不確定的說話人請保留原代碼。回應格式必須是一個JSON，key為原始說話人代碼，value為你辨識的真實姓名/職稱。
            只需回傳JSON，不要有其他文字。
            """

            response = self.try_multiple_gemini_models(
                system_prompt,
                f"對話內容如下：\n{sample_dialogue}\n\n請辨識出各個說話人代碼（如 {', '.join(original_speakers)}）對應的最可能真實姓名或職稱。",
                models=['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.0-flash-lite']
            )
            
            response_text = response.text
            # 有時 Gemini 會在 JSON 前後加上額外文字，需要提取純 JSON 部分
            json_match = re.search(r'({.*?})', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)
            
            # 解析 JSON 回應
            speaker_map = json.loads(response_text)
            logging.info(f"✅ 說話人身份識別成功: {speaker_map}")
            
            return speaker_map
            
        except Exception as e:
            logging.error(f"❌ 說話人身份識別失敗: {e}")
            return {speaker: speaker for speaker in original_speakers}  # 失敗時返回原始代碼
    
    def generate_summary(self, transcript: str, attachment_text: Optional[str] = None) -> Dict[str, Any]:
        """使用 Gemini 生成摘要、標題和待辦事項"""
        logging.info("🔄 使用 Gemini 生成摘要...")
        
        try:
            context = ""
            if attachment_text:
                context = f"以下是提供的背景資料：\n{attachment_text}\n\n"
            
            system_prompt = """
            你是一位會議記錄專家，專長於分析會議內容並產生重點摘要。
            同時你具備電子工程通訊相關背景，能夠理解技術性內容(包括一些常聽到的socket, RIC, gNB, nFAPI, OAI等術語)。
            請分析以下會議記錄，並提供:
            1. 一個簡短且清晰的會議標題
            2. 一段簡潔的會議摘要 (約200-300字)
            3. 一個待辦事項清單 (列出會議中提到的需要執行的項目)

            回應格式須為 JSON，包含以下欄位：
            - title: 會議標題
            - summary: 會議摘要
            - todos: 待辦事項清單 (陣列)

            只需回傳 JSON，不要有其他文字。
            """
            
            response = self.try_multiple_gemini_models(
                system_prompt,
                f"{context}以下是會議記錄：\n{transcript}",
                models=
                ['gemini-2.5-flash-preview-04-17',
                        'gemini-1.5-pro', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.0-flash-lite']
            )
            
            response_text = response.text
            # 提取 JSON 部分
            json_match = re.search(r'({.*?})', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)
            
            # 解析 JSON 回應
            summary_data = json.loads(response_text)
            logging.info(f"✅ 摘要生成成功：{summary_data['title']}")
            
            return summary_data
            
        except Exception as e:
            logging.error(f"❌ 摘要生成失敗: {e}")
            # 返回預設值
            return {
                "title": "會議記錄",
                "summary": "摘要生成失敗。" + str(e),
                "todos": ["檢查摘要生成服務"]
            }

    def process_audio(self, audio_path: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
        """處理音檔：預處理、轉文字並進行說話人分離"""
        logging.info(f"🔄 處理音檔: {os.path.basename(audio_path)}")
        
        # 確保模型已載入
        self.load_models()
        
        # 如果檔案非 WAV 格式，先轉換
        if not audio_path.lower().endswith('.wav'):
            wav_path = self.convert_to_wav(audio_path)
            # 移除原始檔案以節省空間
            os.remove(audio_path)
            audio_path = wav_path
        
        # 音頻預處理 (移除靜音)
        preprocessed_path = self.preprocess_audio(audio_path)
        if preprocessed_path != audio_path and os.path.exists(audio_path):
            # 如果產生了新的處理檔案，可以選擇刪除原始檔案
            os.remove(audio_path)
            audio_path = preprocessed_path
            
        # 使用 Whisper 進行語音轉文字，添加錯誤處理和回退機制
        logging.info("- 執行語音轉文字...")
        asr_result = None
        transcription_attempts = [
            # 第一次嘗試：使用預設設置
            {"word_timestamps": False, "verbose": False, "model_name": None, "description": "預設設置"},
            # 第二次嘗試：使用較小的模型
            {"word_timestamps": False, "verbose": False, "model_name": "small", "description": "使用小型模型"}
        ]
        
        for i, attempt in enumerate(transcription_attempts):
            try:
                logging.info(f"- 嘗試轉錄 ({i+1}/{len(transcription_attempts)}): {attempt['description']}")
                
                # 如果指定了不同的模型大小，臨時加載該模型
                temp_model = None
                if attempt['model_name'] and attempt['model_name'] != "medium":
                    temp_model = whisper.load_model(attempt['model_name'])
                    model_to_use = temp_model
                else:
                    model_to_use = self.whisper_model
                
                # 執行轉錄
                asr_result = model_to_use.transcribe(
                    audio_path, 
                    word_timestamps=attempt['word_timestamps'],
                    verbose=attempt['verbose']
                )
                
                # 如果成功，退出嘗試循環
                logging.info(f"✅ 語音轉錄成功 ({attempt['description']})")
                break
            
            except RuntimeError as e:
                # 檢查是否是張量大小不匹配錯誤
                if "must match the size of tensor" in str(e):
                    logging.warning(f"⚠️ 轉錄失敗 ({attempt['description']}): 張量大小不匹配。嘗試其他參數。{e}")
                    if i == len(transcription_attempts) - 1:
                        logging.error("❌ 所有轉錄嘗試均失敗")
                    raise
                else:
                    logging.error(f"❌ 轉錄時發生運行時錯誤: {e}")
                    raise
            except Exception as e:
                logging.error(f"❌ 轉錄失敗: {e}")
                raise
        
        if not asr_result:
            raise RuntimeError("無法轉錄音頻文件")
        
        # 使用 Pyannote 進行說話人分離
        logging.info("- 執行說話人分離...")
        diarization = self.diarization_pipeline(audio_path)
        
        # 整合結果
        logging.info("- 整合結果...")
        segments = []
        transcript_full = ""
        original_speakers = set()
        
        # 製作格式化的輸出
        for i, segment in enumerate(asr_result["segments"]):
            # 找出此段落的主要說話人
            segment_start = segment["start"]
            segment_end = segment["end"]
            text = segment["text"].strip()
            
            # 從說話人分離結果中找出覆蓋此段落時間最多的說話人
            speakers = {}
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                # 計算重疊時間
                overlap_start = max(segment_start, turn.start)
                overlap_end = min(segment_end, turn.end)
                
                if overlap_end > overlap_start:  # 有重疊
                    overlap_duration = overlap_end - overlap_start
                    if speaker in speakers:
                        speakers[speaker] += overlap_duration
                    else:
                        speakers[speaker] = overlap_duration
            
            # 找出主要說話人 (覆蓋時間最長)
            main_speaker = max(speakers.items(), key=lambda x: x[1])[0] if speakers else "未知"
            original_speakers.add(main_speaker)
            
            segment_data = {
                "speaker": main_speaker,
                "start": segment_start,
                "end": segment_end,
                "text": text
            }
            
            segments.append(segment_data)
        
        logging.info(f"✅ 音檔處理完成，共 {len(segments)} 個段落")
        return transcript_full, segments, list(original_speakers)

    def _process_file_job(self, job_id: str, file_id: str, attachment_file_ids: Optional[List[str]] = None):
        """後台處理音頻檔案的工作函數 (在線程中執行)"""
        main_temp_dir = None
        attachments_temp_dir = None
        downloaded_pdf_paths = []
        context_summary = ""
        attachment_texts = []

        try:
            logging.info(f"[Job {job_id}] 開始處理 file_id: {file_id}")
            
            # 獲取原始檔案名稱
            try:
                file_meta = self.drive_service.files().get(
                    fileId=file_id, fields="name"
                ).execute()
                original_filename = file_meta.get('name', '')
                logging.info(f"[Job {job_id}] 原始檔案名稱: {original_filename}")
            except Exception as e:
                logging.error(f"[Job {job_id}] ❌ 獲取原始檔案名稱失敗: {e}")
                original_filename = ""
            
            # 更新進度: 10%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 10
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            # 處理附件 (如果有)
            if attachment_file_ids:
                attachment_texts = []
                for attachment_file_id in attachment_file_ids:
                    attachment_text, attachment_temp_dir = self.download_and_extract_text(attachment_file_id)
                    attachment_texts.append(attachment_text)
                    if attachment_temp_dir:
                        attachments_temp_dir = attachment_temp_dir
            
            # 更新進度: 20%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 20
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            # 下載音頻檔案
            audio_path, audio_temp_dir = self.download_from_drive(file_id)
            
            # 更新進度: 30%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 30
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            # 處理音頻: 轉錄和說話人分離
            _, segments, original_speakers = self.process_audio(audio_path)
            
            # 更新進度: 60%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 60
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
                
            # 識別說話人
            speaker_map = self.identify_speakers(segments, original_speakers)
            
            # 更新進度: 70%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 70
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            # 準備輸出
            updated_segments = []
            transcript_for_summary = ""
            if not segments:
                logging.warning(f"[Job {job_id}] ⚠️ No segments found after audio processing. Transcript will be empty.")
            for seg in segments:
                identified_speaker = speaker_map.get(seg['speaker'], seg['speaker'])
                updated_segments.append({**seg, "speaker": identified_speaker})
                transcript_for_summary += f"[{identified_speaker}]: {seg['text']}\n"
            
            # 更新進度: 75%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 75
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            # 生成摘要
            summary_data = self.generate_summary(transcript_for_summary, attachment_texts[0] if attachment_texts else None)
            title = summary_data["title"]
            summary = summary_data["summary"]
            todos = summary_data["todos"]
            
            # 更新進度: 85%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 85
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            # 建立 Notion 頁面
            page_id, page_url = self.create_notion_page(
                title, summary, todos, updated_segments, speaker_map, file_id
            )
            
            # 更新進度: 95%
            with self.jobs_lock:
                self.jobs[job_id]['progress'] = 95
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            # 重命名 Google Drive 檔案 (可選)
            # 從原始檔名提取日期，如果無法提取則使用當前日期
            file_date = None
            if original_filename:
                file_date = self.extract_date_from_filename(original_filename)
            
            date_str = file_date if file_date else datetime.now().strftime('%Y-%m-%d')
            new_filename = f"[{date_str}] {title}.m4a"
            self.rename_drive_file(file_id, new_filename)
            
            # 更新工作狀態為完成
            result = {
                "success": True,
                "notion_page_id": page_id,
                "notion_page_url": page_url,
                "title": title,
                "summary": summary,
                "todos": todos,
                "identified_speakers": speaker_map,
                "drive_filename": new_filename
            }
            
            with self.jobs_lock:
                self.jobs[job_id]['status'] = JOB_STATUS['COMPLETED']
                self.jobs[job_id]['progress'] = 100
                self.jobs[job_id]['result'] = result
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            logging.info(f"[Job {job_id}] ✅ 處理完成")
            return result

        except Exception as e:
            logging.error(f"[Job {job_id}] ❌ 處理失敗: {e}", exc_info=True)
            
            # 準備錯誤結果
            final_title = summary_data["title"] if 'summary_data' in locals() and summary_data else "處理失敗"
            final_summary = summary_data["summary"] if 'summary_data' in locals() and summary_data else f"處理過程中發生錯誤: {e}"
            final_todos = summary_data["todos"] if 'summary_data' in locals() and summary_data else ["檢查處理日誌"]
            final_speakers = speaker_map if 'speaker_map' in locals() and speaker_map else None
            
            # 更新工作狀態為失敗
            error_result = {
                "success": False,
                "error": f"處理失敗: {e}",
                "notion_page_id": None,
                "notion_page_url": None,
                "title": final_title,
                "summary": final_summary,
                "todos": final_todos,
                "identified_speakers": final_speakers
            }
            
            with self.jobs_lock:
                self.jobs[job_id]['status'] = JOB_STATUS['FAILED']
                self.jobs[job_id]['progress'] = 100
                self.jobs[job_id]['result'] = error_result
                self.jobs[job_id]['error'] = str(e)
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
            
            return error_result

        finally:
            # 清理臨時檔案
            if audio_temp_dir and os.path.exists(audio_temp_dir):
                logging.info(f"[Job {job_id}] 🧹 清理音檔臨時目錄")
                shutil.rmtree(audio_temp_dir)
            if attachments_temp_dir and os.path.exists(attachments_temp_dir):
                logging.info(f"[Job {job_id}] 🧹 清理附件臨時目錄")
                shutil.rmtree(attachments_temp_dir)

    def process_file_async(self, file_id: str, attachment_file_ids: Optional[List[str]] = None) -> str:
        """非同步處理檔案，返回工作 ID"""
        # 生成唯一工作 ID
        job_id = str(uuid.uuid4())
        
        # 初始化工作狀態
        with self.jobs_lock:
            self.jobs[job_id] = {
                'id': job_id,
                'file_id': file_id,
                'attachment_file_ids': attachment_file_ids,
                'status': JOB_STATUS['PENDING'],
                'progress': 0,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'result': None,
                'error': None
            }
        
        # 提交工作到線程池
        self.executor.submit(
            self._process_file_job, job_id, file_id, attachment_file_ids
        )
        
        return job_id
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """獲取工作狀態"""
        with self.jobs_lock:
            job = self.jobs.get(job_id)
            
        if not job:
            return {'error': '工作不存在'}
        
        # 根據工作狀態返回不同信息
        if job['status'] == JOB_STATUS['COMPLETED']:
            return {
                'id': job['id'],
                'status': job['status'],
                'progress': job['progress'],
                'created_at': job['created_at'],
                'updated_at': job['updated_at'],
                'result': job['result']
            }
        elif job['status'] == JOB_STATUS['FAILED']:
            return {
                'id': job['id'],
                'status': job['status'],
                'progress': job['progress'],
                'created_at': job['created_at'],
                'updated_at': job['updated_at'],
                'error': job['error']
            }
        else:
            # 處理中或等待中
            return {
                'id': job['id'],
                'status': job['status'],
                'progress': job['progress'],
                'created_at': job['created_at'],
                'updated_at': job['updated_at']
            }

    def update_job_progress(self, job_id: str, progress: int, message: str, status: Optional[str] = None, error: Optional[str] = None, result_url: Optional[str] = None, notion_page_id: Optional[str] = None):
        """更新指定工作的進度、狀態、訊息、錯誤和結果URL"""
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id]['progress'] = progress
                self.jobs[job_id]['message'] = message
                self.jobs[job_id]['last_updated'] = datetime.utcnow().isoformat() + 'Z'
                if status:
                    self.jobs[job_id]['status'] = status
                if error:
                    self.jobs[job_id]['error'] = error
                if result_url: # Notion page URL or other result link
                    self.jobs[job_id]['result_url'] = result_url
                if notion_page_id:
                    self.jobs[job_id]['notion_page_id'] = notion_page_id
                
                # 如果狀態是完成或失敗，記錄完成時間
                if status in [JOB_STATUS['COMPLETED'], JOB_STATUS['FAILED']]:
                    self.jobs[job_id]['completed_at'] = datetime.utcnow().isoformat() + 'Z'
                    
                logging.info(f"📊 工作進度更新 - ID: {job_id}, 狀態: {self.jobs[job_id]['status']}, 進度: {progress}%, 訊息: {message}")
            else:
                logging.warning(f"⚠️ 嘗試更新不存在的工作 ID: {job_id}")

    def shutdown_executor(self):
        """優雅地關閉 ThreadPoolExecutor"""
        if hasattr(self, 'executor') and self.executor:
            logging.info("🔄 正在關閉 AudioProcessor 的 ThreadPoolExecutor...")
            try:
                # 等待所有目前正在執行的任務完成，但不接受新任務
                self.executor.shutdown(wait=True)
                logging.info("✅ AudioProcessor 的 ThreadPoolExecutor 已成功關閉。")
            except Exception as e:
                logging.error(f"❌ 關閉 AudioProcessor 的 ThreadPoolExecutor 時發生錯誤: {e}", exc_info=True)