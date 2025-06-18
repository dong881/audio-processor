import os
import json
import logging
import redis
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
import google.auth.transport.requests
from typing import Optional, Dict, Any

class CredentialManager:
    """憑證管理器，負責 OAuth 憑證的持久化存儲和刷新"""
    
    def __init__(self):
        self.redis_client = None
        self.init_redis()
        
    def init_redis(self):
        """初始化 Redis 連接"""
        try:
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_db = int(os.getenv('REDIS_DB', 0))
            
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # 測試連接
            self.redis_client.ping()
            logging.info("✅ Redis 連接成功")
            
        except Exception as e:
            logging.error(f"❌ Redis 連接失敗: {e}")
            self.redis_client = None
    
    def _get_credential_key(self, user_id: str) -> str:
        """生成憑證存儲的 Redis key"""
        return f"oauth_credentials:{user_id}"
    
    def save_credentials(self, user_id: str, credentials: Credentials) -> bool:
        """保存 OAuth 憑證到 Redis"""
        if not self.redis_client:
            logging.error("Redis 未連接，無法保存憑證")
            return False
            
        try:
            # 準備憑證數據
            cred_data = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes,
                'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
                'id_token': credentials.id_token if hasattr(credentials, 'id_token') else None,
                'saved_at': datetime.now().isoformat()
            }
            
            # 存儲到 Redis，設置過期時間為 30 天
            key = self._get_credential_key(user_id)
            self.redis_client.setex(
                key, 
                timedelta(days=30), 
                json.dumps(cred_data)
            )
            
            logging.info(f"✅ 用戶 {user_id} 的憑證已保存到 Redis")
            return True
            
        except Exception as e:
            logging.error(f"❌ 保存憑證失敗: {e}")
            return False
    
    def load_credentials(self, user_id: str) -> Optional[Credentials]:
        """從 Redis 載入 OAuth 憑證"""
        if not self.redis_client:
            logging.error("Redis 未連接，無法載入憑證")
            return None
            
        try:
            key = self._get_credential_key(user_id)
            cred_json = self.redis_client.get(key)
            
            if not cred_json:
                logging.info(f"用戶 {user_id} 沒有已保存的憑證")
                return None
            
            cred_data = json.loads(cred_json)
            
            # 重建憑證對象
            credentials = Credentials(
                token=cred_data['token'],
                refresh_token=cred_data['refresh_token'],
                token_uri=cred_data['token_uri'],
                client_id=cred_data['client_id'],
                client_secret=cred_data['client_secret'],
                scopes=cred_data['scopes']
            )
            
            # 設置過期時間
            if cred_data.get('expiry'):
                credentials.expiry = datetime.fromisoformat(cred_data['expiry'])
            
            # 設置 id_token
            if cred_data.get('id_token'):
                credentials.id_token = cred_data['id_token']
            
            logging.info(f"✅ 成功載入用戶 {user_id} 的憑證")
            return credentials
            
        except Exception as e:
            logging.error(f"❌ 載入憑證失敗: {e}")
            return None
    
    def refresh_credentials(self, user_id: str, credentials: Credentials) -> Optional[Credentials]:
        """刷新過期的憑證"""
        try:
            if not credentials.refresh_token:
                logging.error("沒有 refresh_token，無法刷新憑證")
                return None
            
            # 檢查憑證是否需要刷新
            if credentials.expired:
                logging.info(f"用戶 {user_id} 的憑證已過期，正在刷新...")
                
                # 刷新憑證
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
                
                # 保存刷新後的憑證
                if self.save_credentials(user_id, credentials):
                    logging.info(f"✅ 用戶 {user_id} 的憑證刷新並保存成功")
                    return credentials
                else:
                    logging.error(f"❌ 憑證刷新成功但保存失敗")
                    return credentials  # 仍然返回刷新後的憑證
            else:
                logging.info(f"用戶 {user_id} 的憑證仍然有效")
                return credentials
                
        except Exception as e:
            logging.error(f"❌ 刷新憑證失敗: {e}")
            return None
    
    def get_valid_credentials(self, user_id: str) -> Optional[Credentials]:
        """獲取有效的憑證（自動刷新如果需要）"""
        credentials = self.load_credentials(user_id)
        
        if not credentials:
            return None
        
        # 如果憑證過期或即將過期（5分鐘內），嘗試刷新
        if credentials.expired or (
            credentials.expiry and 
            credentials.expiry < datetime.utcnow() + timedelta(minutes=5)
        ):
            credentials = self.refresh_credentials(user_id, credentials)
        
        return credentials
    
    def delete_credentials(self, user_id: str) -> bool:
        """刪除用戶的憑證"""
        if not self.redis_client:
            return False
            
        try:
            key = self._get_credential_key(user_id)
            result = self.redis_client.delete(key)
            logging.info(f"✅ 用戶 {user_id} 的憑證已刪除")
            return bool(result)
            
        except Exception as e:
            logging.error(f"❌ 刪除憑證失敗: {e}")
            return False
    
    def extend_credential_expiry(self, user_id: str, days: int = 30) -> bool:
        """延長憑證在 Redis 中的存儲時間"""
        if not self.redis_client:
            return False
            
        try:
            key = self._get_credential_key(user_id)
            result = self.redis_client.expire(key, timedelta(days=days))
            if result:
                logging.info(f"✅ 用戶 {user_id} 的憑證存儲時間延長至 {days} 天")
            return bool(result)
            
        except Exception as e:
            logging.error(f"❌ 延長憑證存儲時間失敗: {e}")
            return False
