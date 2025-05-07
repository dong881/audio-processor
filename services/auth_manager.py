import os
import json
import logging
from typing import Optional, Dict, Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow


class AuthManager:
    """
    管理 Google OAuth 認證流程的類別
    負責處理獲取授權、刷新 token 和提供認證資訊
    """

    def __init__(self):
        # 設定 OAuth 流程所需的客戶端資訊
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5000/api/auth/google/callback")
        self.scopes = [
            'https://www.googleapis.com/auth/userinfo.profile',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/drive.metadata.readonly'
        ]
        self.flow = None
        self._create_flow()

    def _create_flow(self) -> None:
        """
        建立 OAuth 流程
        """
        if not self.client_id or not self.client_secret:
            logging.warning("未設定 Google OAuth 憑證，某些功能可能無法正常運作")
            return

        try:
            # 建立 OAuth2 流程
            self.flow = Flow.from_client_config(
                client_config={
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.redirect_uri],
                    }
                },
                scopes=self.scopes
            )
            self.flow.redirect_uri = self.redirect_uri
        except Exception as e:
            logging.error(f"建立 OAuth 流程時發生錯誤: {str(e)}")
            self.flow = None

    def get_authorization_url(self) -> str:
        """
        獲取 Google 授權 URL
        
        Returns:
            授權 URL 字串
        """
        if not self.flow:
            self._create_flow()
            if not self.flow:
                raise ValueError("無法建立 OAuth 流程")
        
        # 生成授權 URL
        auth_url, _ = self.flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        return auth_url
    
    def exchange_code(self, code: str) -> Credentials:
        """
        用授權碼換取 OAuth2 憑證
        
        Args:
            code: 從 Google OAuth 回調獲得的授權碼
            
        Returns:
            Google OAuth2 憑證對象
        """
        if not self.flow:
            self._create_flow()
            if not self.flow:
                raise ValueError("無法建立 OAuth 流程")

        # 交換授權碼獲取憑證
        self.flow.fetch_token(code=code)
        credentials = self.flow.credentials
        
        return credentials
    
    def credentials_from_json(self, json_string: str) -> Credentials:
        """
        從 JSON 字串還原憑證對象
        
        Args:
            json_string: 包含憑證資訊的 JSON 字串
            
        Returns:
            Google OAuth2 憑證對象
        """
        json_data = json.loads(json_string)
        return Credentials(
            token=json_data['token'],
            refresh_token=json_data.get('refresh_token'),
            token_uri=json_data['token_uri'],
            client_id=json_data['client_id'],
            client_secret=json_data['client_secret'],
            scopes=json_data['scopes']
        )
    
    def is_token_valid(self, credentials: Optional[Credentials]) -> bool:
        """
        檢查憑證是否有效
        
        Args:
            credentials: 要檢查的憑證
            
        Returns:
            布林值，表示憑證是否有效
        """
        if not credentials:
            return False
        
        # 簡單檢查 token 是否存在
        # 實際應用中可能需要檢查過期時間
        return bool(credentials.token)
