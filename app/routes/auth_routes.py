import os
import logging
import json
from flask import Blueprint, request, jsonify, redirect, session, url_for
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import google.auth.transport.requests
from google.oauth2 import id_token
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from app.services.credential_manager import CredentialManager

# 建立藍圖
auth_bp = Blueprint('auth', __name__)

# 初始化憑證管理器
credential_manager = CredentialManager()

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
                scopes=['https://www.googleapis.com/auth/drive.readonly'],
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
    from app.services.audio_processor import AudioProcessor
    from main import processor
    
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
            scopes=['https://www.googleapis.com/auth/drive.readonly'],
            state=state,
            redirect_uri=redirect_uri
        )
        
        try:
            logging.info("🔄 使用授權碼換取令牌...")
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            session['authenticated'] = True
            logging.info("✅ OAuth 認證狀態已設置為 True")

            # 保存用戶信息到session
            try:
                google_client_id = credentials.client_id
                
                request_session_for_user_info = google.auth.transport.requests.Request()
                id_info = id_token.verify_oauth2_token(
                    credentials.id_token,
                    request_session_for_user_info,
                    google_client_id
                )
                user_info = {
                    'id': id_info.get('sub'),
                    'name': id_info.get('name', '未知用戶'),
                    'email': id_info.get('email', ''),
                    'picture': id_info.get('picture')
                }
                session['user_info'] = user_info
                logging.info(f"✅ 用戶資訊已獲取並存儲到 session: {user_info.get('name')}")
                
                # *** 新增：保存憑證到 Redis ***
                user_id = user_info.get('id')
                if user_id and user_id != 'unknown':
                    if credential_manager.save_credentials(user_id, credentials):
                        logging.info(f"✅ 用戶 {user_id} 的憑證已保存到 Redis")
                        # 延長存儲時間到 60 天
                        credential_manager.extend_credential_expiry(user_id, 60)
                    else:
                        logging.warning("⚠️ 憑證保存到 Redis 失敗，但認證仍然有效")
                        
            except Exception as e:
                logging.warning(f"⚠️ 在 auth_callback 中獲取用戶資訊失敗: {str(e)}. Session user_info 可能不完整。")
                session['user_info'] = { 
                    'id': 'unknown', 
                    'name': '資訊獲取失敗', 
                    'email': '', 
                    'picture': None
                }
            
            # 保存憑證到 session（保持現有功能）
            session['credentials'] = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes,
                'id_token': credentials.id_token if hasattr(credentials, 'id_token') else None 
            }
            logging.info("✅ OAuth 憑證已轉換並存儲到 session")
            
            # 使用OAuth憑證初始化Drive服務
            try:
                if processor is not None:
                    if processor.set_oauth_credentials(credentials):
                        logging.info("✅ 已成功將OAuth憑證設置到AudioProcessor")
                    else:
                        logging.error("❌ 設置OAuth憑證到AudioProcessor失敗")
            except Exception as e:
                logging.error(f"⚠️ 設置OAuth憑證到AudioProcessor時發生錯誤: {str(e)}")
            
            logging.info("✅ OAuth 認證成功，重定向到應用主頁")
            return redirect('/')

        except google.auth.exceptions.RefreshError as re:
            error_msg = f"OAuth 憑證刷新失敗: {str(re)}"
            logging.error(f"❌ OAuth 回調處理錯誤 (憑證刷新): {error_msg}", exc_info=True)
            return redirect(f'/login?error={error_msg}')
        except google.auth.exceptions.OAuthError as oe:
            error_msg = f"OAuth 令牌交換或驗證失敗: {str(oe)}"
            logging.error(f"❌ OAuth 回調處理錯誤 (OAuthError): {error_msg}", exc_info=True)
            return redirect(f'/login?error={error_msg}')
        except Exception as e:
            error_msg = f"處理 OAuth 回調時發生內部錯誤: {str(e)}"
            logging.error(f"❌ OAuth 回調處理錯誤 (內部): {error_msg}", exc_info=True)
            return redirect(f'/login?error={error_msg}')    
            
    except Exception as e:
        error_msg = f"OAuth 回調前置檢查失敗: {str(e)}"
        logging.error(f"❌ OAuth 回調處理錯誤 (前置檢查): {error_msg}", exc_info=True)
        return redirect(f'/login?error={error_msg}')

