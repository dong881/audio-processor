import os
import re
import json
import logging
import tempfile
import shutil
from typing import Dict, List, Tuple, Optional, Any

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

class GoogleService:
    """
    Google API 服務類別
    處理與 Google Drive 相關的操作，包括列出、下載、上傳和重命名檔案等
    """

    def __init__(self):
        self.credentials = None
        self.drive_service = None
        self._initialize_service()
    
    def _initialize_service(self) -> None:
        """
        初始化 Google API 服務
        嘗試使用服務帳號或 OAuth 憑證
        """
        try:
            # 檢查是否使用服務帳號
            if os.getenv("USE_SERVICE_ACCOUNT") == "true":
                service_account_path = os.getenv("GOOGLE_SA_JSON_PATH")
                if service_account_path and os.path.exists(service_account_path):
                    self.credentials = service_account.Credentials.from_service_account_file(
                        service_account_path,
                        scopes=['https://www.googleapis.com/auth/drive.file',
                               'https://www.googleapis.com/auth/drive.metadata.readonly']
                    )
                    logging.info("✅ 已使用服務帳號建立 Google API 憑證")
                else:
                    logging.warning("⚠️ 找不到服務帳號 JSON 檔案，無法初始化 Google API 服務")
            
            # 若沒有憑證，暫不建立服務
            if self.credentials:
                self.drive_service = build('drive', 'v3', credentials=self.credentials)
                logging.info("✅ Google Drive API 服務已初始化")
            else:
                logging.warning("⚠️ Google Drive API 服務初始化失敗。用戶需要先登入才能使用文件功能。")
            
        except Exception as e:
            logging.error(f"❌ Google 服務初始化錯誤: {str(e)}", exc_info=True)
    
    def set_credentials(self, credentials: Credentials) -> None:
        """
        設定 OAuth 憑證並建立服務
        
        Args:
            credentials: Google OAuth 憑證
        """
        try:
            self.credentials = credentials
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            logging.info("✅ 已使用 OAuth 憑證重新建立 Google API 服務")
        except Exception as e:
            logging.error(f"❌ 使用 OAuth 憑證建立服務失敗: {str(e)}", exc_info=True)
            raise ValueError(f"無法使用提供的憑證建立 Google 服務: {str(e)}")
    
    def list_files(self, folder_name: str = 'WearNote_Recordings', 
                   page_token: Optional[str] = None, 
                   page_size: int = 30) -> Dict[str, Any]:
        """
        列出指定資料夾中的檔案
        
        Args:
            folder_name: 要搜尋的資料夾名稱
            page_token: 分頁令牌，用於獲取下一頁結果
            page_size: 每頁顯示的檔案數量
            
        Returns:
            包含檔案列表和下一頁令牌的字典
        """
        if not self.drive_service:
            raise ValueError("Google Drive 服務未初始化，請先登入")
        
        try:
            # 先查詢資料夾 ID
            folder_query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            folder_results = self.drive_service.files().list(
                q=folder_query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            folders = folder_results.get('files', [])
            
            if not folders:
                raise ValueError(f"找不到名為 '{folder_name}' 的資料夾")
            
            folder_id = folders[0]['id']
            
            # 查詢資料夾內的檔案
            query = f"'{folder_id}' in parents and trashed = false"
            
            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType, createdTime, size)',
                pageToken=page_token,
                pageSize=page_size
            ).execute()
            
            files = results.get('files', [])
            next_page_token = results.get('nextPageToken')
            
            # 處理檔案資訊
            formatted_files = []
            for file in files:
                # 取得檔案類型
                mime_type = file.get('mimeType', '')
                file_type = 'unknown'
                icon = '📄'
                
                if 'audio' in mime_type:
                    file_type = 'audio'
                    icon = '🎵'
                elif mime_type == 'application/pdf':
                    file_type = 'pdf'
                    icon = '📑'
                elif 'image' in mime_type:
                    file_type = 'image'
                    icon = '🖼️'
                elif 'video' in mime_type:
                    file_type = 'video'
                    icon = '🎬'
                elif 'document' in mime_type or 'text' in mime_type:
                    file_type = 'document'
                    icon = '📝'
                
                # 格式化檔案大小
                size = file.get('size')
                formatted_size = 'N/A'
                if size:
                    size_int = int(size)
                    if size_int < 1024:
                        formatted_size = f"{size_int} B"
                    elif size_int < 1024 * 1024:
                        formatted_size = f"{size_int // 1024} KB"
                    else:
                        formatted_size = f"{size_int // (1024 * 1024)} MB"
                
                # 格式化日期
                created_time = file.get('createdTime', '')
                formatted_date = 'N/A'
                if created_time:
                    # 轉換 ISO 格式為 YYYY-MM-DD
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                        formatted_date = dt.strftime('%Y-%m-%d')
                    except:
                        formatted_date = created_time
                
                formatted_files.append({
                    'id': file.get('id'),
                    'name': file.get('name'),
                    'mimeType': mime_type,
                    'type': file_type,
                    'icon': icon,
                    'size': size,
                    'formatted_size': formatted_size,
                    'created_time': created_time,
                    'formatted_date': formatted_date
                })
            
            return {
                'files': formatted_files,
                'nextPageToken': next_page_token
            }
            
        except Exception as e:
            logging.error(f"❌ 列出 Google Drive 檔案失敗: {str(e)}", exc_info=True)
            raise

    def download_file(self, file_id: str) -> Tuple[str, str]:
        """
        從 Google Drive 下載檔案到臨時目錄
        
        Args:
            file_id: Google Drive 檔案 ID
            
        Returns:
            tuple: (本地檔案路徑, 臨時目錄路徑)
        """
        if not self.drive_service:
            raise ValueError("Google Drive 服務未初始化，請先登入")
        
        try:
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
            
            logging.info(f"✅ 檔案下載完成: {safe_file_name}")
            return local_path, temp_dir
            
        except Exception as e:
            logging.error(f"❌ 下載檔案失敗: {str(e)}", exc_info=True)
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise
    
    def rename_file(self, file_id: str, new_name: str) -> bool:
        """
        重命名 Google Drive 上的檔案
        
        Args:
            file_id: 檔案 ID
            new_name: 新檔名
            
        Returns:
            布林值，表示操作是否成功
        """
        if not self.drive_service:
            raise ValueError("Google Drive 服務未初始化，請先登入")
        
        try:
            self.drive_service.files().update(
                fileId=file_id,
                body={'name': new_name}
            ).execute()
            logging.info(f"✅ 已重命名檔案為: {new_name}")
            return True
        except Exception as e:
            logging.error(f"❌ 重命名檔案失敗: {str(e)}", exc_info=True)
            return False
    
    def create_folder(self, folder_name: str) -> Optional[str]:
        """
        在 Google Drive 根目錄建立資料夾
        
        Args:
            folder_name: 要建立的資料夾名稱
            
        Returns:
            新建資料夾的 ID，失敗則返回 None
        """
        if not self.drive_service:
            raise ValueError("Google Drive 服務未初始化，請先登入")
        
        try:
            # 檢查資料夾是否已存在
            query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                logging.info(f"資料夾 '{folder_name}' 已存在，ID: {folders[0]['id']}")
                return folders[0]['id']
            
            # 建立新資料夾
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logging.info(f"✅ 已建立資料夾 '{folder_name}'，ID: {folder_id}")
            return folder_id
            
        except Exception as e:
            logging.error(f"❌ 建立資料夾失敗: {str(e)}", exc_info=True)
            return None
    
    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """
        從檔案名稱中提取日期，支援多種格式
        
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
                from datetime import datetime
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
        
    def get_file_details(self, file_id: str) -> Dict[str, Any]:
        """
        獲取檔案詳細資訊
        
        Args:
            file_id: Google Drive 檔案 ID
            
        Returns:
            包含檔案資訊的字典
        """
        if not self.drive_service:
            raise ValueError("Google Drive 服務未初始化，請先登入")
        
        try:
            file_meta = self.drive_service.files().get(
                fileId=file_id, 
                fields="name,mimeType,size,createdTime,modifiedTime,webViewLink"
            ).execute()
            
            return file_meta
        except Exception as e:
            logging.error(f"❌ 獲取檔案詳細資訊失敗: {str(e)}", exc_info=True)
            raise
