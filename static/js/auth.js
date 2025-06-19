// Authentication helper functions

// Check if the user is authenticated
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status');
        
        if (!response.ok) {
            console.error(`Auth status check failed with status: ${response.status}`);
            return null;
        }
        
        const data = await response.json();
        
        if (!data.authenticated) {
            console.log('用戶未認證，需要登入');
            return null;
        }
        
        // 檢查用戶資訊完整性
        const user = data.user || {};
        
        // 如果用戶資訊不完整，嘗試刷新
        if (!user.name || user.name === '資訊獲取失敗' || user.name === '未知用戶' || user.id === 'unknown') {
            console.log('用戶資訊不完整，嘗試刷新...');
            const refreshedUser = await refreshUserInfo();
            if (refreshedUser) {
                return refreshedUser;
            }
        }
        
        // 確保返回完整的用戶對象
        return {
            id: user.id || 'unknown',
            name: user.name || '已認證用戶',
            email: user.email || '',
            picture: user.picture || null
        };
    } catch (error) {
        console.error('Auth status check failed:', error);
        return null;
    }
}

// 新增：刷新用戶資訊的函數
async function refreshUserInfo() {
    try {
        const response = await fetch('/api/auth/userinfo');
        
        if (!response.ok) {
            console.error(`Refresh user info failed with status: ${response.status}`);
            return null;
        }
        
        const data = await response.json();
        
        if (data.success && data.user && data.user.name) {
            console.log('用戶資訊刷新成功:', data.user);
            return data.user;
        } else {
            console.warn('用戶資訊刷新失敗:', data.error);
            return null;
        }
    } catch (error) {
        console.error('Refresh user info failed:', error);
        return null;
    }
}

