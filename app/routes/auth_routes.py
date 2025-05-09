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
                # 如果正在使用Docker內部地址，則使用配置的外部地址
                redirect_uri = "http://localhost:5000/api/auth/callback"
                logging.info(f"使用硬編碼的外部URL: {redirect_uri}")
            
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
    """處理OAuth回調"""
    from app.services.audio_processor import AudioProcessor
    # 取得全域的 processor 實例
    from main import processor
    
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    logging.info(f"🔄 收到 OAuth 回調: code={'有值' if code else '無值'}, state={'有值' if state else '無值'}")
    
    # 檢查是否有錯誤
    if error:
        error_msg = f"Google OAuth 返回錯誤: {error}"
        logging.error(f"❌ OAuth 回調失敗: {error_msg}")
        return redirect(f'/login?error={error_msg}')
    
    # 檢查是否收到授權碼和狀態
    if not code or not state:
        error_msg = '缺少授權碼或狀態參數'
        logging.error(f"❌ OAuth 回調失敗: {error_msg}")
        return redirect(f'/login?error={error_msg}')
    
    # 檢查狀態是否匹配
    session_state = session.get('flow_state')
    if state != session_state:
        error_msg = f'狀態參數不匹配 (收到: {state}, 期望: {session_state})'
        logging.error(f"❌ OAuth 回調失敗: {error_msg}")
        return redirect(f'/login?error={error_msg}')
    
    try:
        # 重新建立 OAuth 流程
        client_secrets_file = os.getenv("GOOGLE_CLIENT_SECRET_PATH", 
                             os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             "credentials/client_secret.json"))
                                           
        # 確認 client_secret.json 文件存在
        if not os.path.exists(client_secrets_file):
            # 嘗試替代路徑
            alt_path = "/app/credentials/client_secret.json"
            if os.path.exists(alt_path):
                client_secrets_file = alt_path
                logging.info(f"✅ 找到替代 OAuth 配置路徑: {alt_path}")
            else:
                error_msg = '找不到 OAuth 配置文件'
                logging.error(f"❌ OAuth 回調失敗: {error_msg}")
                return redirect(f'/login?error={error_msg}')
        
        # 使用之前保存的重定向URI
        redirect_uri = session.get('redirect_uri')
        if not redirect_uri:
            # 如果沒有保存的URI，使用與auth_google相同的邏輯重建
            redirect_uri = request.url_root.rstrip('/') + '/api/auth/callback'
            # 檢查是否需要替換內部地址
            if 'localhost' in redirect_uri or '0.0.0.0' in redirect_uri or '127.0.0.1' in redirect_uri:
                # 嘗試獲取環境變數中設定的外部URL
                external_url = os.getenv("EXTERNAL_URL")
                if external_url:
                    redirect_uri = external_url.rstrip('/') + '/api/auth/callback'
                else:
                    # 如果正在使用Docker內部地址，則使用配置的外部地址
                    redirect_uri = "http://localhost:5000/api/auth/callback"
        
        logging.info(f"🔄 重建 OAuth 流程，使用重定向 URI: {redirect_uri}")
        
        try:
            flow = Flow.from_client_secrets_file(
                client_secrets_file,
                scopes=['https://www.googleapis.com/auth/drive.readonly'],
                state=state,
                redirect_uri=redirect_uri
            )
            
            # 使用授權碼換取令牌
            logging.info("🔄 使用授權碼換取令牌...")
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # 設定會話認證狀態
            session['authenticated'] = True
            
            # 使用OAuth憑證初始化Drive服務
            try:
                if processor is not None:
                    # 設置OAuth憑證到processor
                    if processor.set_oauth_credentials(credentials):
                        logging.info("✅ 已成功將OAuth憑證設置到AudioProcessor")
                    else:
                        logging.error("❌ 設置OAuth憑證到AudioProcessor失敗")
            except Exception as e:
                logging.error(f"⚠️ 設置OAuth憑證時發生錯誤: {str(e)}")
            
            logging.info("✅ OAuth 認證成功，重定向到回調頁面")
            return redirect('/callback')
        except Exception as e:
            error_msg = f"建立 OAuth 流程失敗: {str(e)}"
            logging.error(f"❌ OAuth 回調處理錯誤: {error_msg}", exc_info=True)
            return redirect(f'/login?error={error_msg}')    
            
    except Exception as e:
        error_msg = str(e)
        logging.error(f"❌ OAuth 回調處理錯誤: {error_msg}", exc_info=True)
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
        
        if authenticated:
            try:
                # 從會話中獲取憑證信息
                from main import processor
                
                if hasattr(processor, 'oauth_credentials') and processor.oauth_credentials:
                    try:
                        # 使用Google API獲取用戶資訊
                        request_session = google.auth.transport.requests.Request()
                        
                        # 檢查憑證是否過期，需要刷新
                        if processor.oauth_credentials.expired and processor.oauth_credentials.refresh_token:
                            processor.oauth_credentials.refresh(request_session)
                        
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
                
                # 如果無法透過OAuth憑證獲取用戶資訊，使用session中的用戶資訊
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
                # 發生錯誤時返回基本資訊
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
    """登出用戶"""
    session.clear()
    return jsonify({'success': True})

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