@auth_bp.route('/api/auth/token', methods=['POST'])
def auth_token():
    """將授權碼轉換為令牌"""
    try:
        data = request.json
        code = data.get('code')
        
        if not code:
            return jsonify({'success': False, 'error': 'No authorization code provided'})
            
        # 設定 OAuth 流程
        client_secrets_file = os.getenv("GOOGLE_CLIENT_SECRET_PATH", 
                            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                            "credentials/client_secret.json"))
        
        # 確認 client_secret.json 文件存在
        if not os.path.exists(client_secrets_file):
            alt_path = "/app/credentials/client_secret.json"
            if os.path.exists(alt_path):
                client_secrets_file = alt_path
                logging.info(f"✅ 找到替代 OAuth 配置路徑: {alt_path}")
            else:
                return jsonify({'success': False, 'error': '找不到 OAuth 配置文件'})
        
        # 構建重定向URI
        redirect_uri = session.get('redirect_uri')
        if not redirect_uri:
            # 使用默認值
            redirect_uri = request.url_root.rstrip('/') + '/api/auth/callback'
            # 檢查是否需要替換內部地址
            if 'localhost' in redirect_uri or '0.0.0.0' in redirect_uri or '127.0.0.1' in redirect_uri:
                external_url = os.getenv("EXTERNAL_URL")
                if external_url:
                    redirect_uri = external_url.rstrip('/') + '/api/auth/callback'
                else:
                    redirect_uri = "http://localhost:5000/api/auth/callback"
        
        # 從session獲取狀態
        state = session.get('flow_state')
        if not state:
            return jsonify({'success': False, 'error': '找不到OAuth流程狀態'})
        
        # 建立流程並交換令牌
        try:
            flow = Flow.from_client_secrets_file(
                client_secrets_file,
                scopes=['https://www.googleapis.com/auth/drive.readonly'],
                state=state,
                redirect_uri=redirect_uri
            )
            
            # 使用授權碼換取令牌
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # 設定會話認證狀態
            session['authenticated'] = True
            
            # 保存用戶信息到session
            try:
                # 獲取用戶資訊
                request_session = google.auth.transport.requests.Request()
                id_info = id_token.verify_oauth2_token(
                    credentials.id_token,
                    request_session,
                    credentials.client_id
                )
                
                user_info = {
                    'id': id_info.get('sub'),
                    'name': id_info.get('name', '未知用戶'),
                    'email': id_info.get('email', ''),
                    'picture': id_info.get('picture')
                }
                
                session['user_info'] = user_info
                
                # 初始化Drive服務
                from main import processor
                if processor is not None:
                    if processor.set_oauth_credentials(credentials):
                        logging.info("✅ 已成功將OAuth憑證設置到AudioProcessor")
                    else:
                        logging.error("❌ 設置OAuth憑證到AudioProcessor失敗")
                
                return jsonify({'success': True, 'user': user_info})
                
            except Exception as e:
                logging.error(f"獲取用戶資訊失敗: {str(e)}")
                session['authenticated'] = True  # 仍然設定為已認證
                return jsonify({'success': True, 'message': '認證成功，但獲取用戶資訊失敗'})
                
        except Exception as e:
            logging.error(f"交換令牌失敗: {str(e)}")
            return jsonify({'success': False, 'error': f"交換令牌失敗: {str(e)}"})
            
    except Exception as e:
        logging.error(f"處理令牌交換時發生錯誤: {str(e)}")
        return jsonify({'success': False, 'error': f"處理令牌交換時發生錯誤: {str(e)}"})

