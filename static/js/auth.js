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
        
        // 確保返回完整的用戶對象
        return data.user || { 
            name: '未知使用者',
            email: '',
            picture: null
        };
    } catch (error) {
        console.error('Auth status check failed:', error);
        return null;
    }
}

// Log out the user
async function logoutUser() {
    try {
        await fetch('/api/auth/logout', {
            method: 'POST'
        });
        window.location.href = '/login';
    } catch (error) {
        console.error('Logout failed:', error);
        // 即使登出 API 失敗，也強制重定向到登入頁面
        window.location.href = '/login';
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
    
    // 確保有頭像URL，並添加錯誤處理
    const avatarUrl = user.picture || '/static/img/avatar-placeholder.png';
    
    // Enhanced user info display with better error handling
    userInfoElement.innerHTML = `
        <div class="user-avatar">
            <img src="${avatarUrl}" alt="${user.name || '使用者'}" 
                 onerror="this.onerror=null; this.src='/static/img/avatar-placeholder.png'; this.style.opacity='0.7';">
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
    
    const loginButton = document.getElementById('login-btn');
    if (loginButton) {
        loginButton.addEventListener('click', () => {
            window.location.href = '/api/auth/google';
        });
    }
    
    // Check auth status and update UI
    try {
        const user = await checkAuthStatus();
        if (user) {
            // 顯示已認證用戶界面
            if (typeof showAuthenticatedUI === 'function') {
                showAuthenticatedUI();
            }
            
            // 更新用戶信息UI
            updateUserInfoUI(user);
        }
    } catch (error) {
        console.error('檢查認證狀態失敗:', error);
    }
});