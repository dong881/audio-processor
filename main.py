import os
import logging
from app import create_app
from app.services.audio_processor import AudioProcessor

def initialize_processor():
    """初始化AudioProcessor並處理可能的錯誤"""
    try:
        # 檢查必要目錄是否存在
        credentials_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials")
        if not os.path.exists(credentials_dir):
            os.makedirs(credentials_dir)
            logging.info(f"✅ 已創建憑證目錄: {credentials_dir}")
        
        # 初始化 AudioProcessor
        processor = AudioProcessor(max_workers=3)
        logging.info("✅ AudioProcessor 初始化成功")
        return processor
    except Exception as e:
        logging.error(f"❌ AudioProcessor 初始化失敗: {str(e)}")
        # 在失敗時返回一個有限功能的處理器實例
        processor = AudioProcessor(max_workers=1)
        processor.drive_service = None  # 確保標記為未初始化
        return processor

# 初始化 AudioProcessor (全域實例，供所有模組使用)
processor = initialize_processor()

# 建立 Flask 應用實例
app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    logging.info(f"🚀 啟動伺服器於 port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True) 