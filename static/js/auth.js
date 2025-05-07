// Authentication helper functions

// Check if the user is authenticated
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status');
        const data = await response.json();
        
        if (!data.authenticated) {
            // If not authenticated, redirect to login
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