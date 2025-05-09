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
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "無效的請求內容"}), 400

        file_id = data.get('file_id')
        
        # attachment_file_id 支援單一 PDF
        attachment_file_id = None
        if 'attachment_file_id' in data:
            attachment_file_id = data['attachment_file_id']
        elif 'attachment_file_ids' in data and isinstance(data['attachment_file_ids'], list) and data['attachment_file_ids']:
            # 只取第一個 PDF
            attachment_file_id = data['attachment_file_ids'][0]

        if not file_id:
            return jsonify({"success": False, "error": "缺少 file_id 參數"}), 400

        # 提交工作
        job_id = processor.process_file_async(file_id, attachment_file_id=attachment_file_id)
        
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
    if not session.get('authenticated', False):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    try:
        if processor.oauth_drive_service is None:
            return jsonify({'success': False, 'error': '未完成OAuth認證，請先登入'}), 401

        # 取得篩選參數
        recordings_folder_name = request.args.get('recordingsFolderName')
        pdf_folder_name = request.args.get('pdfFolderName')
        recordings_filter = request.args.get('recordingsFilter', 'disabled') == 'enabled'
        pdf_filter = request.args.get('pdfFilter', 'disabled') == 'enabled'

        # 查找資料夾ID
        folder_id = None
        file_type_query = ""
        if recordings_filter and recordings_folder_name:
            folder_id = processor.find_folder_id_by_path(recordings_folder_name)
            file_type_query = "mimeType contains 'audio/'"
        elif pdf_filter and pdf_folder_name:
            folder_id = processor.find_folder_id_by_path(pdf_folder_name)
            file_type_query = "mimeType = 'application/pdf'"

        # 組合查詢
        if folder_id:
            query = f"trashed = false and '{folder_id}' in parents"
            if file_type_query:
                query += f" and ({file_type_query})"
        else:
            query = "trashed = false and (mimeType contains 'audio/' or mimeType = 'application/pdf')"

        files = processor.list_drive_files(query=query)
        formatted_files = []
        for file in files:
            formatted_files.append({
                'id': file.get('id'),
                'name': file.get('name', '未命名檔案'),
                'mimeType': file.get('mimeType', 'application/octet-stream'),
                'size': file.get('size', 0),
                'parents': file.get('parents', [])
            })
        return jsonify({'success': True, 'files': formatted_files})

    except Exception as e:
        logging.error(f"獲取 Google Drive 檔案列表時發生錯誤: {str(e)}")
        return jsonify({'success': False, 'error': f'獲取檔案列表失敗: {str(e)}'}), 500