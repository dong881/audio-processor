import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from app.utils.constants import JOB_STATUS

# 建立藍圖
api_bp = Blueprint('api', __name__)

# 假設我們在此處獲取processor實例
# 實際應用中會在main.py中初始化並導入
from main import processor

@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    # Create a consistent snapshot of jobs while holding the lock
    with processor.jobs_lock:
        # Create a full copy of the jobs dictionary to ensure a consistent snapshot
        all_jobs = {job_id: job.copy() for job_id, job in processor.jobs.items()}
    
    # Count active jobs from the snapshot (outside the lock)
    active_job_count = len([j for j in all_jobs.values() 
                          if j['status'] in [JOB_STATUS['PENDING'], JOB_STATUS['PROCESSING']]])
    
    # Log the count for debugging
    logging.debug(f"Health check: Found {active_job_count} active jobs at {datetime.now().isoformat()}")
    
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "active_jobs": active_job_count
    })

@api_bp.route('/process', methods=['POST'])
def process_audio_endpoint():
    """非同步處理音檔的 API 端點，立即返回工作 ID"""
    try:
        data = request.json

        if not data:
            return jsonify({"success": False, "error": "無效的請求內容"}), 400

        file_id = data.get('file_id')
        
        # 支援多個與單個附件ID
        attachment_file_id = data.get('attachment_file_id')
        attachment_file_ids = data.get('attachment_file_ids')

        if not file_id:
            return jsonify({"success": False, "error": "缺少 file_id 參數"}), 400

        # 處理附件ID的不同格式
        if attachment_file_ids:
            # 如果提供了多個附件ID
            if isinstance(attachment_file_ids, list):
                job_id = processor.process_file_async(file_id, attachment_file_ids=attachment_file_ids)
            else:
                return jsonify({"success": False, "error": "attachment_file_ids 參數必須是一個陣列"}), 400
        elif attachment_file_id:
            # 向後兼容：如果提供了單個附件ID
            job_id = processor.process_file_async(file_id, attachment_file_id)
        else:
            # 沒有附件
            job_id = processor.process_file_async(file_id, None)
        
        # 立即返回工作ID
        return jsonify({
            "success": True,
            "message": "工作已提交，正在後台處理",
            "job_id": job_id
        })

    except Exception as e:
        logging.error(f"API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {e}"}), 500

@api_bp.route('/job/<job_id>', methods=['GET'])
def get_job_status_endpoint(job_id):
    """獲取工作狀態的 API 端點"""
    try:
        job_status = processor.get_job_status(job_id)
        
        if 'error' in job_status:
            return jsonify({"success": False, "error": job_status['error']}), 404
            
        return jsonify({
            "success": True,
            "job": job_status
        })
        
    except Exception as e:
        logging.error(f"API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {e}"}), 500

@api_bp.route('/jobs', methods=['GET'])
def get_active_jobs_endpoint():
    """獲取工作列表的 API 端點，可選擇性過濾狀態"""
    try:
        # Get filter status from query parameter, default to show only active jobs
        filter_status = request.args.get('filter', 'active')
        
        # Create a consistent snapshot of jobs while holding the lock
        with processor.jobs_lock:
            # First create a snapshot of all jobs while holding the lock
            all_jobs = {job_id: job.copy() for job_id, job in processor.jobs.items()}
        
        # Process the jobs data outside the lock to minimize lock contention
        if filter_status == 'all':
            # Return all jobs regardless of status
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
            }
        elif filter_status == 'active':
            # Return only pending or processing jobs
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
                if job['status'] in [JOB_STATUS['PENDING'], JOB_STATUS['PROCESSING']]
            }
        elif filter_status == 'completed':
            # Return only completed jobs
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
                if job['status'] == JOB_STATUS['COMPLETED']
            }
        elif filter_status == 'failed':
            # Return only failed jobs
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
                if job['status'] == JOB_STATUS['FAILED']
            }
        else:
            # Invalid filter value
            return jsonify({"success": False, "error": "Invalid filter parameter. Use 'active', 'all', 'completed', or 'failed'"}), 400
            
        # Add job count information
        result = {
            "success": True,
            "active_jobs": jobs_to_return,
            "count": len(jobs_to_return),
            "timestamp": datetime.now().isoformat()
        }
        
        # Log the results for debugging
        logging.debug(f"Jobs endpoint: Found {len(jobs_to_return)} jobs with filter={filter_status} at {datetime.now().isoformat()}")
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {e}"}), 500

@api_bp.route('/drive/files')
def drive_files():
    """獲取Google Drive檔案列表"""
    # 檢查認證
    if not session.get('authenticated', False):
        return jsonify({
            'success': False,
            'error': 'Not authenticated'
        }), 401
    
    try:
        # 使用processor的list_drive_files方法獲取檔案列表
        if processor.oauth_drive_service is None:
            return jsonify({
                'success': False,
                'error': '未完成OAuth認證，請先登入'
            }), 401
            
        # 檢查是否啟用資料夾過濾
        filter_enabled = request.args.get('filter', 'disabled') == 'enabled'
        
        # 執行查詢，獲取音頻檔案和PDF檔案
        files = processor.list_drive_files(
            query="trashed = false and (mimeType contains 'audio/' or mimeType = 'application/pdf')"
        )
        
        if not files:
            logging.info("未找到檔案")
            return jsonify({
                'success': True,
                'files': []
            })
        
        # 獲取檔案資料夾路徑（如果啟用了過濾）
        folder_paths = {}
        if filter_enabled:
            try:
                # 獲取每個檔案的資料夾路徑
                for file in files:
                    file_id = file.get('id')
                    if file_id:
                        folder_path = processor.get_file_folder_path(file_id)
                        folder_paths[file_id] = folder_path
            except Exception as e:
                logging.error(f"獲取資料夾路徑失敗: {str(e)}")
        
        # 整理檔案資訊
        formatted_files = []
        for file in files:
            # 確保檔案具有所有需要的屬性
            file_id = file.get('id')
            formatted_file = {
                'id': file_id,
                'name': file.get('name', '未命名檔案'),
                'mimeType': file.get('mimeType', 'application/octet-stream'),
                'size': file.get('size', 0)
            }
            
            # 添加資料夾路徑（如果有）
            if file_id in folder_paths:
                formatted_file['folderPath'] = folder_paths[file_id]
            
            formatted_files.append(formatted_file)
        
        logging.info(f"找到 {len(formatted_files)} 個檔案")
        return jsonify({
            'success': True,
            'files': formatted_files
        })
        
    except Exception as e:
        logging.error(f"獲取 Google Drive 檔案列表時發生錯誤: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'獲取檔案列表失敗: {str(e)}'
        }), 500