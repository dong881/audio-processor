// 全局變數
const API_BASE_URL = '';  // 空字串表示相對路徑
let googleAuthInitialized = false;
let activeJobsTimer = null;
let currentJobId = null;
let jobStatusTimer = null;
let redirectBlocked = false; // 防止循環跳轉的標記
let lastActiveJobsData = null; // 用於存儲上一次的任務數據
let activeJobsUpdateTimeout = null; // 用於防抖動

// Add global variables for folder filtering
let recordingsFilterEnabled = false;
let pdfFilterEnabled = false;
const RECORDINGS_FOLDER = 'WearNote_Recordings';
const DOCUMENTS_FOLDER = 'WearNote_Recordings/Documents';

// Task Manager 相關變數
let taskManager = {
    isExpanded: true,
    currentFilter: 'active',
    tasks: {},
    updateTimer: null,
    updateInterval: 2000,
    estimatedTimes: {
        'pending': 0,
        'downloading': 30,
        'converting': 60,
        'transcribing': 300,
        'analyzing': 120,
        'generating': 90,
        'uploading': 45,
        'finalizing': 15
    }
};

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

    // 錄音資料夾過濾切換開關
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
        if (recordingsFilterEnabled) {
            const toggleTrack = recordingsFilterToggle.nextElementSibling.querySelector('.toggle-track');
            if (toggleTrack) toggleTrack.classList.add('active');
        }
        
        recordingsFilterToggle.addEventListener('change', function(e) {
            recordingsFilterEnabled = e.target.checked;
            
            // 提供視覺反饋
            const toggleLabel = this.nextElementSibling;
            if (toggleLabel) {
                toggleLabel.classList.add('pulse');
                setTimeout(() => toggleLabel.classList.remove('pulse'), 300);
            }
            
            // 保存偏好設置
            localStorage.setItem('filter-recordings-enabled', recordingsFilterEnabled);
            
            // 只重新載入音訊檔案列表
            loadAudioFiles();
        });
    }
    
    // PDF資料夾過濾切換開關
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
        if (pdfFilterEnabled) {
            const toggleTrack = pdfFilterToggle.nextElementSibling.querySelector('.toggle-track');
            if (toggleTrack) toggleTrack.classList.add('active');
        }
        
        pdfFilterToggle.addEventListener('change', function(e) {
            pdfFilterEnabled = e.target.checked;
            
            // 提供視覺反饋
            const toggleLabel = this.nextElementSibling;
            if (toggleLabel) {
                toggleLabel.classList.add('pulse');
                setTimeout(() => toggleLabel.classList.remove('pulse'), 300);
            }
            
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

// ===== 認證相關函數 =====

// 檢查用戶認證狀態 - 簡化版本，委託給auth.js處理
async function checkAuthStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/status`);
        
        if (!response.ok) {
            console.error(`認證狀態檢查失敗，錯誤碼: ${response.status}`);
            return null;
        }
        
        const data = await response.json();
        
        if (data.authenticated && data.user) {
            return data.user;
        } else {
            return null;
        }
    } catch (error) {
        console.error('檢查認證狀態時出錯:', error);
        return null;
    }
}

// 顯示已認證用戶界面 - 接受用戶參數
function showAuthenticatedUI(user) {
    if (elements.authSection) elements.authSection.classList.add('d-none');
    if (elements.processingSection) elements.processingSection.classList.remove('d-none');
    if (elements.loginButtons.length > 0) {
        elements.loginButtons.forEach(button => {
            button.classList.add('d-none');
        });
    }
    if (elements.logoutButton) elements.logoutButton.classList.remove('d-none');
    
    // 如果有用戶資訊，也更新UI
    if (user && typeof updateUserInfoUI === 'function') {
        updateUserInfoUI(user);
    }
}

// 顯示未認證用戶界面
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
}

// 處理登入
function handleLogin() {
    window.location.href = `${API_BASE_URL}/api/auth/google`;
}

// 處理登出
async function handleLogout() {
    // 使用 auth.js 中的 logoutUser 函数，它包含了防止循環重定向的邏輯
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
        
        const response = await fetch(`${API_BASE_URL}/drive/files?${queryParams.toString()}`);
        
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
        
        const response = await fetch(`${API_BASE_URL}/drive/files?${queryParams.toString()}`);
        
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

// ===== Task Manager 核心功能 =====

/**
 * 建立新任務
 */
async function createNewTask() {
    const selectedFile = document.querySelector('input[name="audioFile"]:checked');
    if (!selectedFile) {
        showError('請先選擇一個音訊檔案');
        return;
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

        const response = await fetch(`${API_BASE_URL}/process`, {
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
                startTime: Date.now()
            };
            
            taskManager.tasks[data.job_id] = newTask;
            addTaskToUI(newTask);
            updateTaskCounts();
            
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
 * 取消任務
 */
async function cancelTask(taskId) {
    if (!confirm('確定要取消這個任務嗎？此操作無法復原。')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/job/${taskId}/cancel`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                // 更新本地任務狀態
                if (taskManager.tasks[taskId]) {
                    taskManager.tasks[taskId].status = 'cancelled';
                    taskManager.tasks[taskId].message = '任務已被使用者取消';
                    taskManager.tasks[taskId].updatedAt = new Date().toISOString();
                    updateTaskInUI(taskManager.tasks[taskId]);
                    updateTaskCounts();
                }
                showSuccess('任務已取消');
            } else {
                throw new Error(data.error || '取消任務失敗');
            }
        } else {
            throw new Error(`HTTP ${response.status}: 取消請求失敗`);
        }
    } catch (error) {
        console.error('取消任務失敗:', error);
        showError(`取消任務失敗: ${error.message}`);
    }
}

