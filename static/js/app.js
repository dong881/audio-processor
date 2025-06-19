// 全局變數
const API_BASE_URL = '';  // 空字串表示相對路徑
let googleAuthInitialized = false;
let activeJobsTimer = null;
let currentJobId = null;
let jobStatusTimer = null;
let redirectBlocked = false; // 防止循環跳轉的標記
let lastActiveJobsData = null; // 用於存儲上一次的任務數據
let activeJobsUpdateTimeout = null; // 用於防抖動
let currentUser = null; // 添加當前用戶變數

// Add global variables for folder filtering
let recordingsFilterEnabled = false;
let pdfFilterEnabled = false;
const RECORDINGS_FOLDER = 'WearNote_Recordings';
const DOCUMENTS_FOLDER = 'WearNote_Recordings/Documents';

// Task Manager 相關變數 - 新增用戶任務管理
let taskManager = {
    isExpanded: true,
    currentFilter: 'active',
    tasks: {},
    updateTimer: null,
    updateInterval: 3000, // 增加到3秒，減少API請求頻率
    estimatedTimes: {
        'pending': 0,
        'downloading': 30,
        'converting': 60,
        'transcribing': 300,
        'analyzing': 120,
        'generating': 90,
        'uploading': 45,
        'finalizing': 15
    },
    // 新增任務持久化相關配置
    storageKey: 'userTasks',
    maxRetentionDays: 30,
    lastCleanupDate: null
};

// 任務持久化管理類
class TaskPersistenceManager {
    constructor() {
        this.storagePrefix = 'audioProcessor_';
        this.retentionDays = 30;
    }

    // 獲取用戶特定的儲存鍵
    getUserTasksKey(userId) {
        return `${this.storagePrefix}tasks_${userId}`;
    }

    // 獲取清理日期鍵
    getCleanupKey(userId) {
        return `${this.storagePrefix}cleanup_${userId}`;
    }

    // 儲存任務
    saveTasks(userId, tasks) {
        try {
            const tasksData = {
                tasks: tasks,
                lastUpdated: new Date().toISOString()
            };
            localStorage.setItem(this.getUserTasksKey(userId), JSON.stringify(tasksData));
            console.log(`已為用戶 ${userId} 儲存 ${Object.keys(tasks).length} 個任務`);
        } catch (error) {
            console.error('儲存任務失敗:', error);
        }
    }

    // 載入任務
    loadTasks(userId) {
        try {
            const stored = localStorage.getItem(this.getUserTasksKey(userId));
            if (!stored) return {};

            const tasksData = JSON.parse(stored);
            const tasks = tasksData.tasks || {};
            
            // 清理過期任務
            const cleanedTasks = this.cleanExpiredTasks(tasks);
            
            // 如果有任務被清理，重新儲存
            if (Object.keys(cleanedTasks).length !== Object.keys(tasks).length) {
                this.saveTasks(userId, cleanedTasks);
            }

            console.log(`已為用戶 ${userId} 載入 ${Object.keys(cleanedTasks).length} 個任務`);
            return cleanedTasks;
        } catch (error) {
            console.error('載入任務失敗:', error);
            return {};
        }
    }

    // 清理過期任務
    cleanExpiredTasks(tasks) {
        const now = new Date();
        const cutoffDate = new Date(now.getTime() - (this.retentionDays * 24 * 60 * 60 * 1000));

        const cleanedTasks = {};
        let removedCount = 0;

        Object.entries(tasks).forEach(([taskId, task]) => {
            const taskDate = new Date(task.createdAt);
            if (taskDate >= cutoffDate) {
                cleanedTasks[taskId] = task;
            } else {
                removedCount++;
            }
        });

        if (removedCount > 0) {
            console.log(`清理了 ${removedCount} 個過期任務`);
        }

        return cleanedTasks;
    }

    // 檢查是否需要進行日常清理
    shouldPerformDailyCleanup(userId) {
        try {
            const lastCleanup = localStorage.getItem(this.getCleanupKey(userId));
            if (!lastCleanup) return true;

            const lastCleanupDate = new Date(lastCleanup);
            const now = new Date();
            const daysSinceCleanup = (now - lastCleanupDate) / (1000 * 60 * 60 * 24);

            return daysSinceCleanup >= 1; // 每天執行一次清理
        } catch (error) {
            console.error('檢查清理狀態失敗:', error);
            return true;
        }
    }

    // 執行日常清理
    performDailyCleanup(userId) {
        try {
            // 載入並清理任務
            const tasks = this.loadTasks(userId);
            this.saveTasks(userId, tasks);

            // 更新清理日期
            localStorage.setItem(this.getCleanupKey(userId), new Date().toISOString());
            
            console.log('日常清理完成');
        } catch (error) {
            console.error('執行日常清理失敗:', error);
        }
    }

    // 清除特定用戶的所有資料
    clearUserData(userId) {
        try {
            localStorage.removeItem(this.getUserTasksKey(userId));
            localStorage.removeItem(this.getCleanupKey(userId));
            console.log(`已清除用戶 ${userId} 的所有任務資料`);
        } catch (error) {
            console.error('清除用戶資料失敗:', error);
        }
    }
}

// 初始化任務持久化管理器
const taskPersistence = new TaskPersistenceManager();

// DOM 元素快取
const elements = {
    // 主UI元素
    fileList: document.getElementById('file-list'),
    attachmentList: document.getElementById('attachment-list'),
    progressContainer: document.getElementById('progress-container'),
    processingBar: document.getElementById('processing-bar'),
    processingStatus: document.getElementById('processing-status'),
    resultContainer: document.getElementById('result-container'),
    authSection: document.getElementById('auth-section'),
    processingSection: document.getElementById('processing-section'),
    // 支援多個登入按鈕元素 (同時支援 login-button 和 login-btn)
    loginButtons: [
        document.getElementById('login-button'),
        document.getElementById('login-btn')
    ].filter(Boolean), // 過濾掉不存在的元素
    logoutButton: document.getElementById('logout-button'),

    // 操作按鈕
    refreshFilesBtn: document.getElementById('refresh-files-btn'),
    
    // 結果顯示區
    jobsList: document.getElementById('jobs-list'),
    resultTitle: document.getElementById('result-title'),
    resultSummary: document.getElementById('result-summary'),
    resultTodos: document.getElementById('result-todos'),
    resultLink: document.getElementById('result-link'),
    resultSpeakers: document.getElementById('result-speakers'),
    
    // 進度指示
    progressPercentage: document.getElementById('progress-percentage'),
    
    // Task Manager 元素
    createTaskBtn: document.getElementById('create-task-btn'),
    refreshTasksBtn: document.getElementById('refresh-tasks-btn'),
    toggleTaskManagerBtn: document.getElementById('toggle-task-manager-btn'),
    taskManagerContent: document.getElementById('task-manager-content'),
    tasksContainer: document.getElementById('tasks-container'),
    activeTasksCount: document.getElementById('active-tasks-count'),
    taskFilterButtons: document.querySelectorAll('input[name="task-filter"]'),
};

// 初始化頁面
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupEventListeners();
});

