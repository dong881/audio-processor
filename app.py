import os
import logging
import json
import uuid
from typing import Dict, Optional
from datetime import datetime

from flask import Flask, request, jsonify, session, redirect, render_template, Response
from flask_cors import CORS
from dotenv import load_dotenv

# 導入重構後的模組
from core.audio_processor import AudioProcessor
from core.notion_formatter import NotionFormatter
from services.auth_manager import AuthManager
from services.google_auth import GoogleAuth
from services.google_service import GoogleService

# 載入環境變數
load_dotenv()

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('audio_processor.log', encoding='utf-8')
    ]
)

# 建立 Flask app 並配置
app = Flask(__name__)
CORS(app)  # 允許跨域請求
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# 工作狀態常量
JOB_STATUS = {
    'PENDING': 'pending',     # 等待處理
    'PROCESSING': 'processing', # 處理中
    'COMPLETED': 'completed',   # 處理完成
    'FAILED': 'failed'        # 處理失敗
}

# 初始化服務
audio_processor = AudioProcessor.get_instance()
auth_manager = AuthManager()
google_service = GoogleService()

# API 健康檢查端點
@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查 API，確認服務是否正常運行"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'version': os.getenv('APP_VERSION', '1.0.0')
    })

# 音頻處理 API
@app.route('/process', methods=['POST'])
def process_audio_endpoint():
    """接收音頻處理請求，啟動非同步工作流程"""
    try:
        data = request.json
        
        # 驗證請求參數
        if not data or 'file_id' not in data:
            return jsonify({
                'success': False,
                'error': '缺少必要參數: file_id'
            }), 400
            
        # 提取參數
        file_id = data['file_id']
        attachment_file_id = data.get('attachment_file_id')  # 選填
        
        # 啟動非同步處理
        job_id = audio_processor.process_file_async(file_id, attachment_file_id)
        
        return jsonify({
            'success': True,
            'message': '工作已提交，正在後台處理',
            'job_id': job_id
        })
        
    except Exception as e:
        logging.error(f"處理請求時發生錯誤: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"處理過程中發生錯誤: {str(e)}"
        }), 500

# 工作狀態檢查 API
@app.route('/job/<job_id>', methods=['GET'])
def get_job_status_endpoint(job_id):
    """查詢指定工作的狀態"""
    try:
        status = audio_processor.get_job_status(job_id)
        if status:
            return jsonify(status)
        else:
            return jsonify({
                'success': False,
                'error': f"找不到工作 ID: {job_id}"
            }), 404
    except Exception as e:
        logging.error(f"獲取工作狀態時發生錯誤: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"獲取工作狀態時發生錯誤: {str(e)}"
        }), 500

# Google 認證端點
@app.route('/api/auth/google', methods=['GET'])
def google_auth():
    """開始 Google OAuth 流程"""
    try:
        auth_url = auth_manager.get_authorization_url()
        return jsonify({
            'success': True,
            'auth_url': auth_url
        })
    except Exception as e:
        logging.error(f"生成授權 URL 時發生錯誤: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Google 認證回調處理
@app.route('/api/auth/google/callback', methods=['GET'])
def google_auth_callback():
    """處理 Google OAuth 回調"""
    try:
        code = request.args.get('code')
        if not code:
            return jsonify({
                'success': False,
                'error': '缺少授權代碼'
            }), 400
            
        credentials = auth_manager.exchange_code(code)
        # 將憑證存儲到 session 或後續使用
        session['google_credentials'] = credentials.to_json()
        
        # 重定向到前端頁面或回傳成功
        return render_template('callback.html', success=True)
    except Exception as e:
        logging.error(f"OAuth 回調處理時發生錯誤: {str(e)}", exc_info=True)
        return render_template('callback.html', success=False, error=str(e))

# 查詢進行中的工作
@app.route('/jobs', methods=['GET'])
def get_active_jobs_endpoint():
    """獲取所有進行中的工作列表"""
    try:
        jobs = audio_processor.jobs
        active_jobs = {}
        
        for job_id, job_info in jobs.items():
            # 只返回必要資訊，不包括內部狀態
            active_jobs[job_id] = {
                'status': job_info.get('status', JOB_STATUS['PENDING']),
                'progress': job_info.get('progress', 0),
                'file_id': job_info.get('file_id', ''),
                'file_name': job_info.get('file_name', ''),
                'created_at': job_info.get('created_at', ''),
                'message': job_info.get('message', '')
            }
            # 如果有錯誤資訊，也返回錯誤
            if 'error' in job_info:
                active_jobs[job_id]['error'] = job_info['error']
        
        return jsonify({
            'success': True,
            'jobs': active_jobs
        })
    except Exception as e:
        logging.error(f"獲取工作列表時發生錯誤: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f"獲取工作列表時發生錯誤: {str(e)}"
        }), 500

# Google Drive 檔案列表 API
@app.route('/drive/files', methods=['GET'])
def list_drive_files():
    """列出 Google Drive 中的檔案（錄音或附件）"""
    try:
        # 檢查是否已經認證
        if 'google_credentials' not in session:
            return jsonify({
                'success': False,
                'error': '用戶未登入，請先完成 Google 授權'
            }), 401
            
        # 從 query 參數獲取搜索選項
        folder = request.args.get('folder', 'WearNote_Recordings')  # 預設資料夾
        page_token = request.args.get('pageToken')  # 分頁令牌
        
        # 使用憑證
        credentials = auth_manager.credentials_from_json(session['google_credentials'])
        google_service.set_credentials(credentials)
        
        # 獲取檔案列表
        files_response = google_service.list_files(folder_name=folder, page_token=page_token)
        
        return jsonify({
            'success': True,
            'files': files_response.get('files', []),
            'nextPageToken': files_response.get('nextPageToken')
        })
        
    except Exception as e:
        logging.error(f"列出 Drive 檔案時發生錯誤: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 前端頁面路由
@app.route('/', methods=['GET'])
def index():
    """提供主頁面"""
    return render_template('index.html')

@app.route('/login', methods=['GET'])
def login():
    """提供登入頁面"""
    return render_template('login.html')

# 應用入口
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    # 確認模型是否已載入
    # 注意: 只有在非 debug 模式下預先載入模型
    if not debug:
        try:
            audio_processor.load_models()
            logging.info("✅ 模型載入完成，服務準備就緒")
        except Exception as e:
            logging.error(f"❌ 模型載入失敗: {str(e)}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
