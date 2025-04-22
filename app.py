import os
import sys
import tempfile
import shutil
import subprocess
import io
import json
import re
import time
import logging  # Import logging
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

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

class AudioProcessor:
    def __init__(self):
        self.whisper_model = None
        self.diarization_pipeline = None
        self.drive_service = None
        self.init_services()

    def init_services(self):
        """初始化所有需要的服務"""
        logging.info("🔄 初始化服務中...")
        
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
        
        logging.info("✅ 服務初始化完成")

    def load_models(self):
        """懶加載 AI 模型，節省記憶體"""
        logging.info("🔄 載入AI模型...")
        
        # 載入 Whisper 模型 (如果尚未載入)
        if self.whisper_model is None:
            logging.info("- 載入 Whisper 模型...")
            self.whisper_model = whisper.load_model("base")
            logging.info("- Whisper 模型載入完成")
        
        # 載入 Pyannote 模型 (如果尚未載入)
        if self.diarization_pipeline is None:
            logging.info("- 載入 Pyannote 說話人分離模型...")
            self.diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=os.getenv("HF_TOKEN")
            )
            logging.info("- Pyannote 模型載入完成")
            
        logging.info("✅ 所有AI模型載入完成")

    def download_from_drive(self, file_id: str) -> Tuple[str, str]:
        """從 Google Drive 下載檔案到臨時目錄"""
        logging.info(f"🔄 從 Google Drive 下載檔案 (ID: {file_id})...")

        # 建立臨時目錄
        temp_dir = tempfile.mkdtemp()

        try:
            # 取得檔案資訊
            file_meta = self.drive_service.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            
            filename = file_meta.get('name', f'audio_{file_id}')
            mime_type = file_meta.get('mimeType', '')
            
            logging.info(f"- 檔案名稱: {filename}")
            logging.info(f"- MIME類型: {mime_type}")
            
            # 建立本地檔案路徑
            local_path = os.path.join(temp_dir, filename)
            
            # 下載檔案
            request = self.drive_service.files().get_media(fileId=file_id)
            with io.FileIO(local_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    logging.info(f"- 下載進度: {int(status.progress() * 100)}%")
            
            logging.info(f"✅ 檔案下載完成: {local_path}")
            return local_path, temp_dir
            
        except Exception as e:
            logging.error(f"❌ 檔案下載失敗: {str(e)}")
            shutil.rmtree(temp_dir)
            raise

    def convert_to_wav(self, input_path: str) -> str:
        """將音檔轉換為 WAV 格式 (16kHz, 單聲道)"""
        logging.info(f"🔄 轉換檔案格式: {os.path.basename(input_path)} -> WAV")
        
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
            logging.info(f"✅ 轉換成功: {temp_wav.name}")
            return temp_wav.name
        except subprocess.CalledProcessError as e:
            logging.error(f"❌ 轉換失敗: {str(e)}")
            logging.error(f"FFmpeg stderr: {e.stderr.decode('utf-8', errors='replace')}")
            os.remove(temp_wav.name)
            raise RuntimeError("音檔轉換失敗")

    def process_audio(self, audio_path: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
        """處理音檔：轉文字並進行說話人分離"""
        logging.info(f"🔄 處理音檔: {os.path.basename(audio_path)}")
        
        # 確保模型已載入
        self.load_models()
        
        # 如果檔案非 WAV 格式，先轉換
        if not audio_path.lower().endswith('.wav'):
            wav_path = self.convert_to_wav(audio_path)
            # 可選：移除原始檔案以節省空間
            os.remove(audio_path)
            audio_path = wav_path
            
        # 使用 Whisper 進行語音轉文字
        logging.info("- 執行語音轉文字...")
        asr_result = self.whisper_model.transcribe(
            audio_path, 
            word_timestamps=True,  # 啟用字詞時間戳記
            verbose=False
        )
        
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

    def identify_speakers(self, segments: List[Dict[str, Any]], original_speakers: List[str]) -> Dict[str, str]:
        """使用 Gemini 嘗試識別說話人名稱"""
        logging.info("🔄 嘗試識別說話人...")
        
        if not original_speakers or "未知" in original_speakers:
            logging.info("- 無法識別 '未知' 說話人，跳過識別。")
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
            # Use the latest flash model identifier
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            response = model.generate_content(prompt)
            
            # 清理並解析 JSON 回應
            cleaned_text = response.text.strip().lstrip('```json').rstrip('```').strip()
            speaker_map = json.loads(cleaned_text)
            
            # 驗證格式是否正確
            if not isinstance(speaker_map, dict):
                raise ValueError("LLM 回應不是有效的 JSON 對象")
            for key in original_speakers:
                if key not in speaker_map:
                    logging.warning(f"⚠️ LLM 回應缺少標籤 '{key}'，將使用原始標籤。")
                    speaker_map[key] = key
                elif not isinstance(speaker_map[key], str):
                    logging.warning(f"⚠️ LLM 回應中標籤 '{key}' 的值不是字串，將使用原始標籤。")
                    speaker_map[key] = key
            
            logging.info(f"✅ 說話人識別完成: {speaker_map}")
            return speaker_map
        except Exception as e:
            logging.error(f"❌ 說話人識別失敗: {str(e)}")
            # Log API feedback if available (check response existence)
            if 'response' in locals() and hasattr(response, 'prompt_feedback'):
                logging.error(f"   - Gemini Prompt Feedback: {response.prompt_feedback}")
            if 'response' in locals() and response and response.candidates:
                logging.error(f"   - Gemini Finish Reason: {response.candidates[0].finish_reason}")
            return {spk: spk for spk in original_speakers}

    def generate_summary(self, transcript: str, attachment_text: Optional[str] = None) -> Dict[str, str]:
        """使用 Gemini 生成摘要和待辦事項，包含重試機制和更詳細的日誌記錄"""
        logging.info("🔄 開始生成摘要與待辦事項...")

        # Check if the transcript is empty or too short
        if not transcript or len(transcript.strip()) < 10:
            logging.warning("⚠️ 傳入的 transcript 為空或過短，無法生成摘要。")
            return self.get_fallback_summary_data("Transcript is empty or too short")

        # Log the first few characters of the transcript to verify content
        logging.info(f"  - Transcript (start): {transcript[:200]}...")
        if attachment_text:
            logging.info(f"  - Attachment Text (start): {attachment_text[:200]}...")

        # --- Prompt Definition ---
        prompt_parts = [
            "你是一位專業的會議記錄員。根據以下提供的語音記錄",
        ]
        if attachment_text:
            prompt_parts.append("和附加文件內容")
        prompt_parts.extend([
            f"""
            ，請執行以下任務：
            1. 撰寫一段不超過300字的摘要。
            2. 列出不超過5項的重要待辦事項 (To-Do)。
            3. 給這個會議一個簡短但描述性強的標題。

            語音記錄：
            {transcript}
            """
        ])
        if attachment_text:
            prompt_parts.append(f"\n附加文件內容：\n{attachment_text}\n")
        prompt_parts.append(
            """
            **重要指示：** 你的回覆 **必須** 僅包含一個有效的 JSON 物件，其結構如下所示。
            **絕對不要** 在 JSON 物件前後包含任何其他文字、註解、說明或 markdown 標記 (例如 ```json ... ```)。

            ```json
            {{
                "title": "會議標題",
                "summary": "會議摘要...",
                "todos": ["待辦事項1", "待辦事項2", ...]
            }}
            ```
            """
        )
        full_prompt = "".join(prompt_parts)
        # --- End Prompt Definition ---

        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            logging.info(f"  - 嘗試調用 Gemini API (第 {attempt + 1}/{max_retries} 次)...")
            response = None  # Initialize response to None
            try:
                # Use the latest flash model identifier
                model = genai.GenerativeModel('gemini-2.0-flash')
                # model = genai.GenerativeModel('models/gemini-2.5-flash-preview-04-17')
                response = model.generate_content(full_prompt)
                raw_text = response.text

                logging.info(f"  - Gemini Raw Response (Attempt {attempt+1}):\n{raw_text}")  # Log the FULL raw response

                # --- JSON Parsing Logic ---
                cleaned_text = raw_text.strip()
                match = re.search(r"```json\s*(\{.*?\})\s*```", cleaned_text, re.DOTALL)
                if match:
                    json_text = match.group(1)
                    logging.info("  - JSON extracted from markdown block.")
                else:
                    if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
                        json_text = cleaned_text
                        logging.info("  - Raw response treated as JSON.")
                    else:
                        logging.error(f"  - 解析失敗：回應內容不是預期的 JSON 物件格式或 Markdown JSON 區塊。")
                        raise ValueError("Response content was not a valid JSON object or markdown block.")

                summary_data = json.loads(json_text)

                if not all(k in summary_data for k in ["title", "summary", "todos"]):
                    logging.error(f"  - 解析失敗：JSON 物件缺少必要的鍵 (title, summary, todos)。 Found keys: {list(summary_data.keys())}")
                    raise ValueError("JSON object missing required keys (title, summary, todos)")
                if not isinstance(summary_data["todos"], list):
                    logging.error(f"  - 解析失敗：'todos' 鍵的值不是列表。 Type: {type(summary_data['todos'])}")
                    raise ValueError("'todos' key value must be a list")
                # --- End JSON Parsing Logic ---

                logging.info("✅ 摘要生成成功")
                return summary_data

            except json.JSONDecodeError as json_err:
                logging.error(f"❌ 第 {attempt + 1} 次 JSON 解析失敗: {str(json_err)}")
                logging.error(f"   - Failed JSON Text: {json_text[:500]}...")  # Log the text that failed parsing

            except Exception as e:
                logging.error(f"❌ 第 {attempt + 1} 次摘要生成/處理時發生錯誤: {str(e)}")
                # Check if response exists before accessing attributes
                if response:
                    if hasattr(response, 'prompt_feedback'):
                        logging.error(f"   - Gemini Prompt Feedback: {response.prompt_feedback}")
                    if response.candidates:
                        logging.error(f"   - Gemini Finish Reason: {response.candidates[0].finish_reason}")
                else:
                    logging.error("   - Gemini API call likely failed before response was received.")

            if attempt < max_retries - 1:
                logging.info(f"   將在 {retry_delay} 秒後重試...")
                time.sleep(retry_delay)
            else:
                logging.error("❌ 已達最大重試次數，摘要生成失敗。")

        logging.warning("❌ 所有摘要生成嘗試失敗，返回預設內容。")
        return self.get_fallback_summary_data("Max retries reached or permanent error")

    def get_fallback_summary_data(self, reason: str = "Unknown error") -> Dict[str, str]:
        """Returns the default summary data when generation fails."""
        logging.warning(f"  - Using fallback summary data. Reason: {reason}")
        return {
            "title": "會議記錄 (摘要生成失敗)",
            "summary": "無法生成摘要，請查看原始記錄。",
            "todos": ["檢閱會議記錄並手動整理重點"]
        }

    def create_notion_page(self, title: str, summary: str, todos: List[str], segments: List[Dict[str, Any]]) -> Tuple[str, str]:
        """建立 Notion 頁面 (移除逐字稿時間戳)"""
        logging.info("🔄 建立 Notion 頁面...")

        notion_token = os.getenv("NOTION_TOKEN")
        database_id = os.getenv("NOTION_DATABASE_ID")

        if not notion_token or not database_id:
            raise ValueError("缺少 Notion API 設定")

        blocks = []

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
            page_url = result.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")
            logging.info(f"✅ Notion 頁面建立成功 (ID: {page_id}, URL: {page_url})")
            return page_id, page_url
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Notion API 請求失敗: {str(e)}", exc_info=True)
            if e.response is not None:
                try:
                    err_details = e.response.json()
                    logging.error(f"   錯誤碼: {e.response.status_code}, 訊息: {json.dumps(err_details, indent=2, ensure_ascii=False)}")
                except json.JSONDecodeError:
                    logging.error(f"   響應內容 (非 JSON): {e.response.text}")
            raise
        except Exception as e:
            logging.error(f"❌ Notion 頁面建立時發生未知錯誤: {str(e)}", exc_info=True)
            raise

    def process_file(self, file_id: str, attachment_file_id: Optional[str] = None) -> Dict[str, Any]:
        """處理完整流程，包含附件和說話人識別"""
        audio_temp_dir = None
        attachment_temp_dir = None
        attachment_text = None
        summary_data = None

        try:
            logging.info(f"Processing file_id: {file_id}, attachment_file_id: {attachment_file_id}")
            if attachment_file_id:
                attachment_text, attachment_temp_dir = self.download_and_extract_text(attachment_file_id)

            audio_path, audio_temp_dir = self.download_from_drive(file_id)

            _, segments, original_speakers = self.process_audio(audio_path)

            speaker_map = self.identify_speakers(segments, original_speakers)

            updated_segments = []
            transcript_for_summary = ""
            if not segments:
                logging.warning("⚠️ No segments found after audio processing. Transcript will be empty.")
            for seg in segments:
                identified_speaker = speaker_map.get(seg['speaker'], seg['speaker'])
                updated_segments.append({**seg, "speaker": identified_speaker})
                transcript_for_summary += f"[{identified_speaker}]: {seg['text']}\n"

            summary_data = self.generate_summary(transcript_for_summary, attachment_text)
            title = summary_data["title"]
            summary = summary_data["summary"]
            todos = summary_data["todos"]

            page_id, page_url = self.create_notion_page(title, summary, todos, updated_segments)

            logging.info(f"✅ File processing successful for file_id: {file_id}")
            return {
                "success": True,
                "notion_page_id": page_id,
                "notion_page_url": page_url,
                "title": title,
                "summary": summary,
                "todos": todos,
                "identified_speakers": speaker_map
            }

        except Exception as e:
            logging.error(f"處理檔案時發生未預期錯誤 (file_id: {file_id}): {str(e)}", exc_info=True)
            final_title = summary_data["title"] if summary_data else "處理失敗"
            final_summary = summary_data["summary"] if summary_data else f"處理過程中發生錯誤: {str(e)}"
            final_todos = summary_data["todos"] if summary_data else ["檢查處理日誌"]

            return {
                "success": False,
                "error": f"處理失敗: {str(e)}",
                "notion_page_id": None,
                "notion_page_url": None,
                "title": final_title,
                "summary": final_summary,
                "todos": final_todos,
                "identified_speakers": None
            }

        finally:
            if audio_temp_dir and os.path.exists(audio_temp_dir):
                logging.info(f"🧹 清理音檔臨時目錄: {audio_temp_dir}")
                shutil.rmtree(audio_temp_dir)
            if attachment_temp_dir and os.path.exists(attachment_temp_dir):
                logging.info(f"🧹 清理附件臨時目錄: {attachment_temp_dir}")
                shutil.rmtree(attachment_temp_dir)

processor = AudioProcessor()

@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/process', methods=['POST'])
def process_audio_endpoint():
    """處理音檔的 API 端點，可選附件"""
    try:
        data = request.json

        if not data:
            return jsonify({"success": False, "error": "無效的請求內容"}), 400

        file_id = data.get('file_id')
        attachment_file_id = data.get('attachment_file_id')

        if not file_id:
            return jsonify({"success": False, "error": "缺少 file_id 參數"}), 400

        result = processor.process_file(file_id, attachment_file_id)

        if result.get("success"):
            return jsonify(result)
        else:
            logging.error(f"處理失敗，錯誤: {result.get('error', '未知錯誤')}")
            return jsonify({"success": False, "error": result.get('error', '處理過程中發生錯誤')}), 500

    except Exception as e:
        logging.error(f"API 錯誤: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    logging.info(f"🚀 啟動伺服器於 port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug)
