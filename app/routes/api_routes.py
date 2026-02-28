import os
import uuid
import logging
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from app.utils.constants import JOB_STATUS

# UUID 驗證正則表達式
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

# 建立藍圖
api_bp = Blueprint('api', __name__)


def _get_processor():
    """取得全域 AudioProcessor 實例"""
    processor = _get_processor()
    return processor


def _is_valid_uuid(value: str) -> bool:
    """驗證字串是否為有效的 UUID 格式"""
    return bool(_UUID_RE.match(value))

@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    processor = _get_processor()
    
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
    processor = _get_processor()
    
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
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/job/<job_id>', methods=['GET'])
def get_job_status_endpoint(job_id):
    """獲取工作狀態的 API 端點"""
    if not _is_valid_uuid(job_id):
        return jsonify({"success": False, "error": "無效的工作 ID 格式"}), 400
    processor = _get_processor()
    
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
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/jobs', methods=['GET'])
def get_active_jobs_endpoint():
    """獲取工作列表的 API 端點，可選擇性過濾狀態"""
    processor = _get_processor()
    
    try:
        # Get filter status from query parameter, default to show only active jobs
        filter_status = request.args.get('filter', 'active')
        
        # 定義有效的過濾器及其對應的狀態
        valid_filters = {
            'all': None,
            'active': [JOB_STATUS['PENDING'], JOB_STATUS['PROCESSING']],
            'completed': [JOB_STATUS['COMPLETED']],
            'failed': [JOB_STATUS['FAILED']],
        }
        
        if filter_status not in valid_filters:
            return jsonify({"success": False, "error": "Invalid filter parameter. Use 'active', 'all', 'completed', or 'failed'"}), 400
        
        # Create a consistent snapshot of jobs while holding the lock
        with processor.jobs_lock:
            all_jobs = {job_id: job.copy() for job_id, job in processor.jobs.items()}
        
        # 根據過濾器篩選並提取摘要欄位
        allowed_statuses = valid_filters[filter_status]
        jobs_to_return = {}
        for job_id, job in all_jobs.items():
            if allowed_statuses is None or job['status'] in allowed_statuses:
                jobs_to_return[job_id] = {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at'],
                }
            
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
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/drive/files')
def drive_files():
    """獲取Google Drive檔案列表"""
    processor = _get_processor()
    
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
    if not _is_valid_uuid(job_id):
        return jsonify({"success": False, "error": "無效的工作 ID 格式"}), 400
    processor = _get_processor()
    
    try:
        logging.info(f"嘗試取消任務: {job_id}")
        
        # 檢查任務是否存在，並記錄調試信息
        with processor.jobs_lock:
            job_exists = job_id in processor.jobs
            total_jobs = len(processor.jobs)
            existing_jobs = list(processor.jobs.keys())
            
        logging.info(f"任務存在檢查: {job_exists}, 總任務數: {total_jobs}")
        if not job_exists:
            logging.warning(f"任務 {job_id} 不存在於 processor.jobs 中")
            logging.debug(f"現有任務ID (前5個): {existing_jobs[:5]}")
            return jsonify({"success": False, "error": "任務不存在"}), 404
        
        # 嘗試取消任務
        result = processor.cancel_job(job_id)
        
        if not result.get('success', False):
            logging.warning(f"取消任務 {job_id} 失敗: {result.get('error', '未知錯誤')}")
            return jsonify(result), 400
            
        logging.info(f"任務 {job_id} 取消成功")
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"取消任務 API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"伺服器內部錯誤: {str(e)}"}), 500

