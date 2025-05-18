import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from app.utils.constants import JOB_STATUS
import google.auth.transport.requests
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_login import login_required

# 建立藍圖
api_bp = Blueprint('api', __name__)

# 初始化緩存
cache = Cache()

# 初始化限流器
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://redis:6379/0"
)

def init_rate_limiter(app):
    limiter.init_app(app)
    cache.init_app(app)

# 緩存裝飾器
def cache_with_timeout(timeout=30):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            cache_key = f"{request.path}:{request.query_string.decode()}"
            rv = cache.get(cache_key)
            if rv is not None:
                return rv
            rv = f(*args, **kwargs)
            cache.set(cache_key, rv, timeout=timeout)
            return rv
        return decorated_function
    return decorator

# 錯誤處理裝飾器
def handle_api_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logging.error(f"API Error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({
                "success": False,
                "error": "Internal server error",
                "timestamp": datetime.now().isoformat()
            }), 500
    return decorated_function

@api_bp.route('/health', methods=['GET'])
@limiter.limit("60 per minute")
@cache_with_timeout(timeout=10)
@handle_api_errors
def health_check():
    """健康檢查端點"""
    processor = current_app.audio_processor
    with processor.jobs_lock:
        all_jobs = {job_id: job.copy() for job_id, job in processor.jobs.items()}
    
    active_job_count = len([j for j in all_jobs.values() 
                          if j['status'] in [JOB_STATUS['PENDING'], JOB_STATUS['PROCESSING']]])
    
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "active_jobs": active_job_count
    })

@api_bp.route('/process', methods=['POST'])
@handle_api_errors
def process_audio_endpoint():
    """非同步處理音檔的 API 端點，立即返回工作 ID"""
    processor = current_app.audio_processor
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "無效的請求內容"}), 400

    file_id = data.get('file_id')
    if not file_id:
        return jsonify({"success": False, "error": "缺少 file_id 參數"}), 400

    attachment_file_ids = data.get('attachment_file_ids')

    if attachment_file_ids is not None:
        if not isinstance(attachment_file_ids, list):
            return jsonify({'success': False, 'error': 'attachment_file_ids must be a list'}), 400
        if not all(isinstance(item, str) for item in attachment_file_ids):
            return jsonify({'success': False, 'error': 'All items in attachment_file_ids must be strings'}), 400
        if not attachment_file_ids:
            attachment_file_ids = None

    job_id = processor.process_file_async(file_id, attachment_file_ids=attachment_file_ids)
    
    return jsonify({
        "success": True,
        "message": "工作已提交，正在後台處理",
        "job_id": job_id
    })

@api_bp.route('/job/<job_id>', methods=['GET'])
@limiter.limit("60 per minute")
@cache_with_timeout(timeout=5)
@handle_api_errors
def get_job_status_endpoint(job_id):
    """獲取工作狀態的 API 端點"""
    processor = current_app.audio_processor
    job_status = processor.get_job_status(job_id)
    
    if 'error' in job_status:
        return jsonify({"success": False, "error": job_status['error']}), 404
        
    return jsonify({
        "success": True,
        "job": job_status
    })

@api_bp.route('/jobs', methods=['GET'])
@login_required
def get_jobs_endpoint():
    """獲取所有工作狀態"""
    try:
        jobs = current_app.audio_processor.get_all_jobs()
        return jsonify({
            'status': 'success',
            'data': {
                'jobs': jobs,
                'total': len(jobs)
            }
        })
    except Exception as e:
        logging.error(f"獲取工作列表失敗: {e}")
        return jsonify({
            'status': 'error',
            'message': f'獲取工作列表失敗: {str(e)}'
        }), 500

@api_bp.route('/jobs/active', methods=['GET'])
@login_required
def get_active_jobs_endpoint():
    """獲取所有活動中的工作狀態"""
    try:
        jobs = current_app.audio_processor.get_active_jobs()
        return jsonify({
            'status': 'success',
            'data': {
                'jobs': jobs,
                'total': len(jobs)
            }
        })
    except Exception as e:
        logging.error(f"獲取活動工作列表失敗: {e}")
        return jsonify({
            'status': 'error',
            'message': f'獲取活動工作列表失敗: {str(e)}'
        }), 500

@api_bp.route('/drive/files')
@handle_api_errors
def drive_files():
    """獲取Google Drive檔案列表"""
    if not session.get('authenticated', False):
        return jsonify({'success': False, 'error': '未認證'}), 401

    processor = current_app.audio_processor
    if processor.oauth_drive_service is None:
        credentials_dict = session.get('credentials')
        if not credentials_dict:
            return jsonify({'success': False, 'error': '未找到憑證信息'}), 401

        from google.oauth2.credentials import Credentials
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )

        if credentials.expired:
            credentials.refresh(google.auth.transport.requests.Request())
            session['credentials']['token'] = credentials.token

        processor.initialize_oauth_service(credentials)

    recordings_folder_name = request.args.get('recordingsFolderName')
    pdf_folder_name = request.args.get('pdfFolderName')
    recordings_filter_active = request.args.get('recordingsFilter') == 'enabled'
    pdf_filter_active = request.args.get('pdfFilter') == 'enabled'

    audio_files_list = []
    pdf_files_list = []

    # 1. Fetch Audio Files
    base_audio_query = "trashed = false and mimeType contains 'audio/'"
    if recordings_filter_active and recordings_folder_name:
        recordings_folder_id = processor.find_folder_id_by_path(recordings_folder_name)
        if recordings_folder_id:
            audio_query = f"{base_audio_query} and '{recordings_folder_id}' in parents"
            audio_files_list = processor.list_drive_files(query=audio_query)
    else:
        audio_files_list = processor.list_drive_files(query=base_audio_query)

    # 2. Fetch PDF Files
    base_pdf_query = "trashed = false and mimeType = 'application/pdf'"
    if pdf_filter_active and pdf_folder_name:
        pdf_folder_id = processor.find_folder_id_by_path(pdf_folder_name)
        if pdf_folder_id:
            pdf_query = f"{base_pdf_query} and '{pdf_folder_id}' in parents"
            pdf_files_list = processor.list_drive_files(query=pdf_query)
    else:
        pdf_files_list = processor.list_drive_files(query=base_pdf_query)

    all_files = audio_files_list + pdf_files_list
    all_files.sort(key=lambda x: x.get('modifiedTime', ''), reverse=True)

    return jsonify({
        'success': True,
        'files': all_files,
        'count': len(all_files)
    })

@api_bp.route('/job/<job_id>/stop', methods=['POST'])
@login_required
def stop_job_endpoint(job_id):
    """停止指定的任務"""
    try:
        if current_app.audio_processor.stop_job(job_id):
            return jsonify({
                'status': 'success',
                'message': '任務已停止'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '無法停止任務：任務不存在或已完成'
            }), 400
    except Exception as e:
        logging.error(f"停止任務失敗: {e}")
        return jsonify({
            'status': 'error',
            'message': f'停止任務失敗: {str(e)}'
        }), 500