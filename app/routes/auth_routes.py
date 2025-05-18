import os
import logging
import json
from flask import Blueprint, request, jsonify, redirect, session, url_for, current_app
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import google.auth.transport.requests
from google.oauth2 import id_token
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

# 建立藍圖
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login():
    """登入頁面"""
    from flask import render_template
    return render_template('login.html')

@auth_bp.route('/callback')
def callback():
    """OAuth回調頁面"""
    from flask import render_template
    return render_template('callback.html')

@auth_bp.route('/api/auth/google')
def auth_google():
    """重定向到 Google OAuth"""
    # 使用 OAuth 2.0 流程，從 client_secret.json 建立 OAuth 流程
    try:
        # 設定 OAuth 流程
        client_secrets_file = os.getenv("GOOGLE_CLIENT_SECRET_PATH", 
                              os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                              "credentials/client_secret.json"))
        
        # 確認 client_secret.json 文件存在
        if not os.path.exists(client_secrets_file):
            logging.error(f"❌ 找不到 OAuth 配置文件: {client_secrets_file}")
            # 嘗試替代路徑
            alt_path = "/app/credentials/client_secret.json"
            if os.path.exists(alt_path):
                client_secrets_file = alt_path
                logging.info(f"✅ 找到替代 OAuth 配置路徑: {alt_path}")
            else:
                return jsonify({
                    'success': False,
                    'error': '伺服器 OAuth 配置錯誤，找不到必要的憑證文件'
                }), 500
            
        # 使用公網可訪問的URL作為重定向地址
        redirect_uri = request.url_root.rstrip('/') + '/api/auth/callback'
        # 記錄原始重定向URI
        logging.info(f"原始重定向URI: {redirect_uri}")
        
        # 檢查是否需要替換內部地址
        if 'localhost' in redirect_uri or '0.0.0.0' in redirect_uri or '127.0.0.1' in redirect_uri:
            # 嘗試獲取環境變數中設定的外部URL
            external_url = os.getenv("EXTERNAL_URL")
            if external_url:
                redirect_uri = external_url.rstrip('/') + '/api/auth/callback'
                logging.info(f"使用環境變數設定的外部URL: {redirect_uri}")
            else:
                # 如果正在使用Docker內部地址且EXTERNAL_URL未設定，則使用預期的外部地址
                # 這應該與 client_secret.json 和 Google Cloud Console 中的 URI 之一匹配。
                redirect_uri = "https://audio-processor.ddns.net/api/auth/callback"
                logging.info(f"使用硬編碼的預期外部URL: {redirect_uri}")
            
        logging.info(f"🔄 OAuth 重定向 URI: {redirect_uri}")
        
        # 檢查client_secret.json文件內容
        try:
            with open(client_secrets_file, 'r') as f:
                client_data = json.load(f)
                web_data = client_data.get('web', {})
                client_id = web_data.get('client_id')
                authorized_redirects = web_data.get('redirect_uris', [])
                
                logging.info(f"OAuth客戶端ID: {client_id}")
                logging.info(f"OAuth授權的重定向URIs: {authorized_redirects}")
                
                # 檢查當前重定向URI是否在授權列表中
                if redirect_uri not in authorized_redirects:
                    logging.warning(f"⚠️ 當前重定向URI不在授權列表中: {redirect_uri}")
        except Exception as e:
            logging.error(f"❌ 解析client_secret.json時出錯: {str(e)}")
            
        try:
            flow = Flow.from_client_secrets_file(
                client_secrets_file,
                scopes=[
                    'https://www.googleapis.com/auth/drive.readonly',
                    'https://www.googleapis.com/auth/userinfo.profile',
                    'https://www.googleapis.com/auth/userinfo.email'
                ],
                redirect_uri=redirect_uri
            )
            
            # 產生授權 URL
            auth_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            # 儲存流程狀態到 session
            session['flow_state'] = state
            session['redirect_uri'] = redirect_uri  # 儲存重定向URI以便在回調時使用
            
            logging.info(f"🔄 重定向到 Google 授權頁面: {auth_url}")
            
            # 重定向到 Google 的授權頁面
            return redirect(auth_url)
        except Exception as e:
            logging.error(f"❌ 建立OAuth流程失敗: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'OAuth 流程初始化失敗: {str(e)}'
            }), 500
            
    except Exception as e:
        logging.error(f"❌ OAuth 流程初始化失敗: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'OAuth 流程初始化失敗: {str(e)}'
        }), 500

@auth_bp.route('/api/auth/google/login')
def auth_google_login():
    """Google 登入入口點"""
    # 直接轉向到auth_google函數，避免重複代碼
    return auth_google()

