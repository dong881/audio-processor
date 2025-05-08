import os
import logging
import json
from flask import Blueprint, request, jsonify, redirect, session, url_for
from google_auth_oauthlib.flow import Flow

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
    data = request.json
    code = data.get('code')
    
    if not code:
        return jsonify({'success': False, 'error': 'No authorization code provided'})
    
    # 實際應用中這裡需要與OAuth提供商交換令牌
    # 為了示例，我們簡單地設置session
    session['authenticated'] = True
    
    return jsonify({'success': True})

@auth_bp.route('/api/auth/status')
def auth_status():
    """檢查用戶認證狀態"""
    authenticated = session.get('authenticated', False)
    
    if authenticated:
        # 簡化示例：實際應用需要從OAuth token獲取用戶資訊
        user = {
            'id': '12345',
            'name': '示例用戶',
            'email': 'user@example.com',
            'picture': 'https://via.placeholder.com/150'
        }
        return jsonify({
            'authenticated': True,
            'user': user
        })
    else:
        return jsonify({
            'authenticated': False
        })

@auth_bp.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """登出用戶"""
    session.clear()
    return jsonify({'success': True}) 