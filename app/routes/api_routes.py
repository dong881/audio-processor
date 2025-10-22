import os
import uuid
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from app.utils.constants import JOB_STATUS

# Create blueprint
api_bp = Blueprint('api', __name__)

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    from main import processor
    
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
def process_audio_endpoint():
    """API endpoint to process audio file and commit to GitHub"""
    from main import processor
    
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "Invalid request"}), 400

        file_id = data.get('file_id')
        if not file_id:
            return jsonify({"success": False, "error": "Missing file_id parameter"}), 400

        # Create job
        job_id = str(uuid.uuid4())
        job_data = processor.create_job(job_id, file_id)
        
        # Submit job to thread pool
        processor.process_file_async(job_id, file_id)
        
        logging.info(f"✅ Job submitted: {job_id}")
        
        return jsonify({
            "success": True,
            "message": "Job submitted for processing",
            "job_id": job_id,
            "job_status": job_data['status']
        })

    except Exception as e:
        logging.error(f"API Error: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Internal server error: {e}"}), 500

@api_bp.route('/job/<job_id>', methods=['GET'])
def get_job_status_endpoint(job_id):
    """Get job status"""
    from main import processor
    
    try:
        job_status = processor.get_job_status(job_id)
        
        if job_status is None or 'error' in job_status:
            return jsonify({"success": False, "error": "Job not found"}), 404
            
        return jsonify({
            "success": True,
            "job": job_status
        })
        
    except Exception as e:
        logging.error(f"API Error for job {job_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Internal server error: {e}"}), 500

@api_bp.route('/jobs', methods=['GET'])
def get_jobs_endpoint():
    """Get all jobs with optional filtering"""
    from main import processor
    
    try:
        filter_status = request.args.get('filter', 'active')
        
        with processor.jobs_lock:
            all_jobs = {job_id: job.copy() for job_id, job in processor.jobs.items()}
        
        if filter_status == 'all':
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'message': job.get('message', ''),
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
            }
        elif filter_status == 'active':
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'message': job.get('message', ''),
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
                if job['status'] in [JOB_STATUS['PENDING'], JOB_STATUS['PROCESSING']]
            }
        elif filter_status == 'completed':
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'message': job.get('message', ''),
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
                if job['status'] == JOB_STATUS['COMPLETED']
            }
        elif filter_status == 'failed':
            jobs_to_return = {
                job_id: {
                    'id': job['id'],
                    'status': job['status'],
                    'progress': job['progress'],
                    'message': job.get('message', ''),
                    'created_at': job['created_at'],
                    'updated_at': job['updated_at']
                }
                for job_id, job in all_jobs.items()
                if job['status'] == JOB_STATUS['FAILED']
            }
        else:
            return jsonify({"success": False, "error": "Invalid filter parameter"}), 400
            
        result = {
            "success": True,
            "jobs": jobs_to_return,
            "count": len(jobs_to_return),
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"API Error: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Internal server error: {e}"}), 500

@api_bp.route('/job/<job_id>/cancel', methods=['POST'])
def cancel_job_endpoint(job_id):
    """Cancel a job"""
    from main import processor
    
    try:
        result = processor.cancel_job(job_id)
        
        if not result.get('success', False):
            return jsonify(result), 400
            
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"API Error: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Internal server error: {e}"}), 500