@auth_bp.route('/api/auth/callback')
def auth_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    logging.info(f"🔄 收到 OAuth 回調: code={'有值' if code else '無值'}, state={'有值' if state else '無值'}, error={error}")
    
    if error:
        error_msg = f"Google OAuth 返回錯誤: {error}"
        logging.error(f"❌ OAuth 回調失敗: {error_msg}")
        return redirect(f'/login?error={error_msg}')
    
    if not code or not state:
        error_msg = '缺少授權碼或狀態參數'
        logging.error(f"❌ OAuth 回調失敗: {error_msg}")
        return redirect(f'/login?error={error_msg}')
    
    session_state = session.get('flow_state')
    if state != session_state:
        error_msg = f'狀態參數不匹配 (收到: {state}, 期望: {session_state})'
        logging.error(f"❌ OAuth 回調失敗: {error_msg}")
        return redirect(f'/login?error={error_msg}')
    
    try:
        client_secrets_file = os.getenv("GOOGLE_CLIENT_SECRET_PATH", 
                                     os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                     "credentials/client_secret.json"))
                                           
        if not os.path.exists(client_secrets_file):
            alt_path = "/app/credentials/client_secret.json"
            if os.path.exists(alt_path):
                client_secrets_file = alt_path
                logging.info(f"✅ 找到替代 OAuth 配置路徑: {alt_path}")
            else:
                error_msg = '找不到 OAuth 配置文件'
                logging.error(f"❌ OAuth 回調失敗: {error_msg}")
                return redirect(f'/login?error={error_msg}')
        
        redirect_uri = session.get('redirect_uri')
        if not redirect_uri:
            # 如果 session 中沒有 redirect_uri，則重新構造它
            # 這段邏輯應該與 auth_google 中的邏輯保持一致
            current_url_root = request.url_root # 獲取當前的根 URL
            base_redirect_uri = current_url_root.rstrip('/') + '/api/auth/callback'
            
            if 'localhost' in base_redirect_uri or '0.0.0.0' in base_redirect_uri or '127.0.0.1' in base_redirect_uri:
                external_url = os.getenv("EXTERNAL_URL")
                if external_url:
                    redirect_uri = external_url.rstrip('/') + '/api/auth/callback'
                    logging.info(f"回調中：使用環境變數EXTERNAL_URL設定的重定向URI: {redirect_uri}")
                else:
                    # 如果EXTERNAL_URL未設定，且是本地請求，則預設為預期的公開URI
                    redirect_uri = "https://audio-processor.ddns.net/api/auth/callback"
                    logging.info(f"回調中：使用硬編碼的預期外部URL: {redirect_uri}")
            else:
                # 如果不是本地請求，則直接使用基於請求的URL
                redirect_uri = base_redirect_uri
                logging.info(f"回調中：使用基於請求的重定向URI: {redirect_uri}")
        
        logging.info(f"🔄 重建 OAuth 流程，使用重定向 URI: {redirect_uri}")
        
        flow = Flow.from_client_secrets_file(
            client_secrets_file,
            scopes=[
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/userinfo.profile',
                'https://www.googleapis.com/auth/userinfo.email'
            ],
            state=state,
            redirect_uri=redirect_uri
        )
        
        # 使用授權碼獲取憑證
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # 儲存憑證到 session
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # 設置認證狀態
        session['authenticated'] = True
        
        # 初始化 AudioProcessor 的 OAuth 服務
        processor = current_app.audio_processor
        processor.initialize_oauth_service(credentials)
        
        logging.info("✅ OAuth 回調處理成功")
        return redirect('/')
        
    except Exception as e:
        error_msg = f'OAuth 回調處理失敗: {str(e)}'
        logging.error(f"❌ {error_msg}")
        return redirect(f'/login?error={error_msg}')

@auth_bp.route('/api/auth/token', methods=['POST'])
def auth_token():
    """獲取新的訪問令牌"""
    try:
        credentials_dict = session.get('credentials')
        if not credentials_dict:
            return jsonify({
                'success': False,
                'error': '未找到憑證信息'
            }), 401
            
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        # 如果令牌已過期，則刷新
        if credentials.expired:
            credentials.refresh(google.auth.transport.requests.Request())
            # 更新 session 中的令牌
            session['credentials']['token'] = credentials.token
            
        return jsonify({
            'success': True,
            'token': credentials.token
        })
        
    except Exception as e:
        logging.error(f"❌ 刷新令牌失敗: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'刷新令牌失敗: {str(e)}'
        }), 500

@auth_bp.route('/api/auth/status')
def auth_status():
    """檢查認證狀態"""
    try:
        is_authenticated = session.get('authenticated', False)
        credentials = session.get('credentials')
        
        if is_authenticated and credentials:
            # 如果令牌已過期，則刷新
            credentials_obj = Credentials(
                token=credentials['token'],
                refresh_token=credentials['refresh_token'],
                token_uri=credentials['token_uri'],
                client_id=credentials['client_id'],
                client_secret=credentials['client_secret'],
                scopes=credentials['scopes']
            )
            
            if credentials_obj.expired:
                credentials_obj.refresh(google.auth.transport.requests.Request())
                # 更新 session 中的令牌
                session['credentials']['token'] = credentials_obj.token
            
            # 使用令牌獲取用戶信息
            service = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials_obj)
            user_info = service.userinfo().get().execute()
            
            return jsonify({
                'success': True,
                'authenticated': True,
                'user': {
                    'email': user_info.get('email'),
                    'name': user_info.get('name'),
                    'picture': user_info.get('picture')
                }
            })
        else:
            return jsonify({
                'success': True,
                'authenticated': False
            })
    except Exception as e:
        logging.error(f"❌ 檢查認證狀態失敗: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'檢查認證狀態失敗: {str(e)}'
        }), 500

@auth_bp.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """登出"""
    session.clear()
    return jsonify({'success': True})

@auth_bp.route('/api/auth/userinfo', methods=['GET'])
def api_userinfo():
    """獲取用戶信息"""
    try:
        if not session.get('authenticated', False):
            return jsonify({
                'success': False,
                'error': '未認證'
            }), 401
            
        credentials_dict = session.get('credentials')
        if not credentials_dict:
            return jsonify({
                'success': False,
                'error': '未找到憑證信息'
            }), 401
            
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        # 如果令牌已過期，則刷新
        if credentials.expired:
            credentials.refresh(google.auth.transport.requests.Request())
            # 更新 session 中的令牌
            session['credentials']['token'] = credentials.token
        
        # 使用令牌獲取用戶信息
        service = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        
        return jsonify({
            'success': True,
            'user': {
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture')
            }
        })
        
    except Exception as e:
        logging.error(f"❌ 獲取用戶信息失敗: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'獲取用戶信息失敗: {str(e)}'
        }), 500