// Log out the user
async function logoutUser() {
    try {
        // 设置登出标记，防止自动重定向
        sessionStorage.setItem('logout_in_progress', 'true');
        
        // 清理所有用戶相關的任務資料
        if (typeof currentUser !== 'undefined' && currentUser && currentUser.id) {
            console.log(`登出時清理用戶 ${currentUser.id} 的任務資料`);
            
            // 清理任務持久化資料
            if (typeof taskPersistence !== 'undefined') {
                taskPersistence.clearUserData(currentUser.id);
            }
            
            // 清理其他用戶相關的 localStorage 項目
            const userTasksKey = `audioProcessor_tasks_${currentUser.id}`;
            const userCleanupKey = `audioProcessor_cleanup_${currentUser.id}`;
            localStorage.removeItem(userTasksKey);
            localStorage.removeItem(userCleanupKey);
        }
        
        const response = await fetch('/api/auth/logout', {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            // 清除所有认证相关的存储
            sessionStorage.removeItem('main_redirect_attempted');
            sessionStorage.removeItem('login_redirect_attempted');
            localStorage.removeItem('filter-recordings-enabled');
            localStorage.removeItem('filter-pdf-enabled');
            
            // 清理可能遺留的任務相關資料
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith('audioProcessor_')) {
                    console.log(`清理遺留的任務資料: ${key}`);
                    localStorage.removeItem(key);
                }
            });
            
            // 延迟一点时间确保登出请求完成，然后跳转
            setTimeout(() => {
                sessionStorage.removeItem('logout_in_progress');
                window.location.href = '/login';
            }, 500);
        } else {
            console.error('Logout failed:', data.error);
            sessionStorage.removeItem('logout_in_progress');
        }
    } catch (error) {
        console.error('Logout failed:', error);
        sessionStorage.removeItem('logout_in_progress');
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
    
    if (!userInfoElement) {
        console.warn('user-info元素不存在，無法更新用戶信息UI');
        return;
    }
    
    if (!user) {
        userInfoElement.innerHTML = '<div class="user-loading">未登入</div>';
        return;
    }
    
    console.log("Updating user info with:", JSON.stringify(user));
    
    // 處理用戶資訊不完整的情況
    let displayName = user.name || '已認證用戶';
    let displayEmail = user.email || '';
    
    // 如果用戶資訊仍然不完整，顯示提示
    if (displayName === '資訊獲取失敗' || displayName === '未知用戶' || user.id === 'unknown') {
        displayName = '已認證用戶 (資訊載入中...)';
        // 嘗試在背景重新載入用戶資訊
        setTimeout(async () => {
            const refreshedUser = await refreshUserInfo();
            if (refreshedUser && refreshedUser.name) {
                updateUserInfoUI(refreshedUser);
            }
        }, 2000);
    }
    
    // 處理頭像 URL - 添加 CORS 和 referrer policy 支持
    let avatarUrl = user.picture || '/static/img/avatar-placeholder.png';
    
    // 如果是 Google 頭像，嘗試使用代理或添加適當的參數
    if (avatarUrl && avatarUrl.includes('googleusercontent.com')) {
        // 移除可能導致 CORS 問題的參數，並添加較小的尺寸
        avatarUrl = avatarUrl.replace(/=s\d+-c$/, '=s64-c');
        console.log('處理 Google 頭像 URL:', avatarUrl);
    }
    
    userInfoElement.innerHTML = `
        <div class="user-avatar">
            <img src="${avatarUrl}" alt="${displayName}" 
                 crossorigin="anonymous"
                 referrerpolicy="no-referrer"
                 onerror="this.onerror=null; this.src='/static/img/avatar-placeholder.png'; this.style.opacity='0.7'; console.log('頭像載入失敗，使用後備圖片');"
                 loading="eager">
        </div>
        <div class="user-details">
            <span class="user-name">${displayName}</span>
            <span class="user-email">${displayEmail}</span>
        </div>
    `;
    
    // 確保用戶信息容器可見
    const userInfoContainer = document.getElementById('user-info-container');
    if (userInfoContainer) {
        userInfoContainer.classList.remove('d-none');
    }
    
    // 增強的頭像載入錯誤處理
    const avatarImg = userInfoElement.querySelector('.user-avatar img');
    if (avatarImg) {
        // 檢查圖片是否已經載入失敗
        if (avatarImg.complete && avatarImg.naturalHeight === 0) {
            console.log('頭像圖片載入失敗，使用後備圖片');
            avatarImg.src = '/static/img/avatar-placeholder.png';
            avatarImg.style.opacity = '0.7';
        }
        
        // 添加載入成功事件
        avatarImg.addEventListener('load', function() {
            console.log('頭像圖片載入成功');
            this.style.opacity = '1';
        });
        
        // 添加載入錯誤事件
        avatarImg.addEventListener('error', function() {
            console.log('頭像圖片載入錯誤，使用後備圖片:', this.src);
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
    
    // 立即檢查認證狀態 - 修復認證狀態判斷
    console.log('開始檢查認證狀態...');
    
    // 检查是否正在进行登出操作
    const logoutInProgress = sessionStorage.getItem('logout_in_progress');
    if (logoutInProgress) {
        console.log('登出操作正在进行中，跳过自动重定向');
        return;
    }
    
    const user = await checkAuthStatus();
    
    if (user && user.id && user.id !== 'unknown') {
        console.log('用戶已認證:', user);
        
        // 顯示已認證用戶界面
        if (typeof showAuthenticatedUI === 'function') {
            showAuthenticatedUI(user);
        }
        
        // 更新用戶信息UI
        updateUserInfoUI(user);
        
        // 如果在登入頁面但已經驗證，則跳轉到主頁
        if (window.location.pathname.includes('/login')) {
            console.log('已認證用戶在登入頁面，跳轉到主頁');
            window.location.href = '/';
        }
    } else {
        console.log('用戶未認證或認證資訊不完整');
        
        // 只有在非登入頁面才跳轉到登入頁面
        if (!window.location.pathname.includes('/login')) {
            console.log('未認證用戶不在登入頁面，跳轉到登入頁面');
            window.location.href = '/login';
        } else {
            console.log('用戶在登入頁面，顯示登入界面');
            // 如果有未認證用戶界面函數，調用它
            if (typeof showUnauthenticatedUI === 'function') {
                showUnauthenticatedUI();
            }
        }
    }
});