// 設置事件監聽器
function setupEventListeners() {
    // 登入/登出按鈕
    if (elements.loginButtons.length > 0) {
        elements.loginButtons.forEach(button => {
            button.addEventListener('click', handleLogin);
        });
    }
    
    if (elements.logoutButton) {
        elements.logoutButton.addEventListener('click', handleLogout);
    }
    
    // 刷新文件列表按鈕
    if (elements.refreshFilesBtn) {
        elements.refreshFilesBtn.addEventListener('click', function() {
            const refreshIcon = document.getElementById('refresh-icon');
            if (refreshIcon) {
                refreshIcon.classList.add('rotating');
                
                // 1秒後移除動畫類，避免下次點擊時動畫不生效
                setTimeout(() => {
                    refreshIcon.classList.remove('rotating');
                }, 1000);
            }
            loadDriveFiles();
        });
    }
    
    // Task Manager 事件監聽器
    if (elements.createTaskBtn) {
        elements.createTaskBtn.addEventListener('click', createNewTask);
    }
    
    if (elements.refreshTasksBtn) {
        elements.refreshTasksBtn.addEventListener('click', refreshTasks);
    }
    
    if (elements.toggleTaskManagerBtn) {
        elements.toggleTaskManagerBtn.addEventListener('click', toggleTaskManager);
    }
    
    // 任務篩選按鈕事件監聽器
    elements.taskFilterButtons.forEach(button => {
        button.addEventListener('change', function() {
            taskManager.currentFilter = this.value;
            filterTasks();
        });
    });

    // 錄音資料夾過濾切換開關 - 修復功能
    const recordingsFilterToggle = document.getElementById('filter-recordings-toggle');
    if (recordingsFilterToggle) {
        // 載入保存的偏好設置或設置為預設開啟
        const recordingsSavedPreference = localStorage.getItem('filter-recordings-enabled');
        if (recordingsSavedPreference === null) {
            recordingsFilterEnabled = true; // Default to true
            localStorage.setItem('filter-recordings-enabled', 'true'); // Save default
        } else {
            recordingsFilterEnabled = (recordingsSavedPreference === 'true');
        }
        recordingsFilterToggle.checked = recordingsFilterEnabled;
        
        // 更新視覺效果
        updateToggleVisualState(recordingsFilterToggle, recordingsFilterEnabled);
        
        recordingsFilterToggle.addEventListener('change', function(e) {
            recordingsFilterEnabled = e.target.checked;
            
            // 更新視覺狀態
            updateToggleVisualState(this, recordingsFilterEnabled);
            
            // 保存偏好設置
            localStorage.setItem('filter-recordings-enabled', recordingsFilterEnabled);
            
            // 只重新載入音訊檔案列表
            loadAudioFiles();
        });
    }
    
    // PDF資料夾過濾切換開關 - 修復功能
    const pdfFilterToggle = document.getElementById('filter-pdf-toggle');
    if (pdfFilterToggle) {
        // 載入保存的偏好設置或設置為預設開啟
        const pdfSavedPreference = localStorage.getItem('filter-pdf-enabled');
        if (pdfSavedPreference === null) {
            pdfFilterEnabled = true; // Default to true
            localStorage.setItem('filter-pdf-enabled', 'true'); // Save default
        } else {
            pdfFilterEnabled = (pdfSavedPreference === 'true');
        }
        pdfFilterToggle.checked = pdfFilterEnabled;
        
        // 更新視覺效果
        updateToggleVisualState(pdfFilterToggle, pdfFilterEnabled);
        
        pdfFilterToggle.addEventListener('change', function(e) {
            pdfFilterEnabled = e.target.checked;
            
            // 更新視覺狀態
            updateToggleVisualState(this, pdfFilterEnabled);
            
            // 保存偏好設置
            localStorage.setItem('filter-pdf-enabled', pdfFilterEnabled);
            
            // 只重新載入 PDF 檔案列表
            loadPdfFiles();
        });
    }

    // Initialize tooltips with updated options
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    if (typeof bootstrap !== 'undefined') {
        tooltipTriggerList.forEach(function(tooltipTriggerEl) {
            new bootstrap.Tooltip(tooltipTriggerEl, {
                animation: true,
                trigger: 'hover focus',
                boundary: document.body, // 添加邊界設定以修復滾動問題
                popperConfig: {
                    modifiers: [{
                        name: 'preventOverflow',
                        options: {
                            boundary: document.body,
                            padding: 8
                        }
                    }]
                }
            });
        });
    } else {
        console.warn('Bootstrap JavaScript is not loaded. Tooltips will not work.');
    }
}

/**
 * 更新切換開關的視覺狀態
 */
function updateToggleVisualState(toggleElement, isEnabled) {
    const toggleTrack = toggleElement.nextElementSibling.querySelector('.toggle-track');
    if (toggleTrack) {
        if (isEnabled) {
            toggleTrack.classList.add('active');
        } else {
            toggleTrack.classList.remove('active');
        }
    }
}

// ===== 認證相關函數 =====

// 檢查用戶認證狀態 - 更新為返回完整用戶資訊
async function checkAuthStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/status`);
        
        if (!response.ok) {
            console.error(`認證狀態檢查失敗，錯誤碼: ${response.status}`);
            return null;
        }
        
        const data = await response.json();
        
        if (data.authenticated && data.user) {
            currentUser = {
                id: data.user.id || data.user.email || 'unknown_user', // 確保有ID
                email: data.user.email,
                name: data.user.name,
                ...data.user
            };
            console.log('當前用戶資訊:', currentUser);
            return currentUser;
        } else {
            currentUser = null;
            return null;
        }
    } catch (error) {
        console.error('檢查認證狀態時出錯:', error);
        currentUser = null;
        return null;
    }
}

// 顯示已認證用戶界面 - 更新為處理任務恢復
function showAuthenticatedUI(user) {
    // 確保 currentUser 全局變數被正確設置
    if (user) {
        currentUser = {
            id: user.id || user.email || 'unknown_user',
            email: user.email,
            name: user.name,
            ...user
        };
        console.log('設置全局 currentUser:', currentUser);
    }
    
    if (elements.authSection) elements.authSection.classList.add('d-none');
    if (elements.processingSection) elements.processingSection.classList.remove('d-none');
    if (elements.loginButtons.length > 0) {
        elements.loginButtons.forEach(button => {
            button.classList.add('d-none');
        });
    }
    if (elements.logoutButton) elements.logoutButton.classList.remove('d-none');
    
    // 更新用戶資訊UI
    if (user && typeof updateUserInfoUI === 'function') {
        updateUserInfoUI(user);
    }

    // 恢復用戶的任務歷史
    if (user && user.id) {
        restoreUserTasks(user.id);
    }
}

// 顯示未認證用戶界面 - 更新為清理當前用戶資料
function showUnauthenticatedUI() {
    console.log('app.js: User not authenticated. UI updated for unauthenticated state.');
    
    if (elements.authSection) elements.authSection.classList.remove('d-none');
    if (elements.processingSection) elements.processingSection.classList.add('d-none');
    if (elements.loginButtons.length > 0) {
        elements.loginButtons.forEach(button => {
            button.classList.remove('d-none');
        });
    }
    if (elements.logoutButton) elements.logoutButton.classList.add('d-none');

    // 清理當前用戶相關資料
    currentUser = null;
    taskManager.tasks = {};
    stopTaskPolling();
    clearTasksUI();
}

// 處理登入
function handleLogin() {
    window.location.href = `${API_BASE_URL}/api/auth/google`;
}

// 處理登出 - 更新為保存任務後登出
async function handleLogout() {
    // 保存當前任務狀態
    if (currentUser && currentUser.id) {
        saveCurrentTasks();
    }

    // 使用 auth.js 中的 logoutUser 函数
    if (typeof logoutUser === 'function') {
        await logoutUser();
    } else {
        // 後備方案
        try {
            sessionStorage.setItem('logout_in_progress', 'true');
            const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
                method: 'POST'
            });
            
            if (response.ok) {
                setTimeout(() => {
                    sessionStorage.removeItem('logout_in_progress');
                    window.location.href = '/login';
                }, 500);
            } else {
                sessionStorage.removeItem('logout_in_progress');
                showError('登出失敗。請稍後再試。');
            }
        } catch (error) {
            console.error('登出失敗:', error);
            sessionStorage.removeItem('logout_in_progress');
            showError('登出失敗。請稍後再試。');
        }
    }
}

// ===== UI 顯示相關函數 =====

// 顯示錯誤訊息 - 持續顯示直到被替換
function showError(message) {
    // 先移除所有現有的提示訊息
    removeAllAlerts();
    
    const errorAlert = document.createElement('div');
    errorAlert.className = 'alert alert-danger alert-dismissible fade show persistent-alert';
    errorAlert.innerHTML = `
        <i class="bi bi-exclamation-triangle-fill me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // 添加到頁面頂部
    document.body.insertBefore(errorAlert, document.body.firstChild);
    
    // 不再自動消失
}

