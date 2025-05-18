import os
import logging
from flask import Flask, render_template, request
from dotenv import load_dotenv
from app.extensions import db, migrate
from app.routes.api_routes import init_rate_limiter

# 載入環境變數
load_dotenv()

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', mode='a')
    ]
)

# 設置第三方庫的日誌級別
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('google').setLevel(logging.WARNING)

def create_app(audio_processor=None):
    """創建並配置 Flask 應用程序"""
    app = Flask(__name__, 
                static_folder='static',
                template_folder='templates',
                static_url_path='/static')
    
    # 配置
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev_secret_key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # 配置緩存
    app.config['CACHE_TYPE'] = 'simple'
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300
    
    # 初始化擴展
    db.init_app(app)
    migrate.init_app(app, db)
    
    # 初始化限流器和緩存
    init_rate_limiter(app)
    
    # 導入路由模組
    from app.routes.auth_routes import auth_bp
    from app.routes.main_routes import main_bp
    from app.routes.api_routes import api_bp
    
    # 註冊藍圖
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # 設置音頻處理器
    if audio_processor:
        app.audio_processor = audio_processor
    else:
        from app.services.audio_processor import AudioProcessor
        app.audio_processor = AudioProcessor(max_workers=3)
    
    # 添加錯誤處理
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.error(f'Page not found: {request.url}')
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Server Error: {error}')
        return render_template('500.html'), 500
    
    return app 