/**
 * 查看任務結果
 */
function viewResult(taskId) {
    const task = taskManager.tasks[taskId];
    if (!task || !task.result) {
        showError('無法找到任務結果');
        return;
    }
    
    // 顯示結果 - 重用現有的結果顯示邏輯
    displayTaskResult(task.result);
}

/**
 * 顯示任務結果
 */
function displayTaskResult(result) {
    // 顯示結果區域
    elements.resultContainer.classList.remove('d-none');
    
    // 填充結果資訊
    if (elements.resultTitle) {
        elements.resultTitle.innerHTML = `<i class="bi bi-file-text me-2"></i>${result.title || '未知標題'}`;
    }
    
    if (elements.resultSummary) {
        elements.resultSummary.textContent = result.summary || '未生成摘要';
    }
    
    if (elements.resultTodos) {
        elements.resultTodos.innerHTML = '';
        if (result.todos && result.todos.length > 0) {
            result.todos.forEach(todo => {
                const li = document.createElement('li');
                li.innerHTML = `<i class="bi bi-check-square me-1"></i> ${todo}`;
                elements.resultTodos.appendChild(li);
            });
        } else {
            elements.resultTodos.innerHTML = '<li><i class="bi bi-info-circle me-1"></i> 未找到待辦事項</li>';
        }
    }
    
    if (elements.resultLink) {
        if (result.notion_page_url) {
            elements.resultLink.href = result.notion_page_url;
            elements.resultLink.classList.remove('d-none');
        } else {
            elements.resultLink.classList.add('d-none');
        }
    }
    
    if (elements.resultSpeakers) {
        elements.resultSpeakers.innerHTML = '';
        if (result.identified_speakers) {
            const speakers = Object.entries(result.identified_speakers);
            if (speakers.length > 0) {
                elements.resultSpeakers.innerHTML = '<h6 class="fw-bold"><i class="bi bi-people-fill me-2"></i> 識別的說話人:</h6><ul>';
                speakers.forEach(([id, name]) => {
                    elements.resultSpeakers.innerHTML += `<li><i class="bi bi-person me-1"></i> ${name} (${id})</li>`;
                });
                elements.resultSpeakers.innerHTML += '</ul>';
            }
        }
    }
    
    // 滾動到結果區域
    elements.resultContainer.scrollIntoView({ behavior: 'smooth' });
}

/**
 * 更新任務在UI中的顯示 - 優化以減少閃爍
 */
