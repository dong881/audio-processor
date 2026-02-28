import os
import logging
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, redirect, session, url_for
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import google.auth.transport.requests
from google.oauth2 import id_token
import google.oauth2.credentials
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
                # EXTERNAL_URL 未設定，保持使用原始 redirect_uri
                logging.warning("⚠️ EXTERNAL_URL 環境變數未設定，OAuth 可能無法正常運作")
            
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
                    'https://www.googleapis.com/auth/userinfo.email',
                    'openid'
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
                    # EXTERNAL_URL 未設定，保持使用原始 redirect_uri
                    redirect_uri = base_redirect_uri
                    logging.warning("⚠️ 回調中：EXTERNAL_URL 環境變數未設定")
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
                'https://www.googleapis.com/auth/userinfo.email',
                'openid'
            ],
            state=state,
            redirect_uri=redirect_uri
        )
        
        try:
            logging.info("🔄 使用授權碼換取令牌...")
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            session['authenticated'] = True
            logging.info("✅ OAuth 認證狀態已設置為 True")

            # 保存用戶信息到session - 改進的用戶資訊獲取邏輯
            user_info = None
            
            try:
                # 方法1: 嘗試從 id_token 解析用戶資訊
                if hasattr(credentials, 'id_token') and credentials.id_token:
                    try:
                        request_session_for_user_info = google.auth.transport.requests.Request()
                        id_info = id_token.verify_oauth2_token(
                            credentials.id_token,
                            request_session_for_user_info,
                            credentials.client_id
                        )
                        user_info = {
                            'id': id_info.get('sub'),
                            'name': id_info.get('name'),
                            'email': id_info.get('email'),
                            'picture': id_info.get('picture')
                        }
                        logging.info(f"✅ 從 id_token 獲取用戶資訊成功: {user_info.get('name')}")
                    except Exception as e:
                        logging.warning(f"從 id_token 解析用戶資訊失敗: {e}")
                
                # 方法2: 如果 id_token 方法失敗，使用 Google People API
                if not user_info or not user_info.get('name'):
                    try:
                        import requests
                        
                        # 使用 userinfo endpoint
                        response = requests.get(
                            'https://www.googleapis.com/oauth2/v2/userinfo',
                            headers={'Authorization': f'Bearer {credentials.token}'},
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            userinfo_data = response.json()
                            user_info = {
                                'id': userinfo_data.get('id'),
                                'name': userinfo_data.get('name'),
                                'email': userinfo_data.get('email'),
                                'picture': userinfo_data.get('picture')
                            }
                            logging.info(f"✅ 從 userinfo API 獲取用戶資訊成功: {user_info.get('name')}")
                        else:
                            logging.error(f"userinfo API 請求失敗: {response.status_code}")
                    except Exception as e:
                        logging.warning(f"從 userinfo API 獲取用戶資訊失敗: {e}")
                
                # 方法3: 最後嘗試使用 Google API Client
                if not user_info or not user_info.get('name'):
                    try:
                        import googleapiclient.discovery
                        service = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials)
                        profile = service.userinfo().get().execute()
                        
                        user_info = {
                            'id': profile.get('id'),
                            'name': profile.get('name'),
                            'email': profile.get('email'),
                            'picture': profile.get('picture')
                        }
                        logging.info(f"✅ 從 Google API Client 獲取用戶資訊成功: {user_info.get('name')}")
                    except Exception as e:
                        logging.warning(f"從 Google API Client 獲取用戶資訊失敗: {e}")
                
                # 驗證用戶資訊完整性
                if user_info and user_info.get('id') and user_info.get('name'):
                    session['user_info'] = user_info
                    logging.info(f"✅ 完整用戶資訊已存儲: ID={user_info.get('id')}, Name={user_info.get('name')}")
                else:
                    # 如果所有方法都失敗，使用基本資訊
                    fallback_info = {
                        'id': 'temp_' + str(hash(credentials.token))[-8:],
                        'name': '已認證用戶',
                        'email': '',
                        'picture': None
                    }
                    session['user_info'] = fallback_info
                    logging.warning(f"⚠️ 無法獲取完整用戶資訊，使用後備資訊: {fallback_info}")
                    
            except Exception as e:
                logging.error(f"獲取用戶資訊過程中發生錯誤: {str(e)}")
                # 設置後備用戶資訊
                session['user_info'] = {
                    'id': 'error_user',
                    'name': '認證用戶',
                    'email': '',
                    'picture': None
                }
            
            # *** 保存憑證到 Redis ***
            user_id = session['user_info'].get('id')
            if user_id and not user_id.startswith('temp_') and user_id != 'error_user':
                if credential_manager.save_credentials(user_id, credentials):
                    logging.info(f"✅ 用戶 {user_id} 的憑證已保存到 Redis")
                    credential_manager.extend_credential_expiry(user_id, 60)
                else:
                    logging.warning("⚠️ 憑證保存到 Redis 失敗，但認證仍然有效")
            
            # *** 設置 OAuth 憑證到 AudioProcessor ***
            try:
                if processor is not None:
                    if processor.set_oauth_credentials(credentials):
                        logging.info("✅ 已成功將OAuth憑證設置到AudioProcessor")
                    else:
                        logging.warning("⚠️ 設置OAuth憑證到AudioProcessor失敗")
            except Exception as proc_err:
                logging.warning(f"⚠️ 設置AudioProcessor憑證時發生錯誤: {proc_err}")
                    
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
                scopes=[
                    'https://www.googleapis.com/auth/drive.readonly',
                    'https://www.googleapis.com/auth/userinfo.profile',
                    'https://www.googleapis.com/auth/userinfo.email',
                    'openid'
                ],
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
        
        # *** 嘗試從 Redis 載入憑證 - 修復 "can't set attribute" 錯誤 ***
        if user_id and user_id != 'unknown' and not user_id.startswith('temp_') and user_id != 'error_user':
            try:
                valid_credentials = credential_manager.get_valid_credentials(user_id)
                if valid_credentials:
                    logging.info(f"✅ 從 Redis 載入用戶 {user_id} 的有效憑證")
                    
                    # 嘗試刷新用戶資訊 - 但不依賴於設置憑證到 processor
                    try:
                        refreshed_user_info = get_user_info_from_credentials(valid_credentials)
                        if refreshed_user_info and refreshed_user_info.get('name'):
                            user_info = refreshed_user_info
                            session['user_info'] = user_info
                            logging.info(f"✅ 用戶資訊已刷新: {user_info.get('name')}")
                    except Exception as refresh_error:
                        logging.warning(f"刷新用戶資訊時出錯，但繼續使用現有資訊: {refresh_error}")
                    
                    # 嘗試設置到 AudioProcessor - 但不讓錯誤影響認證狀態
                    try:
                        from main import processor
                        if processor is not None:
                            processor.set_oauth_credentials(valid_credentials)
                            logging.info("✅ 憑證已設置到 AudioProcessor")
                    except Exception as processor_error:
                        logging.warning(f"設置憑證到 AudioProcessor 失敗，但不影響認證狀態: {processor_error}")
                    
                    session['authenticated'] = True
                    authenticated = True
                    
                elif not authenticated:
                    logging.info(f"用戶 {user_id} 沒有有效憑證")
                    return jsonify({'authenticated': False})
                    
            except Exception as e:
                logging.error(f"從 Redis 載入憑證時出錯: {e}")
                # 不讓 Redis 錯誤影響基本認證狀態檢查
        
        if authenticated:
            # 確保用戶資訊完整性
            if not user_info.get('name') or user_info.get('name') in ['資訊獲取失敗', '未知用戶']:
                try:
                    # 嘗試重新獲取用戶資訊 - 修復憑證重建邏輯
                    refreshed_user_info = None
                    
                    # 嘗試從 session 中的憑證資訊重新獲取
                    session_credentials = session.get('credentials')
                    if session_credentials:
                        try:
                            # 修復：正確重建憑證對象
                            credential_kwargs = {
                                'token': session_credentials.get('token'),
                                'refresh_token': session_credentials.get('refresh_token'),
                                'token_uri': session_credentials.get('token_uri'),
                                'client_id': session_credentials.get('client_id'),
                                'client_secret': session_credentials.get('client_secret'),
                                'scopes': session_credentials.get('scopes')
                            }
                            
                            # 如果有過期時間，添加到參數中
                            if session_credentials.get('expiry'):
                                try:
                                    if isinstance(session_credentials['expiry'], str):
                                        credential_kwargs['expiry'] = datetime.fromisoformat(session_credentials['expiry'])
                                    else:
                                        credential_kwargs['expiry'] = session_credentials['expiry']
                                except Exception:
                                    pass  # 忽略過期時間解析錯誤
                            
                            creds = Credentials(**credential_kwargs)
                            refreshed_user_info = get_user_info_from_credentials(creds)
                        except Exception as cred_error:
                            logging.warning(f"從 session 憑證重新獲取用戶資訊失敗: {cred_error}")
                    
                    if refreshed_user_info and refreshed_user_info.get('name'):
                        user_info = refreshed_user_info
                        session['user_info'] = user_info
                        logging.info(f"✅ 用戶資訊重新獲取成功: {user_info.get('name')}")
                        
                except Exception as e:
                    logging.error(f"重新獲取用戶資訊失敗: {e}")
            
            # 確保返回完整的用戶對象，包括 picture URL
            complete_user_info = {
                'id': user_info.get('id', 'unknown'),
                'name': user_info.get('name', '已認證用戶'),
                'email': user_info.get('email', ''),
                'picture': user_info.get('picture')  # 確保包含 picture
            }
            
            return jsonify({
                'authenticated': True,
                'user': complete_user_info
            })
        else:
            return jsonify({'authenticated': False})
            
    except Exception as e:
        logging.error(f"檢查認證狀態時出錯: {e}")
        return jsonify({
            'authenticated': False,
            'error': str(e)
        }), 500