@auth_bp.route('/api/auth/status')
def auth_status():
    """檢查用戶認證狀態並返回實際用戶資訊，增強錯誤處理"""
    try:
        authenticated = session.get('authenticated', False)
        user_info = session.get('user_info', {})
        user_id = user_info.get('id')
        
        # *** 新增：嘗試從 Redis 載入憑證 ***
        if user_id and user_id != 'unknown':
            try:
                valid_credentials = credential_manager.get_valid_credentials(user_id)
                if valid_credentials:
                    logging.info(f"✅ 從 Redis 載入用戶 {user_id} 的有效憑證")
                    # 更新 session 中的憑證
                    session['credentials'] = {
                        'token': valid_credentials.token,
                        'refresh_token': valid_credentials.refresh_token,
                        'token_uri': valid_credentials.token_uri,
                        'client_id': valid_credentials.client_id,
                        'client_secret': valid_credentials.client_secret,
                        'scopes': valid_credentials.scopes,
                        'id_token': valid_credentials.id_token if hasattr(valid_credentials, 'id_token') else None
                    }
                    session['authenticated'] = True
                    authenticated = True
                    
                    # 設置到 AudioProcessor
                    from main import processor
                    if processor is not None:
                        processor.set_oauth_credentials(valid_credentials)
                        
                elif not authenticated:
                    # 如果 Redis 中沒有憑證且 session 也未認證，則確實未認證
                    logging.info(f"用戶 {user_id} 沒有有效憑證")
                    return jsonify({'authenticated': False})
                    
            except Exception as e:
                logging.error(f"從 Redis 載入憑證時出錯: {e}")
                # 繼續使用 session 中的認證狀態
        
        if authenticated:
            # ...existing user info logic...
            try:
                from main import processor
                
                if hasattr(processor, 'oauth_credentials') and processor.oauth_credentials:
                    try:
                        request_session = google.auth.transport.requests.Request()
                        
                        if processor.oauth_credentials.expired and processor.oauth_credentials.refresh_token:
                            logging.info("🔄 OAuth憑證已過期，嘗試刷新...")
                            processor.oauth_credentials.refresh(request_session)
                            logging.info("✅ OAuth憑證刷新成功")
                            
                            # *** 新增：刷新後重新保存到 Redis ***
                            if user_id and user_id != 'unknown':
                                credential_manager.save_credentials(user_id, processor.oauth_credentials)
                            
                            session['credentials'] = {
                                'token': processor.oauth_credentials.token,
                                'refresh_token': processor.oauth_credentials.refresh_token,
                                'token_uri': processor.oauth_credentials.token_uri,
                                'client_id': processor.oauth_credentials.client_id,
                                'client_secret': processor.oauth_credentials.client_secret,
                                'scopes': processor.oauth_credentials.scopes,
                                'id_token': processor.oauth_credentials.id_token if hasattr(processor.oauth_credentials, 'id_token') else None
                            }
                            session.modified = True
                            logging.info("✅ 已將刷新後的憑證更新回 session")
                        
                        # 獲取用戶資訊 - 首先嘗試從id_token中取得
                        user = None
                        
                        # 優先透過id_token取得用戶資訊
                        if hasattr(processor.oauth_credentials, 'id_token') and processor.oauth_credentials.id_token:
                            try:
                                id_info = id_token.verify_oauth2_token(
                                    processor.oauth_credentials.id_token,
                                    request_session,
                                    processor.oauth_credentials.client_id
                                )
                                
                                user = {
                                    'id': id_info.get('sub'),
                                    'name': id_info.get('name'),
                                    'email': id_info.get('email'),
                                    'picture': id_info.get('picture')
                                }
                            except Exception as e:
                                logging.warning(f"透過id_token獲取用戶資訊失敗: {e}")
                                
                        # 如果無法透過id_token獲取或用戶資訊不完整，則嘗試userinfo API
                        if not user or not (user.get('name') and user.get('email')):
                            try:
                                import requests
                                userinfo_response = requests.get(
                                    'https://www.googleapis.com/oauth2/v3/userinfo',
                                    headers={'Authorization': f'Bearer {processor.oauth_credentials.token}'}
                                )
                                
                                if userinfo_response.status_code == 200:
                                    userinfo = userinfo_response.json()
                                    user = {
                                        'id': userinfo.get('sub'),
                                        'name': userinfo.get('name'),
                                        'email': userinfo.get('email'),
                                        'picture': userinfo.get('picture')
                                    }
                                else:
                                    logging.warning(f"userinfo API 返回狀態碼 {userinfo_response.status_code}")
                            except Exception as e:
                                logging.warning(f"透過userinfo API獲取用戶資訊失敗: {e}")
                        
                        # 如果成功取得用戶資訊，更新session
                        if user and user.get('id') and user.get('name'):
                            session['user_info'] = user
                            return jsonify({
                                'authenticated': True,
                                'user': user
                            })
                    except Exception as e:
                        logging.error(f"處理OAuth憑證時出錯: {e}")
                
                user_info = session.get('user_info', {
                    'id': 'unknown',
                    'name': '未知用戶',
                    'email': '',
                    'picture': None
                })
                
                return jsonify({
                    'authenticated': True,
                    'user': user_info
                })
                    
            except Exception as e:
                logging.error(f"獲取用戶資訊失敗: {str(e)}")
                return jsonify({
                    'authenticated': True,
                    'user': {
                        'id': 'unknown',
                        'name': '已認證用戶',
                        'email': '',
                        'picture': None
                    },
                    'error': str(e)
                })
        else:
            return jsonify({
                'authenticated': False
            })
    except Exception as e:
        logging.error(f"檢查認證狀態時出錯: {e}")
        return jsonify({
            'authenticated': False,
            'error': str(e)
        }), 500

