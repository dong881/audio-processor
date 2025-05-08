// Authentication helper functions

// Check if the user is authenticated
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status');
        
        // 處理非200響應
        if (!response.ok) {
            console.error(`Auth status check failed with status: ${response.status}`);
            window.location.href = '/login?error=' + encodeURIComponent('認證狀態檢查失敗，請重新登入');
            return null;
        }
        
        const data = await response.json();
        
        if (!data.authenticated) {
            console.log('用戶未認證，重定向到登入頁面');
            window.location.href = '/login';
            return null;
        }
        
        return data.user;
    } catch (error) {
        console.error('Auth status check failed:', error);
        window.location.href = '/login';
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
    
    userInfoElement.innerHTML = `
        <div class="user-avatar">
            <img src="${user.picture || '/static/img/avatar-placeholder.png'}" alt="${user.name}">
        </div>
        <div class="user-details">
            <span class="user-name">${user.name || '未知使用者'}</span>
            <span class="user-email">${user.email || ''}</span>
        </div>
    `;
}

// Initialize auth when the document is loaded
document.addEventListener('DOMContentLoaded', async () => {
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
    const user = await checkAuthStatus();
    if (user) {
        // 顯示已認證用戶界面
        if (typeof showAuthenticatedUI === 'function') {
            showAuthenticatedUI();
        }
        
        // 更新用戶信息UI
        updateUserInfoUI(user);
    }
});