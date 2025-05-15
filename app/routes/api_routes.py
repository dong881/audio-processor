import os
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

        # 提交工作
        job_id = processor.process_file_async(file_id, attachment_file_ids=attachment_file_ids)
        
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

        # Format files
        formatted_files = []
        for file_id, file_data in combined_files_map.items():
            formatted_files.append({
                'id': file_id,
                'name': file_data.get('name', '未命名檔案'),
                'mimeType': file_data.get('mimeType', 'application/octet-stream'),
                'size': file_data.get('size', 0),
                'parents': file_data.get('parents', [])
            })
        
        logging.info(f"Found {len(formatted_files)} unique files after filtering and combination.")
        return jsonify({'success': True, 'files': formatted_files})

    except Exception as e:
        logging.error(f"獲取 Google Drive 檔案列表時發生錯誤: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'獲取檔案列表失敗: {str(e)}'}), 500