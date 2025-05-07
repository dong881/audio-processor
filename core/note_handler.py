import os
import json
import time
import logging
import requests
import re
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
import google.generativeai as genai

class NoteHandler:
    """
    筆記處理器類別
    負責處理摘要生成、筆記格式化和 Notion 整合
    """
    
    def __init__(self, notion_formatter):
        """
        初始化筆記處理器
        
        Args:
            notion_formatter: Notion 格式化工具實例
        """
        self.notion_formatter = notion_formatter
        self.notion_token = os.getenv("NOTION_TOKEN")
        self.notion_database_id = os.getenv("NOTION_DATABASE_ID")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        # 配置 Google Gemini API
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
        else:
            logging.warning("⚠️ 未設置 GEMINI_API_KEY 環境變數，AI 功能將無法使用")

    def try_multiple_gemini_models(self, system_prompt: str, user_content: str, 
                                models: Optional[List[str]] = None) -> Any:
        """
        嘗試使用多個 Gemini 模型，直到一個成功
        
        Args:
            system_prompt: 系統提示詞
            user_content: 使用者內容
            models: 要嘗試的模型列表，如果為 None 則使用預設列表
            
        Returns:
            Gemini API 回應對象
            
        Raises:
            ValueError: 若所有模型都失敗
        """
        # 預設模型列表
        if models is None:
            models = [
                'gemini-2.5-pro-exp-03-25', 
                'gemini-1.5-pro', 
                'gemini-2.5-flash-preview-04-17',
                'gemini-2.0-flash', 
                'gemini-1.5-flash', 
                'gemini-2.0-flash-lite'
            ]
        
        response = None
        last_error = None
        quota_errors = []

        # 嘗試不同模型直到成功
        for model_name in models:
            try:
                logging.info(f"🔄 使用模型: {model_name}")
                model = genai.GenerativeModel(model_name)
                
                # 配置生成參數
                generation_config = {
                    "temperature": 0.2,  # 較低溫度以獲得更一致的回應
                    "top_p": 0.9,
                    "top_k": 40,
                    "max_output_tokens": 4096
                }
                
                # 生成內容
                response = model.generate_content(
                    [system_prompt, user_content],
                    generation_config=generation_config
                )
                
                # 成功則跳出循環
                logging.info(f"✅ 成功使用模型 {model_name}")
                break
                
            except Exception as e:
                last_error = e
                
                # 檢查是否為配額錯誤
                if "429" in str(e) or "quota" in str(e).lower():
                    # 提取錯誤訊息中的 URL
                    url_match = re.search(r'https?://\S+', str(e))
                    url_info = url_match.group(0) if url_match else "未知URL"
                    
                    logging.warning(f"⚠️ 模型 {model_name} 配額已用盡: {url_info}")
                    quota_errors.append(model_name)
                    continue
                else:
                    # 其他非配額錯誤
                    logging.error(f"❌ 使用模型 {model_name} 時發生錯誤: {str(e)}")
                    if model_name == models[-1]:
                        raise  # 最後一個模型也失敗時才拋出錯誤

        # 檢查是否所有模型都失敗
        if response is None:
            if quota_errors:
                error_msg = f"所有模型都達到配額限制: {', '.join(quota_errors)}"
            else:
                error_msg = f"所有模型都失敗: {str(last_error)}"
                
            logging.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        return response

    def generate_comprehensive_notes(self, transcript: str) -> str:
        """
        使用 Gemini 生成結構化筆記
        
        Args:
            transcript: 會議逐字稿
            
        Returns:
            Markdown 格式的結構化筆記
        """
        logging.info("🔄 生成會議筆記...")
        
        try:
            # 系統提示詞
            system_prompt = """
            你是一位專業的會議筆記整理專家。請將提供的會議逐字稿整理為結構化的 Markdown 格式筆記。
            
            請遵循以下格式:
            1. 使用適當的標題層級 (##, ###)
            2. 識別並列出關鍵主題、決策和行動項目
            3. 依照邏輯順序組織內容，將相關討論分組
            4. 使用清單 (- 或 1.) 來列舉要點
            5. 使用粗體和斜體來強調重要內容
            
            直接輸出 Markdown，不要使用代碼區塊標記如 ```markdown。
            保持客觀、簡潔，不要添加未在原始內容中提及的解釋或資訊。
            """

            # 使用備選模型嘗試生成
            response = self.try_multiple_gemini_models(
                system_prompt,
                f"會議逐字稿：\n{transcript}",
                models=['gemini-2.5-flash-preview-04-17', 'gemini-1.5-pro', 'gemini-2.0-flash-lite']
            )
            
            # 提取筆記內容
            notes = response.text.strip()
            logging.info("✅ 筆記生成成功")
            return notes
            
        except Exception as e:
            logging.error(f"❌ 筆記生成失敗: {str(e)}")
            return f"### 筆記生成失敗\n\n發生錯誤: {str(e)}\n\n請參考完整逐字稿。"
    
    def generate_summary(self, transcript: str, attachment_text: Optional[str] = None) -> Dict[str, Any]:
        """
        使用 Gemini 生成摘要、標題和待辦事項
        
        Args:
            transcript: 會議逐字稿
            attachment_text: 附件文本（可選）
            
        Returns:
            包含標題、摘要和待辦事項的字典
        """
        logging.info("🔄 生成會議摘要...")
        
        try:
            # 準備上下文
            context = ""
            if attachment_text:
                context = f"以下是提供的背景資料：\n{attachment_text[:3000]}...\n\n" if len(attachment_text) > 3000 else f"以下是提供的背景資料：\n{attachment_text}\n\n"
            
            # 截取逐字稿，避免太長
            truncated_transcript = transcript
            if len(transcript) > 12000:  # 約 3000 個中文字
                truncated_transcript = transcript[:12000] + "...(後續內容已省略)"
                
            # 系統提示詞
            system_prompt = """
            你是一位專業的會議分析專家，精通摘要生成和識別行動項目。
            請分析提供的會議記錄，並以 JSON 格式返回以下內容:
            
            1. title: 簡短且描述性的會議標題 (20字以內)
            2. summary: 會議核心內容的摘要 (200-300字)
            3. todos: 會議中明確提到或隱含的待辦事項列表 (每項最多30字)
            
            JSON 格式範例:
            {
              "title": "會議標題",
              "summary": "會議摘要...",
              "todos": ["待辦事項1", "待辦事項2", "..."]
            }
            
            僅返回純 JSON，不要包含其他文字。如果找不到待辦事項，返回空列表。
            """
            
            # 使用備選模型生成
            response = self.try_multiple_gemini_models(
                system_prompt,
                f"{context}會議記錄：\n{truncated_transcript}"
            )
            
            # 解析 JSON
            response_text = response.text
            json_match = re.search(r'({.*?})', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)
                
            try:
                summary_data = json.loads(response_text)
                
                # 確保所有字段都存在
                summary_data.setdefault("title", "會議記錄")
                summary_data.setdefault("summary", "未能生成摘要")
                summary_data.setdefault("todos", [])
                
                logging.info(f"✅ 摘要生成成功：{summary_data['title']}")
                return summary_data
                
            except json.JSONDecodeError as e:
                logging.error(f"❌ 無法解析 AI 回應的 JSON: {str(e)}")
                return {
                    "title": "會議記錄",
                    "summary": "摘要生成失敗。無法解析 AI 回應。",
                    "todos": ["檢查摘要生成服務"]
                }
                
        except Exception as e:
            logging.error(f"❌ 摘要生成失敗: {str(e)}")
            return {
                "title": "會議記錄",
                "summary": f"摘要生成失敗: {str(e)}",
                "todos": ["檢查摘要生成服務"]
            }
    
    def identify_speakers(self, segments: List[Dict[str, Any]], original_speakers: List[str]) -> Dict[str, str]:
        """
        嘗試辨識說話人身份
        
        Args:
            segments: 語音段落列表
            original_speakers: 原始說話人編號列表
            
        Returns:
            說話人映射字典，從原始編號到猜測的身份
        """
        logging.info("🔄 辨識說話人身份...")
        
        try:
            # 如果只有一位說話人，直接返回
            if len(original_speakers) <= 1:
                return {original_speakers[0]: "參與者 1"} if original_speakers else {}
            
            # 建立初始話者映射
            speaker_map = {speaker: f"參與者 {i+1}" for i, speaker in enumerate(original_speakers)}
            
            # 為每位說話人收集發言樣本
            speaker_samples = {}
            for segment in segments:
                speaker = segment["speaker"]
                text = segment["text"]
                
                if not text.strip():
                    continue
                    
                if speaker not in speaker_samples:
                    speaker_samples[speaker] = []
                    
                if len(speaker_samples[speaker]) < 5:  # 每位說話人最多收集 5 個樣本
                    speaker_samples[speaker].append(text)
            
            # 如果沒有足夠樣本，使用默認映射
            if not speaker_samples or sum(len(samples) for samples in speaker_samples.values()) < 3:
                return speaker_map
            
            # 準備提示詞
            sample_text = ""
            for speaker, samples in speaker_samples.items():
                sample_text += f"\n【{speaker} 的發言範例】\n"
                for i, sample in enumerate(samples):
                    sample_text += f"{i+1}. {sample}\n"
            
            system_prompt = """
            你是一位對話分析專家，能從對話內容推測說話者的身份或角色。
            請分析提供的對話片段，推測每位說話者可能的身份或角色（如：主持人、專案經理、客戶等）。
            如無法判斷具體身份，可用「參與者 1」、「參與者 2」等表示。

            請以 JSON 格式返回結果:
            {"SPEAKER_ID": "身份名稱", ...}

            只返回 JSON 格式，不要其他文字。
            """
            
            response = self.try_multiple_gemini_models(
                system_prompt,
                f"以下是一段會議中不同講者的發言樣本，請幫助識別他們可能的身份或角色：{sample_text}",
                models=['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.0-flash-lite']
            )
            
            # 解析結果
            try:
                # 嘗試從回應中提取 JSON
                json_match = re.search(r'{.*}', response.text, re.DOTALL)
                if json_match:
                    speaker_identities = json.loads(json_match.group(0))
                    
                    # 使用識別結果更新映射
                    for speaker in original_speakers:
                        if speaker in speaker_identities and speaker_identities[speaker].strip():
                            speaker_map[speaker] = speaker_identities[speaker]
                    
                    logging.info(f"✅ 識別到的說話人: {speaker_map}")
                    return speaker_map
                else:
                    logging.warning("⚠️ 無法從回應中提取 JSON")
                    return speaker_map
                    
            except Exception as e:
                logging.warning(f"⚠️ 解析說話人身份時出錯: {str(e)}")
                return speaker_map
                
        except Exception as e:
            logging.error(f"❌ 說話人身份識別失敗: {str(e)}")
            return {speaker: f"參與者 {i+1}" for i, speaker in enumerate(original_speakers)}
    
    def create_notion_page(self, title: str, summary: str, todos: List[str], 
                          segments: List[Dict[str, Any]], speaker_map: Dict[str, str], 
                          google_service, file_id: str = None) -> Tuple[str, str]:
        """
        建立 Notion 頁面
        
        Args:
            title: 頁面標題
            summary: 摘要內容
            todos: 待辦事項列表
            segments: 語音段落列表
            speaker_map: 說話人映射
            google_service: Google 服務實例，用於獲取檔案連結
            file_id: Google Drive 檔案 ID
            
        Returns:
            Tuple[str, str]: (Notion 頁面 ID, 頁面 URL)
        """
        logging.info("🔄 建立 Notion 頁面...")

        if not self.notion_token or not self.notion_database_id:
            raise ValueError("缺少 Notion API 設定 (NOTION_TOKEN 或 NOTION_DATABASE_ID)")

        # --- 準備頁面內容區塊 ---
        blocks = []
        
        # 從檔案名稱提取日期或使用當前日期
        current_date = datetime.now()
        date_str = current_date.strftime("%Y-%m-%d")
        
        # 嘗試從檔案ID提取日期
        if file_id and google_service:
            try:
                file_details = google_service.get_file_details(file_id)
                file_name = file_details.get("name", "")
                extracted_date = google_service.extract_date_from_filename(file_name)
                if extracted_date:
                    date_str = extracted_date
            except Exception as e:
                logging.error(f"❌ 提取檔案日期失敗: {str(e)}")
        
        # 格式化日期
        formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y年%m月%d日")

        # --- 標題區塊 ---
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
        participants = list(set(speaker_map.values()))
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
            
            # 添加待辦事項
            for todo in todos:
                blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": todo}}],
                        "checked": False
                    }
                })
            
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # --- 準備完整逐字稿 ---
        full_transcript = ""
        for segment in segments:
            speaker = segment["speaker"]
            text = segment["text"]
            timestamp = segment.get("timestamp", "")
            line = f"{timestamp} {speaker}: {text}" if timestamp else f"{speaker}: {text}"
            full_transcript += f"{line}\n"

        # --- 生成詳細筆記 ---
        comprehensive_notes = self.generate_comprehensive_notes(full_transcript)
        
        # --- 添加詳細筆記區塊 ---
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📊 詳細筆記"}}]
            }
        })
        
        # 使用 Notion 格式化器處理筆記
        note_blocks = self.notion_formatter.process_note_format_for_notion(comprehensive_notes)
        
        # API 限制：每次請求最多 100 個區塊
        MAX_BLOCKS_PER_REQUEST = 90
        
        # 檢查區塊數量
        base_blocks_count = len(blocks)
        available_slots = MAX_BLOCKS_PER_REQUEST - base_blocks_count
        
        if len(note_blocks) > available_slots:
            blocks.extend(note_blocks[:available_slots])
            remaining_note_blocks = note_blocks[available_slots:]
        else:
            blocks.extend(note_blocks)
            remaining_note_blocks = []
        
        # 添加分隔線
        remaining_note_blocks.append({"object": "block", "type": "divider", "divider": {}})

        # --- 添加音檔連結 (如果有) ---
        if file_id and google_service:
            try:
                file_details = google_service.get_file_details(file_id)
                file_name = file_details.get("name", "音頻檔案")
                file_link = file_details.get("webViewLink", f"https://drive.google.com/file/d/{file_id}")
                
                remaining_note_blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "🎵 原始錄音"}}]
                    }
                })
                
                remaining_note_blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": "📁 錄音檔案: "}},
                            {"type": "text", "text": {"content": file_name, "link": {"url": file_link}}}
                        ]
                    }
                })
                
                remaining_note_blocks.append({"object": "block", "type": "divider", "divider": {}})
            except Exception as e:
                logging.error(f"❌ 獲取檔案連結失敗: {str(e)}")
        
        # --- 完整逐字稿區塊 ---
        remaining_note_blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "🎙️ 完整逐字稿"}}]
            }
        })
        
        # 使用 toggle 區塊包裝逐字稿
        transcript_blocks = []
        
        # 添加帶時間戳的逐字稿
        for segment in segments:
            speaker = segment["speaker"]
            text = segment["text"]
            timestamp = segment.get("timestamp", "")
            
            # 如果有時間戳，加入時間戳
            content = f"{timestamp} **{speaker}**: {text}" if timestamp else f"**{speaker}**: {text}"
            
            transcript_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            })
        
        # 分批添加逐字稿，使用 toggle 區塊
        MAX_TOGGLE_CHILDREN = 90
        
        # 分割 transcript_blocks 為多個 toggle 區塊
        for i in range(0, len(transcript_blocks), MAX_TOGGLE_CHILDREN):
            toggle_children = []
            end_idx = min(i + MAX_TOGGLE_CHILDREN, len(transcript_blocks))
            
            # 只在第一個 toggle 區塊添加說明
            if i == 0:
                toggle_children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": "此區塊包含完整逐字稿"}}]
                    }
                })
                toggle_children.append({"object": "block", "type": "divider", "divider": {}})
            
            # 添加本批次的 transcript_blocks
            toggle_children.extend(transcript_blocks[i:end_idx])
            
            # 建立 toggle 區塊
            toggle_title = "點擊展開完整逐字稿"
            if len(transcript_blocks) > MAX_TOGGLE_CHILDREN:
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
        
        # Notion API 請求設定
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

        try:
            # 建立主頁面
            data = {
                "parent": {"database_id": self.notion_database_id},
                "properties": {
                    "title": {
                        "title": [{"text": {"content": page_title}}]
                    }
                },
                "children": blocks
            }
            
            logging.info(f"- 建立 Notion 頁面 (包含 {len(blocks)} 個區塊)")
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            page_id = result["id"]
            page_url = result.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")
            
            # 若有剩餘區塊，分批添加
            if remaining_note_blocks:
                total_batches = (len(remaining_note_blocks) + MAX_BLOCKS_PER_REQUEST - 1) // MAX_BLOCKS_PER_REQUEST
                logging.info(f"- 分批添加剩餘內容 (共 {len(remaining_note_blocks)} 個區塊，分 {total_batches} 批)")
                
                # 添加剩餘區塊
                for i in range(0, len(remaining_note_blocks), MAX_BLOCKS_PER_REQUEST):
                    end_idx = min(i + MAX_BLOCKS_PER_REQUEST, len(remaining_note_blocks))
                    batch_num = i // MAX_BLOCKS_PER_REQUEST + 1
                    
                    # 添加重試邏輯
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            logging.info(f"- 添加第 {batch_num}/{total_batches} 批 (嘗試 {retry+1}/{max_retries})")
                            
                            batch_response = requests.patch(
                                f"https://api.notion.com/v1/blocks/{page_id}/children",
                                headers=headers,
                                json={"children": remaining_note_blocks[i:end_idx]},
                                timeout=30
                            )
                            batch_response.raise_for_status()
                            logging.info(f"✅ 第 {batch_num}/{total_batches} 批添加成功")
                            break
                            
                        except Exception as e:
                            if retry < max_retries - 1:
                                wait_time = 2 ** retry  # 指數退避
                                logging.warning(f"⚠️ 第 {batch_num} 批添加失敗，{wait_time} 秒後重試: {str(e)}")
                                time.sleep(wait_time)
                            else:
                                logging.error(f"❌ 第 {batch_num} 批添加失敗: {str(e)}")
                    
                    # 批次之間短暫暫停，避免 rate limit
                    if i + MAX_BLOCKS_PER_REQUEST < len(remaining_note_blocks):
                        time.sleep(1)
            
            logging.info(f"✅ Notion 頁面建立完成 (URL: {page_url})")
            return page_id, page_url
            
        except requests.exceptions.RequestException as e:
            # 詳細記錄 API 錯誤
            error_message = f"Notion API 請求失敗: {str(e)}"
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
                try:
                    error_data = e.response.json()
                    error_message = f"Notion API 錯誤 ({status_code}): {error_data}"
                except:
                    error_message = f"Notion API 錯誤 ({status_code}): {e.response.text}"
            
            logging.error(f"❌ {error_message}")
            raise ValueError(error_message)
            
        except Exception as e:
            logging.error(f"❌ 建立 Notion 頁面時發生未知錯誤: {str(e)}")
            raise
    
    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """
        從檔案名稱中提取日期
        
        Args:
            filename: 檔案名稱
        
        Returns:
            日期字串 (YYYY-MM-DD) 或 None
        """
        # 嘗試匹配 REC_YYYYMMDD_HHMMSS 格式
        pattern1 = r'REC_(\d{8})_\d+'
        match1 = re.search(pattern1, filename)
        if match1:
            date_str = match1.group(1)
            try:
                date_obj = datetime.strptime(date_str, '%Y%m%d')
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        # 嘗試匹配 [YYYY-MM-DD] 格式
        pattern2 = r'\[(\d{4}-\d{2}-\d{2})\]'
        match2 = re.search(pattern2, filename)
        if match2:
            return match2.group(1)
        
        # 嘗試匹配 YYYY-MM-DD 格式
        pattern3 = r'(\d{4}-\d{2}-\d{2})'
        match3 = re.search(pattern3, filename)
        if match3:
            return match3.group(1)
        
        # 嘗試匹配 YYYY/MM/DD 格式
        pattern4 = r'(\d{4})[/\-](\d{2})[/\-](\d{2})'
        match4 = re.search(pattern4, filename)
        if match4:
            y, m, d = match4.groups()
            return f"{y}-{m}-{d}"
        
        return None
