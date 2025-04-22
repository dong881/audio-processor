import os
import sys
import tempfile
import shutil
import subprocess
import io
import json
import re  # Added for cleaning JSON
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

# PDF 處理 (需要 pip install PyPDF2)
try:
    import PyPDF2
except ImportError:
    print("⚠️ PyPDF2 未安裝，無法處理 PDF 附件。請執行 'pip install PyPDF2'")
    PyPDF2 = None

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

    def download_from_drive(self, file_id: str) -> Tuple[str, str]:
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
            return local_path, temp_dir
            
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

    def process_audio(self, audio_path: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
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
        
        print(f"✅ 音檔處理完成，共 {len(segments)} 個段落")
        return transcript_full, segments, list(original_speakers)

    def identify_speakers(self, segments: List[Dict[str, Any]], original_speakers: List[str]) -> Dict[str, str]:
        """使用 Gemini 嘗試識別說話人名稱"""
        print("🔄 嘗試識別說話人...")
        
        if not original_speakers or "未知" in original_speakers:
            print("- 無法識別 '未知' 說話人，跳過識別。")
            return {spk: spk for spk in original_speakers}
        
        # 組合對話內容給 LLM
        conversation = ""
        for seg in segments:
            conversation += f"[{seg['speaker']}] {seg['text']}\n"
        
        prompt = f"""
        以下是一段對話記錄，其中說話人被標記為 {', '.join(original_speakers)}。
        請分析對話內容，判斷每個標籤（例如 SPEAKER_00, SPEAKER_01）實際代表的人名是誰。
        人名可能在對話中被直接提及。

        對話記錄：
        {conversation}

        請根據你的分析，提供一個 JSON 格式的映射，將原始標籤映射到識別出的人名。
        如果無法從對話中確定某個標籤的人名，請保留原始標籤。
        範例：{{ "SPEAKER_00": "張三", "SPEAKER_01": "SPEAKER_01" }}

        請只回覆 JSON 格式的映射，不要有其他文字或解釋。
        """
        
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            
            # 清理並解析 JSON 回應
            cleaned_text = response.text.strip().lstrip('```json').rstrip('```').strip()
            speaker_map = json.loads(cleaned_text)
            
            # 驗證格式是否正確
            if not isinstance(speaker_map, dict):
                raise ValueError("LLM 回應不是有效的 JSON 對象")
            for key in original_speakers:
                if key not in speaker_map:
                    print(f"⚠️ LLM 回應缺少標籤 '{key}'，將使用原始標籤。")
                    speaker_map[key] = key
                elif not isinstance(speaker_map[key], str):
                    print(f"⚠️ LLM 回應中標籤 '{key}' 的值不是字串，將使用原始標籤。")
                    speaker_map[key] = key
            
            print(f"✅ 說話人識別完成: {speaker_map}")
            return speaker_map
        except Exception as e:
            print(f"❌ 說話人識別失敗: {str(e)}")
            return {spk: spk for spk in original_speakers}

    def generate_summary(self, transcript: str, attachment_text: Optional[str] = None) -> Dict[str, str]:
        """使用 Gemini 生成摘要和待辦事項，可選加入附件內容"""
        print("🔄 生成摘要與待辦事項...")
        
        # 基礎提示
        prompt_parts = [
            "你是一位專業的會議記錄員，以下是一段會議的語音轉文字記錄",
        ]
        
        # 如果有附件內容，加入提示
        if attachment_text:
            prompt_parts.append("以及一份相關的附加文件內容")
        
        prompt_parts.extend([
            f"""
            請幫我：
            1. 撰寫一段不超過300字的摘要
            2. 列出不超過5項的重要待辦事項 (To-Do)
            3. 給這個會議一個簡短但描述性強的標題

            語音記錄：
            {transcript}
            """
        ])
        
        # 加入附件內容到提示
        if attachment_text:
            prompt_parts.append(f"\n附加文件內容：\n{attachment_text}\n")
        
        # 結束提示
        prompt_parts.append(
            """
            請以下列JSON格式回覆：
            {
                "title": "會議標題",
                "summary": "會議摘要...",
                "todos": ["待辦事項1", "待辦事項2", ...]
            }
            只回覆JSON，不要有其他文字或解釋。
            """
        )
        
        full_prompt = "".join(prompt_parts)
        
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(full_prompt)
            
            # 嘗試提取和清理 JSON
            match = re.search(r"```json\s*(\{.*?\})\s*```", response.text, re.DOTALL)
            if match:
                json_text = match.group(1)
            else:
                json_text = response.text.strip()
                if not json_text.startswith('{') or not json_text.endswith('}'):
                    raise ValueError("回應不是預期的 JSON 格式")
            
            # 解析 JSON 回應
            summary_data = json.loads(json_text)
            
            # 基本驗證
            if not all(k in summary_data for k in ["title", "summary", "todos"]):
                raise ValueError("缺少必要的 JSON 鍵")
            if not isinstance(summary_data["todos"], list):
                raise ValueError("'todos' 必須是一個列表")
            
            print("✅ 摘要生成完成")
            return summary_data
        except Exception as e:
            print(f"❌ 摘要生成失敗: {str(e)}")
            return {
                "title": "會議記錄 (摘要生成失敗)",
                "summary": "無法生成摘要，請查看原始記錄。",
                "todos": ["檢閱會議記錄並手動整理重點"]
            }

    def download_and_extract_text(self, file_id: str) -> Tuple[Optional[str], Optional[str]]:
        """下載 Google Drive 檔案並提取文字 (目前僅支援 PDF)"""
        print(f"🔄 下載並提取附件文字 (ID: {file_id})...")
        temp_dir = None
        try:
            # 取得檔案資訊
            file_meta = self.drive_service.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            mime_type = file_meta.get('mimeType', '')
            filename = file_meta.get('name', f'attachment_{file_id}')
            print(f"- 附件名稱: {filename}")
            print(f"- MIME類型: {mime_type}")

            # 目前僅支援 PDF
            if 'pdf' not in mime_type.lower():
                print(f"⚠️ 不支援的附件類型: {mime_type}。跳過文字提取。")
                return None, None

            if PyPDF2 is None:
                print("⚠️ PyPDF2 未安裝，無法提取 PDF 文字。")
                return None, None

            # 下載檔案
            local_path, temp_dir = self.download_from_drive(file_id)

            # 提取 PDF 文字
            text = ""
            try:
                with open(local_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text += page.extract_text() or ""
                print(f"✅ PDF 文字提取完成 (共 {len(text)} 字元)")
                return text, temp_dir
            except Exception as pdf_err:
                print(f"❌ PDF 文字提取失敗: {str(pdf_err)}")
                return None, temp_dir

        except Exception as e:
            print(f"❌ 附件處理失敗: {str(e)}")
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return None, None

    def create_notion_page(self, title: str, summary: str, todos: List[str], segments: List[Dict[str, Any]]) -> str:
        """建立 Notion 頁面 (移除逐字稿時間戳)"""
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

        # 每個段落作為單獨的段落區塊 (無時間戳)
        for segment in segments:
            speaker = segment["speaker"]
            text = segment["text"]

            content = f"[{speaker}]: {text}"

            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            })

        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

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

    def process_file(self, file_id: str, attachment_file_id: Optional[str] = None) -> Dict[str, Any]:
        """處理完整流程，包含附件和說話人識別"""
        audio_temp_dir = None
        attachment_temp_dir = None
        attachment_text = None

        try:
            # 1. 下載並處理附件 (如果提供)
            if attachment_file_id:
                attachment_text, attachment_temp_dir = self.download_and_extract_text(attachment_file_id)

            # 2. 下載音檔
            audio_path, audio_temp_dir = self.download_from_drive(file_id)

            # 3. 處理音檔 (獲取原始分段和說話人標籤)
            _, segments, original_speakers = self.process_audio(audio_path)

            # 4. 識別說話人
            speaker_map = self.identify_speakers(segments, original_speakers)

            # 5. 更新分段中的說話人名稱，並組合完整文字稿
            updated_segments = []
            transcript_for_summary = ""
            for seg in segments:
                identified_speaker = speaker_map.get(seg['speaker'], seg['speaker'])
                updated_segments.append({**seg, "speaker": identified_speaker})
                transcript_for_summary += f"[{identified_speaker}]: {seg['text']}\n"

            # 6. 生成摘要 (傳入更新後的文字稿和附件文字)
            summary_data = self.generate_summary(transcript_for_summary, attachment_text)
            title = summary_data["title"]
            summary = summary_data["summary"]
            todos = summary_data["todos"]

            # 7. 上傳到 Notion (傳入更新後的分段)
            page_id = self.create_notion_page(title, summary, todos, updated_segments)

            # 8. 回傳結果
            return {
                "success": True,
                "notion_page_id": page_id,
                "title": title,
                "summary": summary,
                "todos": todos,
                "identified_speakers": speaker_map
            }

        except Exception as e:
            print(f"處理檔案時發生未預期錯誤: {str(e)}")
            return {
                "success": False,
                "error": f"處理失敗: {str(e)}",
                "notion_page_id": None,
                "title": None,
                "summary": None,
                "todos": None,
                "identified_speakers": None
            }

        finally:
            # 清理臨時檔案
            if audio_temp_dir and os.path.exists(audio_temp_dir):
                shutil.rmtree(audio_temp_dir)
            if attachment_temp_dir and os.path.exists(attachment_temp_dir):
                shutil.rmtree(attachment_temp_dir)

# 建立單一 AudioProcessor 實例
processor = AudioProcessor()

@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/process', methods=['POST'])
def process_audio_endpoint():
    """處理音檔的 API 端點，可選附件"""
    try:
        # 驗證請求
        data = request.json

        if not data:
            return jsonify({"success": False, "error": "無效的請求內容"}), 400

        file_id = data.get('file_id')
        attachment_file_id = data.get('attachment_file_id')

        if not file_id:
            return jsonify({"success": False, "error": "缺少 file_id 參數"}), 400

        # 處理檔案 (傳入兩個 ID)
        result = processor.process_file(file_id, attachment_file_id)

        if result.get("success"):
            return jsonify(result)
        else:
            print(f"處理失敗，錯誤: {result.get('error', '未知錯誤')}")
            return jsonify({"success": False, "error": result.get('error', '處理過程中發生錯誤')}), 500

    except Exception as e:
        print(f"API 錯誤: {str(e)}")
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {str(e)}"}), 500

if __name__ == "__main__":
    # 設定 Flask 伺服器
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    print(f"🚀 啟動伺服器於 port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug)