function updateTaskInUI(task) {
    const taskElement = document.querySelector(`[data-task-id="${task.id}"]`);
    if (!taskElement) {
        // 如果元素不存在，創建新的
        addTaskToUI(task);
        return;
    }
    
    // 更新狀態屬性
    taskElement.setAttribute('data-task-status', task.status);
    
    // 獲取狀態配置
    const statusConfig = getStatusConfig(task.status);
    const progressWidth = Math.max(task.progress, 2);
    
    // 只更新需要變更的元素，而不是重新創建整個任務元素
    
    // 更新狀態圖標
    const statusIcon = taskElement.querySelector('.task-title i');
    if (statusIcon) {
        statusIcon.className = `${statusConfig.icon} me-2`;
    }
    
    // 更新卡片邊框樣式
    const card = taskElement.querySelector('.task-card');
    if (card) {
        card.className = `card task-card ${statusConfig.cardClass}`;
    }
    
    // 更新狀態文字
    const statusText = taskElement.querySelector('.task-status-text');
    if (statusText) {
        statusText.textContent = statusConfig.label;
        statusText.className = `task-status-text ${statusConfig.textClass}`;
    }
    
    // 更新進度百分比
    const progressText = taskElement.querySelector('.task-progress-text');
    if (progressText) {
        progressText.textContent = `${task.progress}%`;
    }
    
    // 更新進度條
    const progressBar = taskElement.querySelector('.progress-bar');
    if (progressBar) {
        progressBar.style.width = `${progressWidth}%`;
        progressBar.setAttribute('aria-valuenow', task.progress);
        progressBar.className = `progress-bar ${statusConfig.progressClass}`;
    }
    
    // 更新訊息
    const messageElement = taskElement.querySelector('.task-message small');
    if (messageElement) {
        messageElement.innerHTML = `<i class="bi bi-info-circle me-1"></i>${task.message || '處理中...'}`;
    }
    
    // 更新預估時間（僅在處理中時顯示）
    let etaElement = taskElement.querySelector('.task-eta');
    if (task.status === 'processing' && task.estimatedCompletion > 0) {
        if (!etaElement) {
            // 創建預估時間元素
            const etaDiv = document.createElement('div');
            etaDiv.className = 'task-eta mt-1';
            etaDiv.innerHTML = `
                <small class="text-muted">
                    <i class="bi bi-clock me-1"></i>
                    預估剩餘時間: <span class="eta-text">${formatRemainingTime(task.estimatedCompletion)}</span>
                </small>
            `;
            const messageElement = taskElement.querySelector('.task-message');
            if (messageElement) {
                messageElement.after(etaDiv);
            }
        } else {
            // 更新現有的預估時間
            const etaText = etaElement.querySelector('.eta-text');
            if (etaText) {
                etaText.textContent = formatRemainingTime(task.estimatedCompletion);
            }
        }
    } else if (etaElement) {
        // 移除預估時間元素
        etaElement.remove();
    }
    
    // 更新時間戳
    const timestampsElement = taskElement.querySelector('.task-timestamps small');
    if (timestampsElement) {
        timestampsElement.innerHTML = `
            建立時間: ${new Date(task.createdAt).toLocaleString()}
            ${task.updatedAt !== task.createdAt ? 
                `| 更新時間: ${new Date(task.updatedAt).toLocaleString()}` : ''
            }
        `;
    }
    
    // 更新操作按鈕
    const actionsElement = taskElement.querySelector('.task-actions');
    if (actionsElement) {
        let actionsHTML = '';
        if (task.status === 'processing' || task.status === 'pending') {
            actionsHTML = `
                <button class="btn btn-sm btn-outline-danger" onclick="cancelTask('${task.id}')" title="取消任務">
                    <i class="bi bi-x-lg"></i>
                </button>
            `;
        } else if (task.status === 'completed') {
            actionsHTML = `
                <button class="btn btn-sm btn-success" onclick="viewResult('${task.id}')" title="查看結果">
                    <i class="bi bi-eye"></i>
                </button>
            `;
        }
        actionsElement.innerHTML = actionsHTML;
    }
}

/**
 * 開始任務輪詢
 */
function startTaskPolling() {
    if (taskManager.updateTimer) return; // 已經在輪詢中
    
    taskManager.updateTimer = setInterval(updateTasksStatus, taskManager.updateInterval);
    updateTasksStatus(); // 立即執行一次
}

/**
 * 停止任務輪詢
 */