// 顯示成功訊息 - 添加自動消失功能
function showSuccess(message) {
    // 先移除所有現有的提示訊息
    removeAllAlerts();
    
    const successAlert = document.createElement('div');
    successAlert.className = 'alert alert-success alert-dismissible fade show persistent-alert';
    successAlert.innerHTML = `
        <i class="bi bi-check-circle-fill me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // 添加到頁面頂部
    document.body.insertBefore(successAlert, document.body.firstChild);
    
    // 3秒後自動消失
    setTimeout(() => {
        if (successAlert && successAlert.parentNode) {
            successAlert.classList.remove('show');
            successAlert.classList.add('fade');
            setTimeout(() => {
                if (successAlert.parentNode) {
                    successAlert.remove();
                }
            }, 150); // 等待fade動畫完成
        }
    }, 3000);
}

// 移除所有提示訊息
function removeAllAlerts() {
    document.querySelectorAll('.persistent-alert').forEach(alert => {
        alert.remove();
    });
}

// ===== Google Drive 檔案操作 =====

// 取得指定名稱的資料夾ID（假設已經有一份所有資料夾的列表，或需先查詢一次）
async function getFolderIdByName(folderName) {
    const response = await fetch(`${API_BASE_URL}/drive/files?folderOnly=true`);
    const data = await response.json();
    if (data.success) {
        const folder = data.files.find(f => f.name === folderName && f.mimeType === 'application/vnd.google-apps.folder');
        return folder ? folder.id : null;
    }
    return null;
}

// 載入 Google Drive 檔案 - 修改為同時載入兩種類型
async function loadDriveFiles() {
    // 檢查是否已認證，未認證則不繼續載入
    const authStatus = await checkAuthStatus();
    if (!authStatus) {
        showUnauthenticatedUI();
        return;
    }
    
    // 同時載入音訊檔案和 PDF 檔案
    await Promise.all([
        loadAudioFiles(),
        loadPdfFiles()
    ]);
}

// 載入音訊檔案列表
async function loadAudioFiles() {
    const fileList = document.getElementById('file-list');
    if (!fileList) return;
    
    try {
        // 檢查是否已認證
        const authStatus = await checkAuthStatus();
        if (!authStatus) {
            showUnauthenticatedUI();
            return;
        }
        
        // 顯示載入狀態
        elements.fileList.innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">正在載入您的音訊檔案...</p>
            </div>`;

        const queryParams = new URLSearchParams({
            fileType: 'audio',
            recordingsFilter: recordingsFilterEnabled ? 'enabled' : 'disabled'
        });
        if (recordingsFilterEnabled) {
            queryParams.append('recordingsFolderName', RECORDINGS_FOLDER);
        }
        
        const response = await fetch(`${API_BASE_URL}/api/drive/files?${queryParams.toString()}`);
        
        if (!response.ok) {
            if (response.status === 401) {
                throw new Error(`401 Unauthorized: Failed to load audio files. Session may be invalid.`);
            }
            throw new Error(`HTTP error ${response.status}: Failed to load audio files.`);
        }
        
        const data = await response.json();
        
        // 過濾音訊檔案
        let audioFiles = data.files.filter(file => isAudioFile(file.mimeType));
        
        console.log("載入的音訊檔案數量:", audioFiles.length);
        
        // 填充音訊文件列表
        if (audioFiles.length === 0) {
            elements.fileList.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle-fill me-2"></i>
                    ${recordingsFilterEnabled ? 
                        `未在 ${RECORDINGS_FOLDER} 資料夾中找到音訊檔案。請上傳音訊檔案到此資料夾。` : 
                        '未找到音訊檔案。請上傳音訊檔案到您的 Google Drive.'}
                </div>`;
        } else {
            elements.fileList.innerHTML = '';
            audioFiles.forEach(file => {
                const option = document.createElement('div');
                option.className = 'file-option';
                option.innerHTML = `
                    <input type="radio" name="audioFile" 
                           id="file-${file.id}" value="${file.id}" data-filename="${file.name}">
                    <div class="file-icon">
                        <i class="bi bi-file-earmark-music"></i>
                    </div>
                    <div class="file-details">
                        <div class="file-name">${file.name}</div>
                        <div class="file-size">${formatFileSize(file.size)}</div>
                    </div>
                `;
                // 點擊整個區域時選中
                option.addEventListener('click', function() {
                    const input = this.querySelector('input');
                    input.checked = true;
                    
                    // 移除其他選擇項的選中樣式
                    document.querySelectorAll('.file-option').forEach(el => {
                        el.classList.remove('selected');
                    });
                    
                    // 添加選中樣式
                    this.classList.add('selected');
                });
                elements.fileList.appendChild(option);
            });
        }
    } catch (error) {
        console.error('載入音訊檔案失敗:', error);
        
        let displayErrorMessage = error.message || '載入音訊檔案失敗。請重試。';

        if (error.message && error.message.startsWith('401 Unauthorized')) {
            displayErrorMessage = '載入 Google Drive 音訊檔案失敗，您的登入可能已失效。請嘗試重新登入。';
            showUnauthenticatedUI();
        }

        elements.fileList.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle-fill me-2" style="font-size: 1.5rem;"></i>
                ${displayErrorMessage}
            </div>`;
    }
}

