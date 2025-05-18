import os
import logging
from app import create_app
from app.services.audio_processor import AudioProcessor
import atexit

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

# 初始化音頻處理器
audio_processor = initialize_processor()

# 註冊關閉函數
def cleanup():
    logging.info("正在關閉應用程序...")
    audio_processor.shutdown_executor()
    logging.info("應用程序已關閉")

atexit.register(cleanup)

# 創建應用程序實例
app = create_app(audio_processor)

if __name__ == '__main__':
    # 設置日誌
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 啟動應用程序
    app.run(host='0.0.0.0', port=5000, debug=True) 