# 新增：專門用於刷新用戶資訊的 API 端點
@auth_bp.route('/api/auth/userinfo')
def get_userinfo():
    """獲取用戶資訊的專用端點"""
    try:
        if not session.get('authenticated'):
            return jsonify({'success': False, 'error': '用戶未認證'})
        
        user_info = session.get('user_info', {})
        user_id = user_info.get('id')
        
        # 嘗試從不同來源刷新用戶資訊
        refreshed_info = None
        
        # 方法1: 從 Redis 憑證獲取
        if user_id and user_id != 'unknown':
            try:
                valid_credentials = credential_manager.get_valid_credentials(user_id)
                if valid_credentials:
                    refreshed_info = get_user_info_from_credentials(valid_credentials)
            except Exception as e:
                logging.warning(f"從 Redis 憑證獲取用戶資訊失敗: {e}")
        
        # 方法2: 從 session 憑證獲取
        if not refreshed_info:
            session_credentials = session.get('credentials')
            if session_credentials:
                try:
                    # 修復：正確重建憑證對象
                    credential_kwargs = {
                        'token': session_credentials.get('token'),
                        'refresh_token': session_credentials.get('refresh_token'),
                        'token_uri': session_credentials.get('token_uri'),
                        'client_id': session_credentials.get('client_id'),
                        'client_secret': session_credentials.get('client_secret'),
                        'scopes': session_credentials.get('scopes')
                    }
                    
                    # 如果有過期時間，添加到參數中
                    if session_credentials.get('expiry'):
                        try:
                            if isinstance(session_credentials['expiry'], str):
                                credential_kwargs['expiry'] = datetime.fromisoformat(session_credentials['expiry'])
                            else:
                                credential_kwargs['expiry'] = session_credentials['expiry']
                        except Exception:
                            pass  # 忽略過期時間解析錯誤
                    
                    creds = Credentials(**credential_kwargs)
                    refreshed_info = get_user_info_from_credentials(creds)
                except Exception as e:
                    logging.warning(f"從 session 憑證獲取用戶資訊失敗: {e}")
        
        if refreshed_info and refreshed_info.get('name'):
            # 更新 session 中的用戶資訊
            session['user_info'] = refreshed_info
            return jsonify({'success': True, 'user': refreshed_info})
        else:
            # 返回現有的用戶資訊
            return jsonify({'success': True, 'user': user_info})
            
    except Exception as e:
        logging.error(f"獲取用戶資訊時出錯: {e}")
        return jsonify({'success': False, 'error': str(e)})