// 載入 PDF 檔案列表
async function loadPdfFiles() {
    const attachmentList = document.getElementById('attachment-list');
    if (!attachmentList) return;
    
    try {
        // 檢查是否已認證
        const authStatus = await checkAuthStatus();
        if (!authStatus) {
            showUnauthenticatedUI();
            return;
        }
        
        // 顯示載入狀態
        elements.attachmentList.innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">正在載入您的 PDF 檔案...</p>
            </div>`;

        const queryParams = new URLSearchParams({
            fileType: 'pdf',
            pdfFilter: pdfFilterEnabled ? 'enabled' : 'disabled'
        });
        if (pdfFilterEnabled) {
            queryParams.append('pdfFolderName', DOCUMENTS_FOLDER);
        }
        
        const response = await fetch(`${API_BASE_URL}/api/drive/files?${queryParams.toString()}`);
        
        if (!response.ok) {
            if (response.status === 401) {
                throw new Error(`401 Unauthorized: Failed to load PDF files. Session may be invalid.`);
            }
            throw new Error(`HTTP error ${response.status}: Failed to load PDF files.`);
        }
        
        const data = await response.json();
        
        // 過濾 PDF 檔案
        let pdfFiles = data.files.filter(file => file.mimeType === 'application/pdf');
        
        console.log("載入的 PDF 檔案數量:", pdfFiles.length);
        
        // 填充附件文件列表
        if (pdfFiles.length === 0) {
            elements.attachmentList.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle-fill me-2" style="font-size: 1.5rem;"></i>
                    ${pdfFilterEnabled ? 
                        `未在 ${DOCUMENTS_FOLDER} 資料夾中找到 PDF 檔案。附件是選用的。` : 
                        '未找到 PDF 檔案。附件是選用的。'}
                </div>`;
        } else {
            elements.attachmentList.innerHTML = '';
            // 添加"無附件"選項
            const noneOption = document.createElement('div');
            noneOption.className = 'attachment-option none-option selected'; // Default selected
            noneOption.innerHTML = `
                <input type="checkbox" id="attachment-none" value="" data-none="true" checked>
                <div class="file-icon">
                    <i class="bi bi-slash-circle"></i>
                </div>
                <div class="file-details">
                    <div class="file-name">無附件</div>
                    <div class="file-size">不選擇附件檔案</div>
                </div>
            `;
            
            noneOption.addEventListener('click', function() {
                const input = this.querySelector('input');
                input.checked = true; // Clicking "None" always selects it
                this.classList.add('selected');
                
                // 取消所有其他附件的選擇
                document.querySelectorAll('.attachment-option:not(.none-option)').forEach(el => {
                    el.classList.remove('selected');
                    el.querySelector('input').checked = false;
                });
            });
            elements.attachmentList.appendChild(noneOption);
            
            // 添加PDF檔案
            pdfFiles.forEach(file => {
                const option = document.createElement('div');
                option.className = 'attachment-option';
                option.innerHTML = `
                    <input type="checkbox" 
                           id="attachment-${file.id}" value="${file.id}" data-filename="${file.name}">
                    <div class="file-icon">
                        <i class="bi bi-file-earmark-pdf"></i>
                    </div>
                    <div class="file-details">
                        <div class="file-name">${file.name}</div>
                        <div class="file-size">${formatFileSize(file.size)}</div>
                    </div>
                `;
                
                option.addEventListener('click', function() {
                    const input = this.querySelector('input');
                    input.checked = !input.checked; // Toggle current PDF's checked state
                    
                    if (input.checked) {
                        this.classList.add('selected');
                        // 選中了一個PDF附件，取消"無附件"的選擇
                        const noneOptionEl = document.querySelector('.attachment-option.none-option');
                        if (noneOptionEl) {
                            noneOptionEl.classList.remove('selected');
                            noneOptionEl.querySelector('input').checked = false;
                        }
                    } else {
                        this.classList.remove('selected');
                        // 如果取消選中後沒有任何其他PDF被選中，則自動選中"無附件"
                        const anyPdfSelected = Array.from(document.querySelectorAll('.attachment-option:not(.none-option) input[type="checkbox"]'))
                            .some(el => el.checked);
                        
                        if (!anyPdfSelected) {
                            const noneOptionEl = document.querySelector('.attachment-option.none-option');
                            if (noneOptionEl) {
                                noneOptionEl.classList.add('selected');
                                noneOptionEl.querySelector('input').checked = true;
                            }
                        }
                    }
                });
                elements.attachmentList.appendChild(option);
            });
        }
    } catch (error) {
        console.error('載入 PDF 檔案失敗:', error);
        
        let displayErrorMessage = error.message || '載入 PDF 檔案失敗。請重試。';

        if (error.message && error.message.startsWith('401 Unauthorized')) {
            displayErrorMessage = '載入 Google Drive PDF 檔案失敗，您的登入可能已失效。請嘗試重新登入。';
            showUnauthenticatedUI();
        }

        elements.attachmentList.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle-fill me-2" style="font-size: 1.5rem;"></i>
                ${displayErrorMessage}
            </div>`;
    }
}

// ===== 任務管理器 核心功能 =====

/**
 * 建立新任務 - 更新為包含持久化
 */
async function createNewTask() {
    const selectedFile = document.querySelector('input[name="audioFile"]:checked');
    if (!selectedFile) {
        showError('請先選擇一個音訊檔案');
        return;
    }
    
    // 確保當前用戶資訊存在
    if (!currentUser) {
        console.log('currentUser 為空，重新檢查認證狀態');
        const user = await checkAuthStatus();
        if (!user) {
            showError('用戶認證已失效，請重新登入');
            showUnauthenticatedUI();
            return;
        }
        currentUser = user;
    }
    
    // 獲取選中的附件
    const attachmentFileIds = [];
    const checkedAttachments = document.querySelectorAll('.attachment-option:not(.none-option) input[type="checkbox"]:checked');
    checkedAttachments.forEach(chk => {
        attachmentFileIds.push(chk.value);
    });
    
    const fileId = selectedFile.value;
    const fileName = selectedFile.getAttribute('data-filename');
    
    // 禁用建立按鈕
    elements.createTaskBtn.disabled = true;
    elements.createTaskBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>建立任務中...';
    
    try {
        const requestBody = { file_id: fileId };
        if (attachmentFileIds.length > 0) {
            requestBody.attachment_file_ids = attachmentFileIds;
        }

        const response = await fetch(`${API_BASE_URL}/api/process`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP error ${response.status}: ${errorData.error || response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            // 建立任務成功
            const newTask = {
                id: data.job_id,
                fileName: fileName,
                attachmentCount: attachmentFileIds.length,
                status: 'pending',
                progress: 0,
                message: '任務已建立，等待處理...',
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
                estimatedCompletion: calculateEstimatedTime('pending'),
                startTime: Date.now(),
                // 添加用戶關聯
                userId: currentUser ? currentUser.id : null
            };
            
            taskManager.tasks[data.job_id] = newTask;
            addTaskToUI(newTask);
            updateTaskCounts();
            
            // 立即保存任務
            saveCurrentTasks();
            console.log(`任務 ${data.job_id} 已建立並保存到 localStorage`);
            
            showSuccess(`任務已建立成功！任務ID: ${data.job_id.substring(0, 8)}...`);
            
            // 開始輪詢任務狀態
            startTaskPolling();
        } else {
            throw new Error(data.error || '任務建立失敗');
        }
    } catch (error) {
        console.error('建立任務失敗:', error);
        showError(`任務建立失敗: ${error.message}`);
    } finally {
        // 重置建立按鈕
        elements.createTaskBtn.disabled = false;
        elements.createTaskBtn.innerHTML = '<i class="bi bi-play-circle me-2"></i>開始處理選中的檔案';
    }
}

/**
 * 計算預估完成時間
 */
function calculateEstimatedTime(currentStage) {
    let totalTime = 0;
    let foundCurrent = false;
    
    for (const [stage, time] of Object.entries(taskManager.estimatedTimes)) {
        if (stage === currentStage) {
            foundCurrent = true;
        }
        if (!foundCurrent) {
            continue; // 跳過已完成的階段
        }
        totalTime += time;
    }
    
    return totalTime;
}

/**
 * 格式化剩餘時間 - 移除小數點
 */
function formatRemainingTime(seconds) {
    if (seconds <= 0) return '即將完成';
    
    const roundedSeconds = Math.round(seconds);
    const minutes = Math.floor(roundedSeconds / 60);
    const remainingSeconds = roundedSeconds % 60;
    
    if (minutes > 0) {
        return `約 ${minutes} 分 ${remainingSeconds} 秒`;
    } else {
        return `約 ${remainingSeconds} 秒`;
    }
}

/**
 * 添加任務到UI
 */
function addTaskToUI(task) {
    const tasksContainer = elements.tasksContainer;
    
    // 移除空狀態
    const emptyState = tasksContainer.querySelector('.task-empty-state');
    if (emptyState) {
        emptyState.style.display = 'none';
    }
    
    const taskElement = createTaskElement(task);
    tasksContainer.appendChild(taskElement);
}

/**
 * 建立任務UI元素
 */
function createTaskElement(task) {
    const taskDiv = document.createElement('div');
    taskDiv.className = 'task-item mb-3';
    taskDiv.setAttribute('data-task-id', task.id);
    taskDiv.setAttribute('data-task-status', task.status);
    
    const statusConfig = getStatusConfig(task.status);
    const progressWidth = Math.max(task.progress, 2); // 最小2%寬度確保可見性
    
    taskDiv.innerHTML = `
        <div class="card task-card ${statusConfig.cardClass}">
            <div class="card-body p-3">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="task-info flex-grow-1">
                        <h6 class="task-title mb-1">
                            <i class="${statusConfig.icon} me-2"></i>
                            ${task.fileName}
                            ${task.attachmentCount > 0 ? `<span class="badge bg-secondary ms-2">+${task.attachmentCount} 附件</span>` : ''}
                        </h6>
                        <small class="text-muted">
                            任務ID: ${task.id.substring(0, 8)}...
                        </small>
                    </div>
                    <div class="task-actions">
                        ${task.status === 'processing' || task.status === 'pending' ? 
                            `<button class="btn btn-sm btn-outline-danger" onclick="cancelTask('${task.id}')" title="取消任務">
                                <i class="bi bi-x-lg"></i>
                            </button>` : ''
                        }
                        ${task.status === 'completed' ? 
                            `<button class="btn btn-sm btn-success" onclick="viewResult('${task.id}')" title="查看結果">
                                <i class="bi bi-eye"></i>
                            </button>` : ''
                        }
                    </div>
                </div>
                
                <div class="task-progress mb-2">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="task-status-text ${statusConfig.textClass}">
                            ${statusConfig.label}
                        </span>
                        <span class="task-progress-text">
                            ${task.progress}%
                        </span>
                    </div>
                    <div class="progress task-progress-bar" style="height: 6px;">
                        <div class="progress-bar ${statusConfig.progressClass}" 
                             role="progressbar" 
                             style="width: ${progressWidth}%"
                             aria-valuenow="${task.progress}" 
                             aria-valuemin="0" 
                             aria-valuemax="100">
                        </div>
                    </div>
                </div>
                
                <div class="task-details">
                    <div class="task-message">
                        <small class="text-muted">
                            <i class="bi bi-info-circle me-1"></i>
                            ${task.message || '處理中...'}
                        </small>
                    </div>
                    ${task.status === 'processing' && task.estimatedCompletion > 0 ? 
                        `<div class="task-eta mt-1">
                            <small class="text-muted">
                                <i class="bi bi-clock me-1"></i>
                                預估剩餘時間: <span class="eta-text">${formatRemainingTime(task.estimatedCompletion)}</span>
                            </small>
                        </div>` : ''
                    }
                    <div class="task-timestamps mt-1">
                        <small class="text-muted">
                            建立時間: ${new Date(task.createdAt).toLocaleString()}
                            ${task.updatedAt !== task.createdAt ? 
                                `| 更新時間: ${new Date(task.updatedAt).toLocaleString()}` : ''
                            }
                        </small>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    return taskDiv;
}

