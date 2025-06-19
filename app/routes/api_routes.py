import os
import uuid
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
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
        if not file_id:
            return jsonify({"success": False, "error": "缺少 file_id 參數"}), 400

        attachment_file_ids = data.get('attachment_file_ids')  # Expect a list

        if attachment_file_ids is not None:
            if not isinstance(attachment_file_ids, list):
                return jsonify({'success': False, 'error': 'attachment_file_ids must be a list'}), 400
            if not all(isinstance(item, str) for item in attachment_file_ids):
                return jsonify({'success': False, 'error': 'All items in attachment_file_ids must be strings'}), 400
            if not attachment_file_ids:  # Treat empty list as no attachments
                attachment_file_ids = None

        # 生成工作ID並創建工作
        job_id = str(uuid.uuid4())
        job_data = processor.create_job(job_id, file_id, attachment_file_ids)
        
        # 提交工作到線程池進行非同步處理
        processor.process_file_async(job_id, file_id, attachment_file_ids)
        
        # 立即返回工作ID
        return jsonify({
            "success": True,
            "message": "工作已提交，正在後台處理",
            "job_id": job_id,
            "job_status": job_data['status']
        })

    except Exception as e:
        logging.error(f"API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {e}"}), 500

@api_bp.route('/job/<job_id>', methods=['GET'])
def get_job_status_endpoint(job_id):
    """獲取工作狀態的 API 端點"""
    try:
        logging.debug(f"Getting job status for job_id: {job_id}")
        job_status = processor.get_job_status(job_id)
        
        if job_status is None:
            logging.warning(f"Job {job_id} not found")
            return jsonify({"success": False, "error": f"Job {job_id} not found"}), 404
        
        if 'error' in job_status:
            logging.warning(f"Error in job status for {job_id}: {job_status['error']}")
            return jsonify({"success": False, "error": job_status['error']}), 404
            
        return jsonify({
            "success": True,
            "job": job_status
        })
        
    except Exception as e:
        logging.error(f"API 錯誤 for job {job_id}: {e}", exc_info=True)
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

        recordings_folder_name = request.args.get('recordingsFolderName')
        pdf_folder_name = request.args.get('pdfFolderName')
        recordings_filter_active = request.args.get('recordingsFilter') == 'enabled'
        pdf_filter_active = request.args.get('pdfFilter') == 'enabled'

        logging.debug(
            f"Drive files request: recordingsFilter={recordings_filter_active}, "
            f"pdfFilter={pdf_filter_active}, recordingsFolder='{recordings_folder_name}', "
            f"pdfFolder='{pdf_folder_name}'"
        )

        audio_files_list = []
        pdf_files_list = []

        # 1. Fetch Audio Files
        base_audio_query = "trashed = false and mimeType contains 'audio/'"
        if recordings_filter_active:
            if recordings_folder_name:
                recordings_folder_id = processor.find_folder_id_by_path(recordings_folder_name)
                if recordings_folder_id:
                    logging.debug(f"Audio filter: Found folder ID '{recordings_folder_id}' for path '{recordings_folder_name}'")
                    audio_query = f"{base_audio_query} and '{recordings_folder_id}' in parents"
                    audio_files_list = processor.list_drive_files(query=audio_query)
                else:
                    # Filter is on, folder name provided, but folder not found. Return no audio files for this filter.
                    logging.debug(f"Audio filter: Folder path '{recordings_folder_name}' not found.")
                    audio_files_list = []
            else:
                # Filter is on, but no folder name provided (should not happen if UI is correct)
                logging.debug("Audio filter: Active but no folder name provided.")
                audio_files_list = []
        else:
            # Recordings filter is OFF, fetch all audio files
            logging.debug("Audio filter: OFF, fetching all audio files.")
            audio_files_list = processor.list_drive_files(query=base_audio_query)

        # 2. Fetch PDF Files
        base_pdf_query = "trashed = false and mimeType = 'application/pdf'"
        if pdf_filter_active:
            if pdf_folder_name:
                pdf_folder_id = processor.find_folder_id_by_path(pdf_folder_name)
                if pdf_folder_id:
                    logging.debug(f"PDF filter: Found folder ID '{pdf_folder_id}' for path '{pdf_folder_name}'")
                    pdf_query = f"{base_pdf_query} and '{pdf_folder_id}' in parents"
                    pdf_files_list = processor.list_drive_files(query=pdf_query)
                else:
                    # Filter is on, folder name provided, but folder not found. Return no PDF files for this filter.
                    logging.debug(f"PDF filter: Folder path '{pdf_folder_name}' not found.")
                    pdf_files_list = []
            else:
                # Filter is on, but no folder name provided
                logging.debug("PDF filter: Active but no folder name provided.")
                pdf_files_list = []
        else:
            # PDF filter is OFF, fetch all PDF files
            logging.debug("PDF filter: OFF, fetching all PDF files.")
            pdf_files_list = processor.list_drive_files(query=base_pdf_query)

        # Combine and de-duplicate by ID
        combined_files_map = {}
        for f in audio_files_list:
            if f.get('id'):
                combined_files_map[f.get('id')] = f
        for f in pdf_files_list:
            if f.get('id'):
                combined_files_map[f.get('id')] = f

        # Format files with proper size conversion
        formatted_files = []
        for file_id, file_data in combined_files_map.items():
            # 確保 size 是數字類型
            size = file_data.get('size', '0')
            if isinstance(size, str):
                try:
                    size = int(size)
                except (ValueError, TypeError):
                    size = 0
            
            formatted_files.append({
                'id': file_id,
                'name': file_data.get('name', '未命名檔案'),
                'mimeType': file_data.get('mimeType', 'application/octet-stream'),
                'size': size,
                'parents': file_data.get('parents', [])
            })
        
        logging.info(f"Found {len(formatted_files)} unique files after filtering and combination.")
        return jsonify({'success': True, 'files': formatted_files})

    except Exception as e:
        logging.error(f"獲取 Google Drive 檔案列表時發生錯誤: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'獲取檔案列表失敗: {str(e)}'}), 500

@api_bp.route('/job/<job_id>/cancel', methods=['POST'])
def cancel_job_endpoint(job_id):
    """取消指定任務的 API 端點"""
    try:
        result = processor.cancel_job(job_id)
        
        if not result['success']:
            return jsonify(result), 400
            
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {e}"}), 500

@api_bp.route('/jobs/status/batch', methods=['POST'])
def get_batch_job_status_endpoint():
    """批量獲取任務狀態的 API 端點"""
    try:
        data = request.get_json()
        if not data or 'job_ids' not in data:
            return jsonify({"success": False, "error": "缺少 job_ids 參數"}), 400
        
        job_ids = data['job_ids']
        if not isinstance(job_ids, list):
            return jsonify({"success": False, "error": "job_ids 必須是陣列"}), 400
        
        # 批量獲取任務狀態
        jobs_status = {}
        for job_id in job_ids:
            job_status = processor.get_job_status(job_id)
            if job_status and 'error' not in job_status:
                jobs_status[job_id] = job_status
        
        return jsonify({
            "success": True,
            "jobs": jobs_status
        })
        
    except Exception as e:
        logging.error(f"批量獲取任務狀態 API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {e}"}), 500

@api_bp.route('/jobs/<job_id>/result', methods=['GET'])
def get_job_result_endpoint(job_id):
    """獲取任務結果的 API 端點"""
    try:
        logging.debug(f"Getting job result for job_id: {job_id}")
        job_status = processor.get_job_status(job_id)
        
        if job_status is None:
            logging.warning(f"Job {job_id} not found")
            return jsonify({"success": False, "error": f"Job {job_id} not found"}), 404
        
        if 'error' in job_status:
            logging.warning(f"Error in job status for {job_id}: {job_status['error']}")
            return jsonify({"success": False, "error": job_status['error']}), 404
        
        # 檢查任務是否已完成
        if job_status.get('status') != 'completed':
            return jsonify({"success": False, "error": "任務尚未完成"}), 400
        
        # 獲取結果數據
        result_data = job_status.get('result', {})
        
        return jsonify({
            "success": True,
            "result": result_data
        })
        
    except Exception as e:
        logging.error(f"獲取任務結果 API 錯誤 for job {job_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {e}"}), 500