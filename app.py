import os
import sys
import tempfile
import shutil
import subprocess
import io
import json
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

# Flask 相關
from flask import Flask, request, jsonify
import requests

# Google API 相關
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 語音處理相關
import whisper
from pyannote.audio import Pipeline

# LLM API 相關
import google.generativeai as genai

# 載入環境變數
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

class AudioProcessor:
    def __init__(self):
        self.whisper_model = None
        self.diarization_pipeline = None
        self.drive_service = None
        self.init_services()

    def init_services(self):
        """初始化所有需要的服務"""
        print("🔄 初始化服務中...")
        
        # 初始化 Google Drive API
        if os.getenv("USE_SERVICE_ACCOUNT") == "true":
            # 使用服務帳號
            credentials = service_account.Credentials.from_service_account_file(
                os.getenv("GOOGLE_SA_JSON_PATH"),
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
        else:
            # 使用 OAuth 憑證
            credentials = Credentials.from_authorized_user_file(
                os.getenv("GOOGLE_CREDS_JSON_PATH"),
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
        
        self.drive_service = build('drive', 'v3', credentials=credentials)
        
        # 初始化 Google Gemini API
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        
        print("✅ 服務初始化完成")

    def load_models(self):
        """懶加載 AI 模型，節省記憶體"""
        print("🔄 載入AI模型...")
        
        # 載入 Whisper 模型 (如果尚未載入)
        if self.whisper_model is None:
            print("- 載入 Whisper 模型...")
            self.whisper_model = whisper.load_model("base")
            print("- Whisper 模型載入完成")
        
        # 載入 Pyannote 模型 (如果尚未載入)
        if self.diarization_pipeline is None:
            print("- 載入 Pyannote 說話人分離模型...")
            self.diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=os.getenv("HF_TOKEN")
            )
            print("- Pyannote 模型載入完成")
            
        print("✅ 所有AI模型載入完成")

    def download_from_drive(self, file_id: str) -> str:
        """從 Google Drive 下載檔案到臨時目錄"""
        print(f"🔄 從 Google Drive 下載檔案 (ID: {file_id})...")
        
        # 建立臨時目錄
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 取得檔案資訊
            file_meta = self.drive_service.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            
            filename = file_meta.get('name', f'audio_{file_id}')
            mime_type = file_meta.get('mimeType', '')
            
            print(f"- 檔案名稱: {filename}")
            print(f"- MIME類型: {mime_type}")
            
            # 建立本地檔案路徑
            local_path = os.path.join(temp_dir, filename)
            
            # 下載檔案
            request = self.drive_service.files().get_media(fileId=file_id)
            with io.FileIO(local_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    print(f"- 下載進度: {int(status.progress() * 100)}%")
            
            print(f"✅ 檔案下載完成: {local_path}")
            return local_path
            
        except Exception as e:
            print(f"❌ 檔案下載失敗: {str(e)}")
            shutil.rmtree(temp_dir)
            raise

    def convert_to_wav(self, input_path: str) -> str:
        """將音檔轉換為 WAV 格式 (16kHz, 單聲道)"""
        print(f"🔄 轉換檔案格式: {os.path.basename(input_path)} -> WAV")
        
        # 在相同目錄中建立暫存 WAV 檔案
        dir_path = os.path.dirname(input_path)
        temp_wav = tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, dir=dir_path
        )
        temp_wav.close()
        
        # 使用 FFmpeg 進行轉換
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-acodec', 'pcm_s16le',  # 16-bit PCM
            '-ar', '16000',          # 16kHz 取樣率
            '-ac', '1',              # 單聲道
            temp_wav.name
        ]
        
        try:
            result = subprocess.run(
                cmd, 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            print(f"✅ 轉換成功: {temp_wav.name}")
            return temp_wav.name
        except subprocess.CalledProcessError as e:
            print(f"❌ 轉換失敗: {str(e)}")
            print(f"FFmpeg stderr: {e.stderr.decode('utf-8', errors='replace')}")
            os.remove(temp_wav.name)
            raise RuntimeError("音檔轉換失敗")

    def process_audio(self, audio_path: str) -> Tuple[str, List[Dict[str, Any]]]:
        """處理音檔：轉文字並進行說話人分離"""
        print(f"🔄 處理音檔: {os.path.basename(audio_path)}")
        
        # 確保模型已載入
        self.load_models()
        
        # 如果檔案非 WAV 格式，先轉換
        if not audio_path.lower().endswith('.wav'):
            wav_path = self.convert_to_wav(audio_path)
            # 可選：移除原始檔案以節省空間
            os.remove(audio_path)
            audio_path = wav_path
            
        # 使用 Whisper 進行語音轉文字
        print("- 執行語音轉文字...")
        asr_result = self.whisper_model.transcribe(
            audio_path, 
            word_timestamps=True,  # 啟用字詞時間戳記
            verbose=False
        )
        
        # 使用 Pyannote 進行說話人分離
        print("- 執行說話人分離...")
        diarization = self.diarization_pipeline(audio_path)
        
        # 整合結果
        print("- 整合結果...")
        segments = []
        transcript_full = ""
        
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
            
            segment_data = {
                "speaker": main_speaker,
                "start": segment_start,
                "end": segment_end,
                "text": text
            }
            
            segments.append(segment_data)
            transcript_full += f"[{main_speaker}] {segment_start:.1f}-{segment_end:.1f}: {text}\n"
        
        print(f"✅ 音檔處理完成，共 {len(segments)} 個段落")
        return transcript_full, segments

    def generate_summary(self, transcript: str) -> Dict[str, str]:
        """使用 Gemini 生成摘要和待辦事項"""
        print("🔄 生成摘要與待辦事項...")
        
        prompt = f"""
        你是一位專業的會議記錄員，以下是一段會議的語音轉文字記錄，請幫我：
        1. 撰寫一段不超過300字的摘要
        2. 列出不超過5項的重要待辦事項 (To-Do)
        3. 給這個會議一個簡短但描述性強的標題
        
        語音記錄：
        {transcript}
        
        請以下列JSON格式回覆：
        {{
            "title": "會議標題",
            "summary": "會議摘要...",
            "todos": ["待辦事項1", "待辦事項2", ...]
        }}
        只回覆JSON，不要有其他文字。
        """
        
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            
            # 解析 JSON 回應
            summary_data = json.loads(response.text)
            print("✅ 摘要生成完成")
            return summary_data
        except Exception as e:
            print(f"❌ 摘要生成失敗: {str(e)}")
            # 若失敗，返回基本資料
            return {
                "title": "會議記錄",
                "summary": "無法生成摘要，請查看原始記錄。",
                "todos": ["檢閱會議記錄並手動整理重點"]
            }

    def create_notion_page(self, title: str, summary: str, todos: List[str], transcript: str, segments: List[Dict[str, Any]]) -> str:
        """建立 Notion 頁面"""
        print("🔄 建立 Notion 頁面...")
        
        notion_token = os.getenv("NOTION_TOKEN")
        database_id = os.getenv("NOTION_DATABASE_ID")
        
        if not notion_token or not database_id:
            raise ValueError("缺少 Notion API 設定")
            
        # 製作 Notion 區塊內容
        blocks = []
        
        # 新增摘要區塊
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "摘要"}}]
            }
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": summary}}]
            }
        })
        
        # 新增待辦事項區塊
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "待辦事項"}}]
            }
        })
        
        for todo in todos:
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": todo}}],
                    "checked": False
                }
            })
        
        # 新增完整記錄區塊
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "完整記錄"}}]
            }
        })
        
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "以下是會議的完整轉錄內容："}}]
            }
        })
        
        # 每個段落作為單獨的段落區塊
        for segment in segments:
            speaker = segment["speaker"]
            start_time = f"{segment['start']:.1f}"
            end_time = f"{segment['end']:.1f}"
            text = segment["text"]
            
            content = f"[{speaker}] {start_time}-{end_time}: {text}"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            })
        
        # 組合 API 請求
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # 設定頁面內容
        current_date = datetime.now().strftime("%Y-%m-%d")
        data = {
            "parent": {"database_id": database_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": f"{title} ({current_date})"}}]
                }
            },
            "children": blocks
        }
        
        # 發送請求
        try:
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            result = response.json()
            page_id = result["id"]
            print(f"✅ Notion 頁面建立成功 (ID: {page_id})")
            return page_id
        except Exception as e:
            print(f"❌ Notion 頁面建立失敗: {str(e)}")
            if hasattr(e, 'response') and e.response:
                print(f"響應內容: {e.response.text}")
            raise

    def process_file(self, file_id: str) -> Dict[str, Any]:
        """處理完整流程"""
        temp_dir = None
        
        try:
            # 下載檔案
            audio_path = self.download_from_drive(file_id)
            temp_dir = os.path.dirname(audio_path)
            
            # 處理音檔
            transcript, segments = self.process_audio(audio_path)
            
            # 生成摘要
            summary_data = self.generate_summary(transcript)
            title = summary_data["title"]
            summary = summary_data["summary"]
            todos = summary_data["todos"]
            
            # 上傳到 Notion
            page_id = self.create_notion_page(title, summary, todos, transcript, segments)
            
            # 回傳結果
            return {
                "success": True,
                "notion_page_id": page_id,
                "title": title,
                "summary": summary,
                "todos": todos
            }
        
        finally:
            # 清理臨時檔案
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

# 建立單一 AudioProcessor 實例
processor = AudioProcessor()

@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/process', methods=['POST'])
def process_audio_endpoint():
    """處理音檔的 API 端點"""
    try:
        # 驗證請求
        data = request.json
        
        if not data:
            return jsonify({"error": "無效的請求內容"}), 400
        
        file_id = data.get('file_id')
        if not file_id:
            return jsonify({"error": "缺少 file_id 參數"}), 400
            
        # 處理檔案
        result = processor.process_file(file_id)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"API 錯誤: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # 設定 Flask 伺服器
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    print(f"🚀 啟動伺服器於 port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug)
