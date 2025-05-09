from flask import Blueprint, jsonify, request, session, current_app
import google.oauth2.credentials
import googleapiclient.discovery

bp = Blueprint('drive', __name__)

@bp.route('/files', methods=['GET'])
def list_files():
    """取得用戶的 Google Drive 檔案列表"""
    try:
        # 驗證用戶已登入
        if 'credentials' not in session:
            return jsonify({'error': 'User not authenticated'}), 401
            
        # 獲取兩個獨立的過濾器設置
        recordings_filter = request.args.get('recordingsFilter', 'disabled')
        pdf_filter = request.args.get('pdfFilter', 'disabled')
        
        # 建立 Drive API 服務
        credentials = google.oauth2.credentials.Credentials(**session['credentials'])
        drive = googleapiclient.discovery.build('drive', 'v3', credentials=credentials)
        
        # 獲取檔案列表
        results = drive.files().list(
            pageSize=500,  # 增加返回的檔案數量
            q="trashed=false and mimeType != 'application/vnd.google-apps.folder'",
            fields="nextPageToken, files(id, name, mimeType, size, createdTime)"
        ).execute()
        
        files = results.get('files', [])
        
        # 增強檔案資訊，添加資料夾路徑
        enhanced_files = []
        audio_processor = current_app.audio_processor
        
        for file in files:
            try:
                folder_path = audio_processor.get_file_folder_path(file['id'])
                # 確保資料夾路徑是字串類型，即使是空值
                file['folderPath'] = folder_path if folder_path is not None else ""
                current_app.logger.debug(f"檔案: {file['name']}, 路徑: {folder_path}")
            except Exception as e:
                file['folderPath'] = ""
                current_app.logger.error(f"獲取檔案資料夾路徑時出錯 ({file['name']}): {e}")
                
            enhanced_files.append(file)
            
        # 更新 session 中的認證資訊
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'id_token': credentials.id_token if hasattr(credentials, 'id_token') else None
        }
            
        return jsonify({'files': enhanced_files})
        
    except Exception as e:
        current_app.logger.error(f"列舉檔案時出錯: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500