/**
 * 獲取狀態配置
 */
function getStatusConfig(status) {
    const configs = {
        'pending': {
            label: '等待中',
            icon: 'bi bi-hourglass',
            cardClass: 'border-warning',
            textClass: 'text-warning',
            progressClass: 'bg-warning'
        },
        'processing': {
            label: '處理中',
            icon: 'bi bi-gear-fill spinning',
            cardClass: 'border-primary',
            textClass: 'text-primary',
            progressClass: 'bg-primary progress-bar-striped progress-bar-animated'
        },
        'completed': {
            label: '已完成',
            icon: 'bi bi-check-circle-fill',
            cardClass: 'border-success',
            textClass: 'text-success',
            progressClass: 'bg-success'
        },
        'failed': {
            label: '失敗',
            icon: 'bi bi-exclamation-triangle-fill',
            cardClass: 'border-danger',
            textClass: 'text-danger',
            progressClass: 'bg-danger'
        },
        'cancelled': {
            label: '已取消',
            icon: 'bi bi-x-circle-fill',
            cardClass: 'border-secondary',
            textClass: 'text-secondary',
            progressClass: 'bg-secondary'
        }
    };
    
    return configs[status] || configs['pending'];
}

/**
 * 更新任務計數
 */
function updateTaskCounts() {
    const tasks = Object.values(taskManager.tasks);
    const activeTasks = tasks.filter(task => 
        task.status === 'pending' || task.status === 'processing'
    );
    
    const activeCountElement = elements.activeTasksCount;
    if (activeCountElement) {
        activeCountElement.textContent = activeTasks.length;
        activeCountElement.className = activeTasks.length > 0 ? 'badge bg-primary ms-2' : 'badge bg-secondary ms-2';
    }
    
    // 確保有當前用戶時才自動保存任務
    if (currentUser && (currentUser.id || currentUser.email)) {
        saveCurrentTasks();
    } else {
        console.log('跳過自動保存：用戶資訊不完整');
    }
}

/**
 * 更新空狀態顯示
 */
function updateEmptyState() {
    const tasksContainer = elements.tasksContainer;
    if (!tasksContainer) return;
    
    const taskItems = tasksContainer.querySelectorAll('.task-item');
    const emptyState = tasksContainer.querySelector('.task-empty-state');
    
    if (taskItems.length === 0) {
        if (emptyState) {
            emptyState.style.display = 'block';
        } else {
            // 創建空狀態元素
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'task-empty-state text-center py-4';
            emptyDiv.innerHTML = `
                <i class="bi bi-inbox text-muted" style="font-size: 3rem;"></i>
                <p class="text-muted mt-2">目前沒有任務</p>
                <small class="text-muted">選擇音訊檔案後點擊上方按鈕開始處理</small>
            `;
            tasksContainer.appendChild(emptyDiv);
        }
    } else {
        if (emptyState) {
            emptyState.style.display = 'none';
        }
    }
}

/**
 * 篩選任務顯示
 */