@api_bp.route('/jobs/status/batch', methods=['POST'])
def get_batch_job_status_endpoint():
    """批量獲取任務狀態的 API 端點"""
    processor = _get_processor()
    
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
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/jobs/<job_id>/result', methods=['GET'])
def get_job_result_endpoint(job_id):
    """獲取任務結果的 API 端點"""
    if not _is_valid_uuid(job_id):
        return jsonify({"success": False, "error": "無效的工作 ID 格式"}), 400
    processor = _get_processor()
    
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
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/jobs/debug', methods=['GET'])
def debug_jobs_endpoint():
    """調試端點：列出所有任務ID (僅用於開發階段)"""
    # 僅在開發模式下允許存取
    if not os.getenv('FLASK_DEBUG', 'false').lower() == 'true':
        return jsonify({"success": False, "error": "此端點僅在開發模式下可用"}), 403
    processor = _get_processor()
    
    try:
        with processor.jobs_lock:
            jobs_info = {
                job_id: {
                    'status': job['status'],
                    'progress': job['progress'],
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in processor.jobs.items()
            }
            
        return jsonify({
            "success": True,
            "total_jobs": len(jobs_info),
            "jobs": jobs_info
        })
        
    except Exception as e:
        logging.error(f"調試端點錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/meeting-minutes/template', methods=['POST'])
def generate_meeting_minutes_template():
    """生成會議紀錄模板的 API 端點"""
    from app.services.meeting_minutes_generator import MeetingMinutesGenerator
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "無效的請求內容"}), 400
        
        generator = MeetingMinutesGenerator()
        
        # 提取參數
        meeting_title = data.get('meeting_title', '[Meeting Title]')
        date = data.get('date')
        start_time = data.get('start_time', 'HH:MM')
        end_time = data.get('end_time', 'HH:MM')
        attendees = data.get('attendees')
        agenda_items = data.get('agenda_items')
        status = data.get('status', 'Draft agenda')
        custom_notes = data.get('custom_notes', '')
        variant = data.get('variant', 'standard')
        
        # 生成模板
        if variant == 'standard':
            template = generator.generate_template(
                meeting_title=meeting_title,
                date=date,
                start_time=start_time,
                end_time=end_time,
                attendees=attendees,
                agenda_items=agenda_items,
                status=status,
                custom_notes=custom_notes
            )
        else:
            template = generator.generate_variant_template(
                variant=variant,
                meeting_title=meeting_title,
                date=date,
                start_time=start_time,
                end_time=end_time,
                attendees=attendees,
                agenda_items=agenda_items,
                status=status,
                custom_notes=custom_notes
            )
        
        return jsonify({
            "success": True,
            "template": template,
            "variant": variant
        })
        
    except Exception as e:
        logging.error(f"生成會議紀錄模板 API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/meeting-minutes/template/from-audio', methods=['POST'])
def generate_template_from_audio():
    """從音頻檔案元數據生成會議紀錄模板的 API 端點"""
    from app.services.meeting_minutes_generator import MeetingMinutesGenerator
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "無效的請求內容"}), 400
        
        audio_metadata = data.get('audio_metadata')
        if not audio_metadata:
            return jsonify({"success": False, "error": "缺少音頻元數據"}), 400
        
        generator = MeetingMinutesGenerator()
        
        # 提取可選參數
        custom_attendees = data.get('custom_attendees')
        custom_agenda = data.get('custom_agenda')
        
        # 生成模板
        template = generator.generate_from_audio_metadata(
            audio_metadata=audio_metadata,
            custom_attendees=custom_attendees,
            custom_agenda=custom_agenda
        )
        
        return jsonify({
            "success": True,
            "template": template
        })
        
    except Exception as e:
        logging.error(f"從音頻生成會議紀錄模板 API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500

@api_bp.route('/meeting-minutes/template/variants', methods=['GET'])
def get_template_variants():
    """獲取可用的會議紀錄模板變體"""
    from app.services.meeting_minutes_generator import MeetingMinutesGenerator
    
    try:
        generator = MeetingMinutesGenerator()
        variants = generator.get_template_variants()
        
        return jsonify({
            "success": True,
            "variants": variants
        })
        
    except Exception as e:
        logging.error(f"獲取模板變體 API 錯誤: {e}", exc_info=True)
        return jsonify({"success": False, "error": "伺服器內部錯誤"}), 500