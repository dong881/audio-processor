// Authentication helper functions

// Check if the user is authenticated
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status');
        
        // 處理非200響應
        if (!response.ok) {
            console.error(`Auth status check failed with status: ${response.status}`);
            return null;
        }
        
        const data = await response.json();
        
        if (!data.authenticated) {
            console.log('用戶未認證，需要登入');
            return null;
        }
        // 確保返回完整的用戶對象，並增強錯誤處理
        return {
            id: data.user?.id || 'unknown',
            name: data.user?.name || '未知使用者',
            email: data.user?.email || '',
            picture: data.user?.picture || null
        };
    } catch (error) {
        console.error('Auth status check failed:', error);
        return null;
    }
}

// Log out the user
async function logoutUser() {
    try {
        const response = await fetch('/api/auth/logout', {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            window.location.href = '/login';
        } else {
            console.error('Logout failed:', data.error);
        }
    } catch (error) {
        console.error('Logout failed:', error);
    }
}

// Create folder if it doesn't exist
async function createRecordingsFolder() {
    try {
        const response = await fetch('/api/create-folder', {
            method: 'POST'
        });
        return await response.json();
    } catch (error) {
        console.error('Failed to create folder:', error);
        return { success: false, error: error.message };
    }
}

// Update the UI with user information
function updateUserInfoUI(user) {
    const userInfoElement = document.getElementById('user-info');
    
    // 檢查元素是否存在
    if (!userInfoElement) {
        console.warn('user-info元素不存在，無法更新用戶信息UI');
        return;
    }
    
    if (!user) {
        userInfoElement.innerHTML = '<div class="user-loading">未登入</div>';
        return;
    }
    
    console.log("Updating user info with:", JSON.stringify(user));
    
    // 確保有頭像URL，並添加增強的錯誤處理
    const avatarUrl = user.picture || '/static/img/avatar-placeholder.png';
    
    // Enhanced user info display with better error handling
    userInfoElement.innerHTML = `
        <div class="user-avatar">
            <img src="${avatarUrl}" alt="${user.name || '使用者'}" 
                 onerror="this.onerror=null; this.src='/static/img/avatar-placeholder.png'; this.style.opacity='0.7';"
                 loading="eager">
        </div>
        <div class="user-details">
            <span class="user-name">${user.name || '未知使用者'}</span>
            <span class="user-email">${user.email || ''}</span>
        </div>
    `;
    
    // 確保用戶信息容器可見
    const userInfoContainer = document.getElementById('user-info-container');
    if (userInfoContainer) {
        userInfoContainer.classList.remove('d-none');
    }
    
    // 增加額外的圖片載入檢查
    const avatarImg = userInfoElement.querySelector('.user-avatar img');
    if (avatarImg) {
        // 檢查圖片是否已經載入
        if (avatarImg.complete) {
            if (avatarImg.naturalHeight === 0) {
                avatarImg.src = '/static/img/avatar-placeholder.png';
                avatarImg.style.opacity = '0.7';
            }
        }
        
        // 加入事件監聽器以確保圖片載入
        avatarImg.addEventListener('error', function() {
            console.log('Avatar image error, using fallback');
            this.src = '/static/img/avatar-placeholder.png';
            this.style.opacity = '0.7';
        });
    }
}

// Initialize auth when the document is loaded
document.addEventListener('DOMContentLoaded', async () => {
    // Add a global error handler for image loading failures
    window.addEventListener('error', function(e) {
        if (e.target.tagName === 'IMG') {
            console.log('Image loading error, using fallback:', e.target.src);
            e.target.src = '/static/img/avatar-placeholder.png';
            e.target.style.opacity = '0.7';
        }
    }, true);

    // Set up logout button
    const logoutButton = document.getElementById('logout-button');
    if (logoutButton) {
        logoutButton.addEventListener('click', logoutUser);
    }
    
    // Fix login button selection and handler
    const loginButton = document.getElementById('login-button') || document.getElementById('login-btn');
    if (loginButton) {
        loginButton.addEventListener('click', () => {
            window.location.href = '/api/auth/google';
        });
    }
    
    // Retry mechanism for auth status check
    let retryCount = 0;
    const maxRetries = 3;
    
    async function checkAuthWithRetry() {
        try {
            const user = await checkAuthStatus();
            if (user) {
                // 顯示已認證用戶界面
                if (typeof showAuthenticatedUI === 'function') {
                    showAuthenticatedUI(user);
                }
                
                // 更新用戶信息UI
                updateUserInfoUI(user);
                
                // 如果在登入頁面但已經驗證，則跳轉到主頁
                if (window.location.pathname.includes('/login')) {
                    // 檢查是否已經嘗試過跳轉，避免無限循環
                    const redirectAttempted = sessionStorage.getItem('main_redirect_attempted');
                    if (!redirectAttempted) {
                        sessionStorage.setItem('main_redirect_attempted', 'true');
                        window.location.href = '/';
                    }
                }
            } else {
                if (!window.location.pathname.includes('/login')) {
                    // 在非登入頁面檢測到未驗證，跳轉到登入頁面
                    const redirectAttempted = sessionStorage.getItem('login_redirect_attempted');
                    if (!redirectAttempted) {
                        sessionStorage.setItem('login_redirect_attempted', 'true');
                        window.location.href = '/login';
                    }
                }
            }
        } catch (error) {
            console.error(`檢查認證狀態失敗 (嘗試 ${retryCount + 1}/${maxRetries}):`, error);
            if (retryCount < maxRetries) {
                retryCount++;
                setTimeout(checkAuthWithRetry, 1000); // 1秒後重試
            }
        }
    }
    
    // Start auth check with retry mechanism
    checkAuthWithRetry();
    
    // 清理重定向標記 - 確保30秒後重設，避免永久鎖定
    setTimeout(() => {
        sessionStorage.removeItem('login_redirect_attempted');
        sessionStorage.removeItem('main_redirect_attempted');
    }, 30000);
});