function stopTaskPolling() {
    if (taskManager.updateTimer) {
        clearInterval(taskManager.updateTimer);
        taskManager.updateTimer = null;
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
    
    // 同時更新所有活躍任務
    const updatePromises = activeTasks.map(task => updateSingleTaskStatus(task.id));
    await Promise.allSettled(updatePromises);
    
    updateTaskCounts();
}

/**
 * 更新單個任務狀態
 */
async function updateSingleTaskStatus(taskId) {
    try {
        const response = await fetch(`${API_BASE_URL}/job/${taskId}`);
        
        if (!response.ok) {
            if (response.status === 404) {
                // 任務不存在，可能已過期
                if (taskManager.tasks[taskId]) {
                    taskManager.tasks[taskId].status = 'failed';
                    taskManager.tasks[taskId].message = '任務已過期或不存在';
                    updateTaskInUI(taskManager.tasks[taskId]);
                }
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.job) {
            const serverTask = data.job;
            const localTask = taskManager.tasks[taskId];
            
            if (!localTask) return;
            
            // 更新本地任務資料
            localTask.status = serverTask.status;
            localTask.progress = serverTask.progress;
            localTask.message = serverTask.message || localTask.message;
            localTask.updatedAt = serverTask.updated_at;
            
            // 計算預估剩餘時間
            if (serverTask.status === 'processing') {
                const elapsedTime = (Date.now() - localTask.startTime) / 1000;
                const progressRatio = serverTask.progress / 100;
                
                if (progressRatio > 0) {
                    const estimatedTotal = elapsedTime / progressRatio;
                    localTask.estimatedCompletion = Math.max(0, estimatedTotal - elapsedTime);
                }
            }
            
            // 如果任務完成，保存結果
            if (serverTask.status === 'completed' && serverTask.result) {
                localTask.result = serverTask.result;
            }
            
            // 如果任務失敗，保存錯誤信息
            if (serverTask.status === 'failed' && serverTask.error) {
                localTask.error = serverTask.error;
                localTask.message = `錯誤: ${serverTask.error}`;
            }
            
            updateTaskInUI(localTask);
        }
    } catch (error) {
        console.error(`更新任務 ${taskId} 狀態失敗:`, error);
    }
}

/**
 * 重新整理任務
 */
function refreshTasks() {
    const refreshIcon = document.getElementById('refresh-tasks-icon');
    if (refreshIcon) {
        refreshIcon.classList.add('rotating');
        setTimeout(() => refreshIcon.classList.remove('rotating'), 1000);
    }
    
    updateTasksStatus();
}

/**
 * 切換任務管理器展開/收合
 */
function toggleTaskManager() {
    const content = elements.taskManagerContent;
    const toggleIcon = document.getElementById('toggle-task-icon');
    
    taskManager.isExpanded = !taskManager.isExpanded;
    
    if (taskManager.isExpanded) {
        content.style.display = 'block';
        toggleIcon.className = 'bi bi-chevron-down';
    } else {
        content.style.display = 'none';
        toggleIcon.className = 'bi bi-chevron-right';
    }
}

/**
 * 篩選任務
 */
function filterTasks() {
    const filter = taskManager.currentFilter;
    const taskElements = document.querySelectorAll('.task-item');
    
    taskElements.forEach(element => {
        const status = element.getAttribute('data-task-status');
        let shouldShow = false;
        
        switch (filter) {
            case 'active':
                shouldShow = status === 'pending' || status === 'processing';
                break;
            case 'completed':
                shouldShow = status === 'completed';
                break;
            case 'failed':
                shouldShow = status === 'failed' || status === 'cancelled';
                break;
            case 'all':
                shouldShow = true;
                break;
        }
        
        element.style.display = shouldShow ? 'block' : 'none';
    });
    
    // 檢查是否需要顯示空狀態
    updateEmptyState();
}

/**
 * 更新空狀態顯示
 */
function updateEmptyState() {
    const visibleTasks = document.querySelectorAll('.task-item[style*="block"], .task-item:not([style*="none"])');
    const emptyState = elements.tasksContainer.querySelector('.task-empty-state');
    
    if (visibleTasks.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
    } else {
        if (emptyState) emptyState.style.display = 'none';
    }
}

/**
 * 更新任務計數
 */
function updateTaskCounts() {
    const activeCount = Object.values(taskManager.tasks).filter(
        task => task.status === 'pending' || task.status === 'processing'
    ).length;
    
    elements.activeTasksCount.textContent = activeCount;
    elements.activeTasksCount.className = activeCount > 0 ? 'badge bg-primary ms-2' : 'badge bg-secondary ms-2';
}

// 修改初始化函數
function initApp() {
    // 檢查用戶認證狀態
    checkAuthStatus()
        .then(isAuthenticated => {
            if (isAuthenticated) {
                showAuthenticatedUI();
                // 只有在已認證的情況下才載入檔案
                loadDriveFiles();
            } else {
                // 未認證用戶將顯示未認證的UI
                showUnauthenticatedUI();
            }
        })
        .catch(error => {
            console.error('認證檢查失敗:', error);
            showUnauthenticatedUI();
        });
    
    // 初始化任務管理器
    initTaskManager();
}

/**
 * 初始化任務管理器
 */
function initTaskManager() {
    // 開始輪詢活躍任務（如果有的話）
    checkAndStartPolling();
}

/**
 * 檢查並開始輪詢
 */
async function checkAndStartPolling() {
    try {
        const response = await fetch(`${API_BASE_URL}/jobs?filter=active`);
        
        if (response.ok) {
            const data = await response.json();
            const activeTasks = data.active_jobs || {};
            
            // 將伺服器任務轉換為本地任務格式
            Object.entries(activeTasks).forEach(([taskId, serverTask]) => {
                taskManager.tasks[taskId] = {
                    id: taskId,
                    fileName: '未知檔案', // 伺服器沒有提供檔案名稱
                    attachmentCount: 0,
                    status: serverTask.status,
                    progress: serverTask.progress,
                    message: serverTask.message || '處理中...',
                    createdAt: serverTask.created_at,
                    updatedAt: serverTask.updated_at,
                    estimatedCompletion: 0,
                    startTime: new Date(serverTask.created_at).getTime()
                };
                
                addTaskToUI(taskManager.tasks[taskId]);
            });
            
            updateTaskCounts();
            
            if (Object.keys(activeTasks).length > 0) {
                startTaskPolling();
            }
        }
    } catch (error) {
        console.error('檢查活躍任務失敗:', error);
    }
}

// 頁面卸載時停止輪詢
window.addEventListener('beforeunload', () => {
    stopTaskPolling();
});
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