function filterTasks() {
    const filter = taskManager.currentFilter;
    const taskItems = document.querySelectorAll('.task-item');
    
    let visibleCount = 0;
    
    taskItems.forEach(item => {
        const taskStatus = item.getAttribute('data-task-status');
        let shouldShow = false;
        
        switch (filter) {
            case 'active':
                shouldShow = taskStatus === 'pending' || taskStatus === 'processing';
                break;
            case 'completed':
                shouldShow = taskStatus === 'completed';
                break;
            case 'failed':
                shouldShow = taskStatus === 'failed' || taskStatus === 'cancelled';
                break;
            case 'all':
                shouldShow = true;
                break;
        }
        
        if (shouldShow) {
            item.style.display = 'block';
            visibleCount++;
        } else {
            item.style.display = 'none';
        }
    });
    
    // 如果沒有可見的任務，顯示相應的空狀態訊息
    const emptyState = elements.tasksContainer.querySelector('.task-empty-state');
    if (visibleCount === 0) {
        if (emptyState) {
            let message = '';
            switch (filter) {
                case 'active':
                    message = '目前沒有進行中的任務';
                    break;
                case 'completed':
                    message = '目前沒有已完成的任務';
                    break;
                case 'failed':
                    message = '目前沒有失敗的任務';
                    break;
                default:
                    message = '目前沒有任務';
            }
            emptyState.innerHTML = `
                <i class="bi bi-inbox text-muted" style="font-size: 3rem;"></i>
                <p class="text-muted mt-2">${message}</p>
                ${filter === 'active' ? '<small class="text-muted">選擇音訊檔案後點擊上方按鈕開始處理</small>' : ''}
            `;
            emptyState.style.display = 'block';
        }
    } else {
        if (emptyState) {
            emptyState.style.display = 'none';
        }
    }
}

/**
 * 切換任務管理器展開狀態
 */
function toggleTaskManager() {
    taskManager.isExpanded = !taskManager.isExpanded;
    
    const content = elements.taskManagerContent;
    const toggleIcon = document.getElementById('toggle-task-icon');
    
    if (taskManager.isExpanded) {
        content.style.display = 'block';
        if (toggleIcon) toggleIcon.className = 'bi bi-chevron-down';
    } else {
        content.style.display = 'none';
        if (toggleIcon) toggleIcon.className = 'bi bi-chevron-up';
    }
}

/**
 * 刷新任務狀態
 */
function refreshTasks() {
    const refreshIcon = document.getElementById('refresh-tasks-icon');
    if (refreshIcon) {
        refreshIcon.classList.add('rotating');
        setTimeout(() => {
            refreshIcon.classList.remove('rotating');
        }, 1000);
    }
    
    // 立即更新任務狀態
    updateTasksStatus();
}

// 設定檔案上傳的 MIME 類型
const SUPPORTED_MIME_TYPES = [
    'audio/mpeg', 'audio/mp4', 'audio/x-m4a', 'audio/mp3', 'audio/wav', 'audio/webm',
    'audio/ogg', 'audio/aac', 'audio/flac', 'audio/x-flac',
    'application/pdf', 'application/vnd.google-apps.document', 'application/vnd.google-apps.presentation'
];

// 檢查檔案類型是否支援
function isFileTypeSupported(mimeType) {
    return SUPPORTED_MIME_TYPES.includes(mimeType);
}

// 初始化頁面
function initApp() {
    console.log('應用程式初始化開始');
    
    // 檢查用戶認證狀態
    checkAuthStatus()
        .then(user => {
            if (user) {
                console.log('用戶已認證:', user.email);
                showAuthenticatedUI(user);
                // 載入檔案（在認證UI顯示後載入）
                loadDriveFiles();
            } else {
                console.log('用戶未認證');
                showUnauthenticatedUI();
            }
        })
        .catch(error => {
            console.error('認證檢查失敗:', error);
            showUnauthenticatedUI();
        });
    
    // 初始化任務管理器
    initTaskManager();
    
    console.log('應用程式初始化完成');
}

// 初始化任務管理器 - 更新為支援任務恢復
function initTaskManager() {
    // 如果用戶已認證，會在 showAuthenticatedUI 中恢復任務
    // 這裡不需要做任何事情
    console.log('任務管理器初始化完成');
}

// 頁面卸載時保存任務並停止輪詢
window.addEventListener('beforeunload', () => {
    console.log('頁面即將卸載，保存任務狀態');
    saveCurrentTasks();
    stopTaskPolling();
});

// 頁面隱藏時保存任務
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        console.log('頁面隱藏，保存任務狀態');
        saveCurrentTasks();
    } else {
        console.log('頁面重新顯示，檢查任務狀態');
        // 如果有活躍任務，重新開始輪詢
        const activeTasks = Object.values(taskManager.tasks).filter(
            task => task.status === 'pending' || task.status === 'processing'
        );
        if (activeTasks.length > 0 && !taskManager.updateTimer) {
            console.log(`頁面重新顯示，恢復 ${activeTasks.length} 個活躍任務的輪詢`);
            startTaskPolling();
        }
    }
});

// 定期自動保存（每30秒）
setInterval(() => {
    if (currentUser && Object.keys(taskManager.tasks).length > 0) {
        console.log('定期自動保存任務狀態');
        saveCurrentTasks();
    }
}, 30000);

// ===== 任務持久化相關函數 =====

/**
 * 恢復用戶任務
 */
function restoreUserTasks(userId) {
    try {
        // 確保有有效的用戶ID
        if (!userId && currentUser) {
            userId = currentUser.id || currentUser.email;
        }
        
        if (!userId) {
            console.log('無法恢復任務：用戶ID不存在');
            return;
        }
        
        console.log(`正在恢復用戶 ${userId} 的任務...`);
        
        // 執行日常清理檢查
        if (taskPersistence.shouldPerformDailyCleanup(userId)) {
            taskPersistence.performDailyCleanup(userId);
        }
        
        // 載入用戶任務
        const savedTasks = taskPersistence.loadTasks(userId);
        taskManager.tasks = savedTasks;
        
        console.log(`從 localStorage 載入的任務數據:`, savedTasks);
        console.log(`任務 IDs:`, Object.keys(savedTasks));
        
        // 更新UI
        refreshTasksUI();
        updateTaskCounts();
        
        // 如果有活躍任務，開始輪詢
        const activeTasks = Object.values(taskManager.tasks).filter(
            task => task.status === 'pending' || task.status === 'processing'
        );
        
        if (activeTasks.length > 0) {
            console.log(`發現 ${activeTasks.length} 個活躍任務，開始輪詢狀態`);
            console.log(`活躍任務詳情:`, activeTasks.map(t => ({ id: t.id, status: t.status, fileName: t.fileName })));
            startTaskPolling();
        }
        
        console.log(`成功恢復 ${Object.keys(savedTasks).length} 個任務`);
    } catch (error) {
        console.error('恢復用戶任務失敗:', error);
        taskManager.tasks = {}; // 重置為空
    }
}

/**
 * 保存當前任務
 */
function saveCurrentTasks() {
    if (!currentUser) {
        console.log('無法保存任務：當前用戶為 null，嘗試重新檢查認證狀態');
        // 嘗試從認證系統重新獲取用戶資訊
        checkAuthStatus().then(user => {
            if (user) {
                currentUser = user;
                console.log('重新獲取用戶資訊成功，再次嘗試保存任務');
                saveCurrentTasks();
            }
        });
        return;
    }
    
    if (!currentUser.id && !currentUser.email) {
        console.log('無法保存任務：當前用戶資訊不完整', currentUser);
        return;
    }
    
    try {
        // 使用 email 作為備用 ID
        const userId = currentUser.id || currentUser.email;
        const taskCount = Object.keys(taskManager.tasks).length;
        console.log(`正在為用戶 ${userId} 保存 ${taskCount} 個任務`);
        
        if (taskCount > 0) {
            console.log('保存的任務詳情:', Object.values(taskManager.tasks).map(t => ({ 
                id: t.id, 
                status: t.status, 
                fileName: t.fileName,
                progress: t.progress 
            })));
        }
        
        taskPersistence.saveTasks(userId, taskManager.tasks);
        console.log(`任務保存完成`);
    } catch (error) {
        console.error('保存任務失敗:', error);
    }
}

