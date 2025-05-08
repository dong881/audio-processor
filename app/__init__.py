import os
import logging
from flask import Flask
from dotenv import load_dotenv

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
    
    # 導入路由模組
    from app.routes.auth_routes import auth_bp
    from app.routes.main_routes import main_bp
    from app.routes.api_routes import api_bp
    
    # 註冊藍圖
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    
    return app 