def get_user_info_from_credentials(credentials):
    """從憑證獲取用戶資訊的輔助函數"""
    try:
        # 方法1: 從 id_token 解析
        if hasattr(credentials, 'id_token') and credentials.id_token:
            try:
                request_session = google.auth.transport.requests.Request()
                id_info = id_token.verify_oauth2_token(
                    credentials.id_token,
                    request_session,
                    credentials.client_id
                )
                return {
                    'id': id_info.get('sub'),
                    'name': id_info.get('name'),
                    'email': id_info.get('email'),
                    'picture': id_info.get('picture')
                }
            except Exception as e:
                logging.warning(f"從 id_token 解析用戶資訊失敗: {e}")
        
        # 方法2: 使用 userinfo API
        try:
            import requests
            response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {credentials.token}'},
                timeout=10
            )
            
            if response.status_code == 200:
                userinfo_data = response.json()
                return {
                    'id': userinfo_data.get('id'),
                    'name': userinfo_data.get('name'),
                    'email': userinfo_data.get('email'),
                    'picture': userinfo_data.get('picture')
                }
        except Exception as e:
            logging.warning(f"從 userinfo API 獲取用戶資訊失敗: {e}")
        
        return None
        
    except Exception as e:
        logging.error(f"獲取用戶資訊時出錯: {e}")
        return None

@auth_bp.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """用戶登出"""
    try:
        # 获取用户ID以清理Redis中的憑證
        user_info = session.get('user_info', {})
        user_id = user_info.get('id')
        
        # 清理Redis中的憑證
        if user_id and user_id != 'unknown' and not user_id.startswith('temp_') and user_id != 'error_user':
            try:
                if credential_manager.delete_credentials(user_id):
                    logging.info(f"✅ 已清理用戶 {user_id} 在 Redis 中的憑證")
                else:
                    logging.warning(f"⚠️ 清理用戶 {user_id} 在 Redis 中的憑證失敗")
            except Exception as e:
                logging.error(f"清理 Redis 憑證時發生錯誤: {e}")
        
        # 清除所有session數據
        session.clear()
        
        # 清理AudioProcessor中的憑證
        try:
            from main import processor
            if processor is not None:
                processor.clear_credentials()
                logging.info("✅ 已清理 AudioProcessor 中的憑證")
        except Exception as e:
            logging.warning(f"清理 AudioProcessor 憑證時發生錯誤: {e}")
        
        logging.info("✅ 用戶已成功登出")
        return jsonify({'success': True, 'message': '登出成功'})
        
    except Exception as e:
        logging.error(f"登出處理失敗: {str(e)}")
        return jsonify({'success': False, 'error': f'登出失敗: {str(e)}'}), 500