/**
 * 清理任務UI
 */
function clearTasksUI() {
    if (elements.tasksContainer) {
        elements.tasksContainer.innerHTML = '';
        updateEmptyState();
    }
    updateTaskCounts();
}

/**
 * 刷新任務UI
 */
function refreshTasksUI() {
    if (!elements.tasksContainer) return;
    
    // 清空現有任務
    elements.tasksContainer.innerHTML = '';
    
    // 重新添加所有任務
    Object.values(taskManager.tasks).forEach(task => {
        addTaskToUI(task);
    });
    
    // 應用當前篩選
    filterTasks();
    updateEmptyState();
}

// ===== 任務輪詢相關函數 =====

/**
 * 開始任務狀態輪詢
 */
function startTaskPolling() {
    // 如果已經在輪詢，先停止
    if (taskManager.updateTimer) {
        stopTaskPolling();
    }
    
    console.log('開始任務狀態輪詢...');
    
    // 立即執行一次更新
    updateTasksStatus();
    
    // 設置定時輪詢
    taskManager.updateTimer = setInterval(() => {
        updateTasksStatus();
    }, taskManager.updateInterval);
}

/**
 * 停止任務狀態輪詢
 */
function stopTaskPolling() {
    if (taskManager.updateTimer) {
        clearInterval(taskManager.updateTimer);
        taskManager.updateTimer = null;
        console.log('任務狀態輪詢已停止');
    }
}

/**
 * 更新任務狀態
 */
async function updateTasksStatus() {
    const activeTasks = Object.values(taskManager.tasks).filter(
        task => task.status === 'pending' || task.status === 'processing'
    );
    
    if (activeTasks.length === 0) {
        stopTaskPolling();
        return;
    }
    
    console.log(`正在更新 ${activeTasks.length} 個活躍任務的狀態...`);
    
    try {
        // 批量檢查所有活躍任務的狀態
        const taskIds = activeTasks.map(task => task.id);
        const response = await fetch(`${API_BASE_URL}/api/jobs/status/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_ids: taskIds })
        });
        
        if (!response.ok) {
            // 如果批量端點失敗，使用單個任務查詢作為後備方案
            if (response.status === 404) {
                console.log('批量狀態端點不可用，使用單個查詢後備方案');
                await updateTasksStatusFallback(activeTasks);
                return;
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.jobs) {
            let hasUpdates = false;
            
            Object.entries(data.jobs).forEach(([jobId, jobData]) => {
                if (taskManager.tasks[jobId]) {
                    const oldStatus = taskManager.tasks[jobId].status;
                    const oldProgress = taskManager.tasks[jobId].progress;
                    
                    console.log(`任務 ${jobId} 狀態更新: ${oldStatus} -> ${jobData.status}, 進度: ${oldProgress}% -> ${jobData.progress}%`);
                    
                    // 更新任務資料
                    updateTaskData(taskManager.tasks[jobId], jobData);
                    
                    // 檢查是否有變化
                    if (oldStatus !== taskManager.tasks[jobId].status || 
                        oldProgress !== taskManager.tasks[jobId].progress) {
                        hasUpdates = true;
                        
                        // 更新UI
                        updateTaskElementUI(jobId, taskManager.tasks[jobId]);
                        
                        // 如果任務完成，顯示通知
                        if (taskManager.tasks[jobId].status === 'completed' && oldStatus !== 'completed') {
                            showSuccess(`任務完成：${taskManager.tasks[jobId].fileName}`);
                        } else if (taskManager.tasks[jobId].status === 'failed' && oldStatus !== 'failed') {
                            showError(`任務失敗：${taskManager.tasks[jobId].fileName}`);
                        }
                    }
                }
            });
            
            if (hasUpdates) {
                updateTaskCounts();
                filterTasks();
                // 立即保存更新後的任務狀態
                saveCurrentTasks();
            }
        }
    } catch (error) {
        console.error('更新任務狀態失敗:', error);
        
        // 如果是認證錯誤，停止輪詢
        if (error.message.includes('401') || error.message.includes('Unauthorized')) {
            stopTaskPolling();
            showUnauthenticatedUI();
        } else {
            // 對於其他錯誤，嘗試使用後備方案
            console.log('嘗試使用單個任務查詢後備方案');
            await updateTasksStatusFallback(activeTasks);
        }
    }
}

/**
 * 後備方案：逐一查詢任務狀態
 */
async function updateTasksStatusFallback(activeTasks) {
    try {
        let hasUpdates = false;
        
        // 限制並發請求數量，避免過載
        const batchSize = 3;
        for (let i = 0; i < activeTasks.length; i += batchSize) {
            const batch = activeTasks.slice(i, i + batchSize);
            
            const promises = batch.map(async (task) => {
                try {
                    const response = await fetch(`${API_BASE_URL}/api/job/${task.id}`);
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    if (data.success && data.job) {
                        const oldStatus = task.status;
                        const oldProgress = task.progress;
                        
                        // 更新任務資料
                        updateTaskData(task, data.job);
                        
                        // 檢查是否有變化
                        if (oldStatus !== task.status || oldProgress !== task.progress) {
                            hasUpdates = true;
                            
                            // 更新UI
                            updateTaskElementUI(task.id, task);
                            
                            // 如果任務完成，顯示通知
                            if (task.status === 'completed' && oldStatus !== 'completed') {
                                showSuccess(`任務完成：${task.fileName}`);
                            } else if (task.status === 'failed' && oldStatus !== 'failed') {
                                showError(`任務失敗：${task.fileName}`);
                            }
                        }
                    }
                } catch (error) {
                    console.error(`獲取任務 ${task.id} 狀態失敗:`, error);
                }
            });
            
            await Promise.all(promises);
            
            // 在批次之間稍微延遲，避免過載
            if (i + batchSize < activeTasks.length) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }
        
        if (hasUpdates) {
            updateTaskCounts();
            filterTasks();
        }
    } catch (error) {
        console.error('後備方案更新任務狀態失敗:', error);
    }
}

/**
 * 查看任務結果
 */
async function viewResult(taskId) {
    const task = taskManager.tasks[taskId];
    if (!task) {
        showError('找不到任務資料');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/jobs/${taskId}/result`);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP ${response.status}: ${errorData.error || '獲取結果失敗'}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.result) {
            displayTaskResult(task, data.result);
        } else {
            throw new Error(data.error || '獲取結果失敗');
        }
    } catch (error) {
        console.error('獲取任務結果失敗:', error);
        showError(`獲取結果失敗: ${error.message}`);
    }
}

// ===== 輔助函數 =====

// 檢查是否為音訊檔案
function isAudioFile(mimeType) {
    const audioMimeTypes = [
        'audio/mpeg', 'audio/mp4', 'audio/x-m4a', 'audio/mp3', 'audio/wav', 'audio/webm',
        'audio/ogg', 'audio/aac', 'audio/flac', 'audio/x-flac'
    ];
    return audioMimeTypes.includes(mimeType);
}

// 格式化檔案大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
}

/**
 * 更新任務資料
 */
