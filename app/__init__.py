import os
import logging
from flask import Flask, session, request
from dotenv import load_dotenv

from app.services.credential_manager import CredentialManager

# 載入環境變數
load_dotenv()

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_app():
    """建立和設定Flask應用"""
    app = Flask(__name__, 
                static_folder='../static',
                template_folder='../templates')
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev_secret_key')
    
    # *** 新增：初始化憑證管理器 ***
    credential_manager = CredentialManager()
    
    @app.before_request
    def restore_credentials():
        """在每個請求前嘗試恢復憑證"""
        # 跳過靜態文件和特定路由
        if (request.endpoint and 
            (request.endpoint.startswith('static') or 
             request.endpoint in ['auth.login', 'auth.auth_google', 'auth.auth_callback'])):
            return
            
        # 如果已經有 session 認證，不需要恢復
        if session.get('authenticated') and session.get('credentials'):
            return
            
        # 嘗試從 Redis 恢復憑證
        user_info = session.get('user_info', {})
        user_id = user_info.get('id')
        
        if user_id and user_id != 'unknown':
            try:
                valid_credentials = credential_manager.get_valid_credentials(user_id)
                if valid_credentials:
                    logging.info(f"🔄 為用戶 {user_id} 恢復憑證")
                    
                    # 恢復 session
                    session['authenticated'] = True
                    session['credentials'] = {
                        'token': valid_credentials.token,
                        'refresh_token': valid_credentials.refresh_token,
                        'token_uri': valid_credentials.token_uri,
                        'client_id': valid_credentials.client_id,
                        'client_secret': valid_credentials.client_secret,
                        'scopes': valid_credentials.scopes,
                        'id_token': valid_credentials.id_token if hasattr(valid_credentials, 'id_token') else None
                    }
                    
                    # 設置到 AudioProcessor
                    from main import processor
                    if processor is not None:
                        processor.set_oauth_credentials(valid_credentials)
                        logging.info(f"✅ 為用戶 {user_id} 恢復 AudioProcessor 憑證")
                        
            except Exception as e:
                logging.error(f"恢復用戶 {user_id} 憑證時出錯: {e}")
    
    # 導入路由模組
    from app.routes.auth_routes import auth_bp
    from app.routes.main_routes import main_bp
    from app.routes.api_routes import api_bp
    
    # 註冊藍圖
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')  # 添加 /api 前綴
    
    return app