@auth_bp.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """登出用戶並清理憑證"""
    try:
        # *** 新增：從 Redis 刪除憑證 ***
        user_info = session.get('user_info', {})
        user_id = user_info.get('id')
        
        if user_id and user_id != 'unknown':
            if credential_manager.delete_credentials(user_id):
                logging.info(f"✅ 用戶 {user_id} 的憑證已從 Redis 刪除")
            else:
                logging.warning(f"⚠️ 刪除用戶 {user_id} 的 Redis 憑證失敗或憑證不存在")
        
        session.clear()
        return jsonify({'success': True})
        
    except Exception as e:
        logging.error(f"登出過程中出錯: {e}")
        session.clear()  # 即使出錯也清理 session
        return jsonify({'success': True, 'warning': str(e)})

@auth_bp.route('/api/auth/userinfo', methods=['GET'])
def api_userinfo():
    """處理API獲取用戶資訊請求"""
    try:
        # 檢查認證狀態
        if 'credentials' not in session:
            return jsonify({
                'success': False, 
                'error': 'User not authenticated',
                'user': None
            }), 401
            
        # 從session獲取憑證
        credentials_dict = session.get('credentials')
        credentials = google.oauth2.credentials.Credentials(**credentials_dict)
        
        # 重新取得用戶資訊
        user_info = {}
        
        # 嘗試從id_token解析
        if hasattr(credentials, 'id_token') and credentials.id_token:
            try:
                # 解析ID token
                id_info = id_token.verify_oauth2_token(
                    credentials.id_token, 
                    google.auth.transport.requests.Request(), 
                    os.environ.get('GOOGLE_CLIENT_ID')
                )
                
                user_info = {
                    'id': id_info.get('sub'),
                    'email': id_info.get('email'),
                    'name': id_info.get('name'),
                    'picture': id_info.get('picture')
                }
            except Exception as e:
                logging.warning(f"無法從ID token解析用戶資訊: {e}")
        
        # 如果id_token不可用或解析失敗，則嘗試使用userinfo API
        if not user_info.get('id') or user_info.get('id') == 'unknown':
            try:
                # 使用credentials訪問Google People API
                service = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials)
                userinfo = service.userinfo().get().execute()
                
                user_info = {
                    'id': userinfo.get('id'),
                    'email': userinfo.get('email'),
                    'name': userinfo.get('name'),
                    'picture': userinfo.get('picture')
                }
            except Exception as e:
                logging.error(f"無法從userinfo API獲取用戶資訊: {e}")
        
        # 更新session中的用戶資訊
        if user_info.get('id') and user_info.get('id') != 'unknown':
            session['user_info'] = user_info
            
            # 更新憑證
            session['credentials'] = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes,
                'id_token': credentials.id_token if hasattr(credentials, 'id_token') else None
            }
            
            return jsonify({
                'success': True,
                'user': user_info
            })
        else:
            return jsonify({
                'success': False,
                'error': '無法獲取完整的用戶資訊',
                'user': user_info
            })
            
    except Exception as e:
        logging.error(f"獲取用戶資訊時出錯: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'user': None
        }), 500

@auth_bp.route('/api/auth/health')
def auth_health():
    """檢查認證系統健康狀態"""
    try:
        # 檢查 Redis 連接
        redis_status = "connected" if credential_manager.redis_client else "disconnected"
        if credential_manager.redis_client:
            try:
                credential_manager.redis_client.ping()
                redis_ping = True
            except:
                redis_ping = False
                redis_status = "connection_failed"
        else:
            redis_ping = False
        
        # 檢查當前用戶憑證狀態
        user_info = session.get('user_info', {})
        user_id = user_info.get('id')
        credential_status = "no_user"
        
        if user_id and user_id != 'unknown':
            try:
                stored_credentials = credential_manager.load_credentials(user_id)
                if stored_credentials:
                    if stored_credentials.expired:
                        credential_status = "expired"
                    else:
                        credential_status = "valid"
                else:
                    credential_status = "not_found"
            except:
                credential_status = "error"
        
        return jsonify({
            'redis_status': redis_status,
            'redis_ping': redis_ping,
            'credential_status': credential_status,
            'authenticated': session.get('authenticated', False),
            'user_id': user_id
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'redis_status': 'unknown',
            'redis_ping': False,
            'credential_status': 'unknown'
        }), 500