function updateTaskData(task, jobData) {
    task.status = jobData.status || task.status;
    task.progress = Math.round(jobData.progress || 0);
    task.message = jobData.message || task.message;
    task.updatedAt = new Date().toISOString();
    
    // 更新預估完成時間
    if (task.status === 'processing' && task.startTime) {
        const elapsed = (Date.now() - task.startTime) / 1000;
        const progressRate = task.progress / elapsed;
        const remainingProgress = 100 - task.progress;
        task.estimatedCompletion = remainingProgress / progressRate;
    } else {
        task.estimatedCompletion = calculateEstimatedTime(task.status);
    }
    
    // 如果任務完成或失敗，保存結果資料
    if (jobData.result) {
        task.result = jobData.result;
    }
}

/**
 * 更新任務元素UI
 */
function updateTaskElementUI(taskId, task) {
    const taskElement = document.querySelector(`[data-task-id="${taskId}"]`);
    if (!taskElement) return;
    
    const statusConfig = getStatusConfig(task.status);
    const progressWidth = Math.max(task.progress, 2);
    
    // 更新狀態屬性
    taskElement.setAttribute('data-task-status', task.status);
    
    // 更新卡片樣式
    const card = taskElement.querySelector('.task-card');
    if (card) {
        card.className = `card task-card ${statusConfig.cardClass}`;
    }
    
    // 更新狀態圖標和文字
    const statusIcon = taskElement.querySelector('.task-title i');
    const statusText = taskElement.querySelector('.task-status-text');
    if (statusIcon) statusIcon.className = `${statusConfig.icon} me-2`;
    if (statusText) {
        statusText.textContent = statusConfig.label;
        statusText.className = `task-status-text ${statusConfig.textClass}`;
    }
    
    // 更新進度條
    const progressBar = taskElement.querySelector('.progress-bar');
    const progressText = taskElement.querySelector('.task-progress-text');
    if (progressBar) {
        progressBar.style.width = `${progressWidth}%`;
        progressBar.setAttribute('aria-valuenow', task.progress);
        progressBar.className = `progress-bar ${statusConfig.progressClass}`;
    }
    if (progressText) {
        progressText.textContent = `${task.progress}%`;
    }
    
    // 更新訊息
    const messageElement = taskElement.querySelector('.task-message small');
    if (messageElement) {
        messageElement.innerHTML = `<i class="bi bi-info-circle me-1"></i>${task.message || '處理中...'}`;
    }
    
    // 更新預估時間
    const etaElement = taskElement.querySelector('.eta-text');
    if (etaElement && task.status === 'processing' && task.estimatedCompletion > 0) {
        etaElement.textContent = formatRemainingTime(task.estimatedCompletion);
    }
    
    // 更新時間戳記
    const timestampElement = taskElement.querySelector('.task-timestamps small');
    if (timestampElement) {
        timestampElement.innerHTML = `
            建立時間: ${new Date(task.createdAt).toLocaleString()}
            ${task.updatedAt !== task.createdAt ? 
                `| 更新時間: ${new Date(task.updatedAt).toLocaleString()}` : ''
            }
        `;
    }
    
    // 更新操作按鈕
    const actionsContainer = taskElement.querySelector('.task-actions');
    if (actionsContainer) {
        let buttonsHtml = '';
        
        if (task.status === 'processing' || task.status === 'pending') {
            buttonsHtml += `
                <button class="btn btn-sm btn-outline-danger" onclick="cancelTask('${task.id}')" title="取消任務">
                    <i class="bi bi-x-lg"></i>
                </button>
            `;
        }
        
        if (task.status === 'completed') {
            buttonsHtml += `
                <button class="btn btn-sm btn-success" onclick="viewResult('${task.id}')" title="查看結果">
                    <i class="bi bi-eye"></i>
                </button>
            `;
        }
        
        actionsContainer.innerHTML = buttonsHtml;
    }
}

// ===== 任務操作函數 =====

/**
 * 取消任務 - 修復API路徑並添加調試信息
 */
async function cancelTask(taskId) {
    if (!confirm('確定要取消這個任務嗎？')) {
        return;
    }
    
    console.log(`嘗試取消任務: ${taskId}`);
    console.log(`當前本地任務狀態:`, taskManager.tasks[taskId]);
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/job/${taskId}/cancel`, {
            method: 'POST'
        });
        
        console.log(`取消任務響應狀態: ${response.status}`);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error(`取消任務失敗，錯誤數據:`, errorData);
            throw new Error(`HTTP ${response.status}: ${errorData.error || '取消任務失敗'}`);
        }
        
        const data = await response.json();
        console.log(`取消任務響應數據:`, data);
        
        if (data.success) {
            // 更新本地任務狀態
            if (taskManager.tasks[taskId]) {
                taskManager.tasks[taskId].status = 'cancelled';
                taskManager.tasks[taskId].message = '任務已取消';
                taskManager.tasks[taskId].updatedAt = new Date().toISOString();
                
                updateTaskElementUI(taskId, taskManager.tasks[taskId]);
                updateTaskCounts();
                filterTasks();
                saveCurrentTasks();
                
                console.log(`本地任務狀態已更新為已取消`);
            }
            
            showSuccess('任務已成功取消');
        } else {
            throw new Error(data.error || '取消任務失敗');
        }
    } catch (error) {
        console.error('取消任務失敗:', error);
        showError(`取消任務失敗: ${error.message}`);
    }
}

/**
 * 查看任務結果
 */
async function viewResult(taskId) {
    const task = taskManager.tasks[taskId];
    if (!task) {
        showError('找不到任務資料');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/jobs/${taskId}/result`);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP ${response.status}: ${errorData.error || '獲取結果失敗'}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.result) {
            displayTaskResult(task, data.result);
        } else {
            throw new Error(data.error || '獲取結果失敗');
        }
    } catch (error) {
        console.error('獲取任務結果失敗:', error);
        showError(`獲取結果失敗: ${error.message}`);
    }
}

/**
 * 顯示任務結果
 */
function displayTaskResult(task, result) {
    // 更新結果顯示區域
    if (elements.resultTitle) {
        elements.resultTitle.textContent = `處理結果 - ${task.fileName}`;
    }
    
    if (elements.resultSummary && result.summary) {
        elements.resultSummary.innerHTML = result.summary.replace(/\n/g, '<br>');
    }
    
    if (elements.resultTodos && result.todos) {
        elements.resultTodos.innerHTML = Array.isArray(result.todos) 
            ? result.todos.map(todo => `<li>${todo}</li>`).join('')
            : result.todos.replace(/\n/g, '<br>');
    }
    
    if (elements.resultSpeakers && result.speakers) {
        elements.resultSpeakers.innerHTML = Array.isArray(result.speakers)
            ? result.speakers.map(speaker => `<li>${speaker}</li>`).join('')
            : result.speakers.replace(/\n/g, '<br>');
    }
    
    if (elements.resultLink && result.document_url) {
        elements.resultLink.href = result.document_url;
        elements.resultLink.textContent = '查看完整文件';
        elements.resultLink.style.display = 'inline-block';
    }
    
    // 顯示結果區域
    if (elements.resultContainer) {
        elements.resultContainer.classList.remove('d-none');
        elements.resultContainer.scrollIntoView({ behavior: 'smooth' });
    }
}

// 添加調試函數
async function debugJobsStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/jobs/debug`);
        const data = await response.json();
        console.log('伺服器端任務狀態:', data);
        return data;
    } catch (error) {
        console.error('獲取調試信息失敗:', error);
    }
}

// 在開發者控制台中可以調用這個函數來查看任務狀態
window.debugJobsStatus = debugJobsStatus;