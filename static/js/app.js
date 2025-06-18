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
    processBtn: document.getElementById('process-btn'),
    showActiveJobsBtn: document.getElementById('show-active-jobs-btn'),
    
    // 結果顯示區
    jobsList: document.getElementById('jobs-list'),
    resultTitle: document.getElementById('result-title'),
    resultSummary: document.getElementById('result-summary'),
    resultTodos: document.getElementById('result-todos'),
    resultLink: document.getElementById('result-link'),
    resultSpeakers: document.getElementById('result-speakers'),
    
    // 進度指示
    progressPercentage: document.getElementById('progress-percentage'),
};

// 初始化頁面
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupEventListeners();
});

// 初始化應用程式
function initApp() {
    // 檢查用戶認證狀態
    checkAuthStatus()
        .then(isAuthenticated => {
            if (isAuthenticated) {
                showAuthenticatedUI();
                // 只有在已認證的情況下才載入檔案
                loadDriveFiles();
                startActiveJobsPolling();
            } else {
                // 未認證用戶將顯示未認證的UI
                showUnauthenticatedUI();
            }
        })
        .catch(error => {
            console.error('認證檢查失敗:', error);
            showUnauthenticatedUI();
        });
}

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
    
    // 處理檔案按鈕
    if (elements.processBtn) {
        elements.processBtn.addEventListener('click', processSelectedFile);
    }
    
    // 顯示活躍任務按鈕
    if (elements.showActiveJobsBtn) {
        elements.showActiveJobsBtn.addEventListener('click', toggleActiveJobs);
    }

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

// 顯示成功訊息 - 持續顯示直到被替換
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
    
    // 不再自動消失
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
                <div class="spinner-border" role="status"></div> 
                <p class="mt-3">正在載入您的音訊檔案...</p>
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
                <div class="spinner-border" role="status"></div> 
                <p class="mt-3">正在載入您的 PDF 檔案...</p>
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

// 處理選擇的檔案
async function processSelectedFile() {
    const selectedFile = document.querySelector('input[name="audioFile"]:checked');
    if (!selectedFile) {
        showError('請先選擇一個音訊檔案');
        return;
    }
    
    const attachmentFileIds = [];
    const attachmentFileNames = [];
    if (elements.attachmentList) {
        const checkedAttachments = document.querySelectorAll('.attachment-option:not(.none-option) input[type="checkbox"]:checked');
        checkedAttachments.forEach(chk => {
            attachmentFileIds.push(chk.value);
            attachmentFileNames.push(chk.getAttribute('data-filename'));
        });
    }
    
    const fileId = selectedFile.value;
    const fileName = selectedFile.getAttribute('data-filename');

    elements.processBtn.disabled = true;
    elements.processBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 處理中...';
    
    try {
        const requestBody = {
            file_id: fileId,
        };
        if (attachmentFileIds.length > 0) {
            requestBody.attachment_file_ids = attachmentFileIds;
        }

        const response = await fetch(`${API_BASE_URL}/process`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({})); // Try to parse error
            throw new Error(`HTTP error ${response.status}: ${errorData.error || response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            elements.progressContainer.classList.remove('d-none');
            elements.resultContainer.classList.add('d-none');
            
            const fileInfo = `處理檔案: ${fileName}`;
            const attachmentInfo = attachmentFileNames.length > 0 ? ` (附件: ${attachmentFileNames.join(', ')})` : '';
            elements.processingStatus.innerHTML = `<i class="bi bi-cpu me-2"></i>${fileInfo}${attachmentInfo}`;
            
            currentJobId = data.job_id;
            checkJobStatus(data.job_id);
            
            showSuccess('檔案處理已開始，請稍候...');
        } else {
            showError(data.error || data.message || '處理請求失敗');
            resetProcessButton();
        }
    } catch (error) {
        console.error('處理請求失敗:', error);
        showError(`處理請求失敗: ${error.message || '請稍後再試。'}`);
        resetProcessButton();
    }
}

// 重設處理按鈕狀態
function resetProcessButton() {
    if (elements.processBtn) {
        elements.processBtn.disabled = false;
        elements.processBtn.innerHTML = '處理選中的檔案';
    }
}

// ===== 任務狀態管理 =====

// 檢查任務狀態
async function checkJobStatus(jobId) {
    try {
        const response = await fetch(`${API_BASE_URL}/job/${jobId}`);
        
        // 先檢查狀態碼，再解析JSON
        if (response.status === 404) {
            // 檢查是否為當前正在處理的任務
            if (currentJobId === jobId) {
                // 增加重試次數限制
                if (!job.retryCount) {
                    job.retryCount = 1;
                } else {
                    job.retryCount++;
                }
                
                // 如果重試次數超過5次，則認為任務已失效
                if (job.retryCount > 5) {
                    console.error(`任務 ${jobId} 重試次數過多，認為任務已失效`);
                    showError(`任務狀態檢查失敗，請重新提交處理請求`);
                    resetProcessButton();
                    clearTimeout(jobStatusTimer);
                    currentJobId = null;
                    return;
                }
                
                console.warn(`任務 ${jobId} 暫時無法獲取狀態，第 ${job.retryCount} 次重試...`);
                // 使用指數退避策略增加重試間隔
                const retryDelay = Math.min(2000 * Math.pow(2, job.retryCount - 1), 30000);
                jobStatusTimer = setTimeout(() => checkJobStatus(jobId), retryDelay);
                return;
            } else {
                console.error(`任務 ${jobId} 不存在，可能已過期或被刪除`);
                showError(`任務不存在或已過期，請重新提交處理請求`);
                resetProcessButton();
                clearTimeout(jobStatusTimer);
                currentJobId = null;
                return;
            }
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}: ${data.error || '未知錯誤'}`);
        }
        
        if (data.success && data.job) {
            const job = data.job;
            
            // 重置重試計數
            job.retryCount = 0;
            
            // 更新進度條
            elements.processingBar.style.width = `${job.progress}%`;
            elements.processingBar.setAttribute('aria-valuenow', job.progress);
            elements.progressPercentage.textContent = `${job.progress}%`;
            
            // 更新狀態訊息
            if (job.message) {
                elements.processingStatus.textContent = job.message;
            }
            
            // 檢查任務狀態
            if (job.status === 'completed') {
                jobCompleted(job);
                clearTimeout(jobStatusTimer);
                currentJobId = null;
            } else if (job.status === 'failed') {
                jobFailed(job);
                clearTimeout(jobStatusTimer);
                currentJobId = null;
            } else {
                // 任務尚未完成，繼續檢查狀態
                jobStatusTimer = setTimeout(() => checkJobStatus(jobId), 2000);
            }
        } else {
            showError(data.message || '獲取任務狀態失敗');
            resetProcessButton();
            clearTimeout(jobStatusTimer);
            currentJobId = null;
        }
    } catch (error) {
        console.error('檢查任務狀態失敗:', error);
        // 如果是當前正在處理的任務，繼續嘗試
        if (currentJobId === jobId) {
            // 增加重試次數限制
            if (!job.retryCount) {
                job.retryCount = 1;
            } else {
                job.retryCount++;
            }
            
            // 如果重試次數超過5次，則認為任務已失效
            if (job.retryCount > 5) {
                console.error(`任務 ${jobId} 重試次數過多，認為任務已失效`);
                showError(`任務狀態檢查失敗，請重新提交處理請求`);
                resetProcessButton();
                clearTimeout(jobStatusTimer);
                currentJobId = null;
                return;
            }
            
            console.warn('任務狀態檢查失敗，將繼續嘗試...');
            // 使用指數退避策略增加重試間隔
            const retryDelay = Math.min(2000 * Math.pow(2, job.retryCount - 1), 30000);
            jobStatusTimer = setTimeout(() => checkJobStatus(jobId), retryDelay);
        } else {
            showError(`檢查任務狀態失敗: ${error.message}`);
            resetProcessButton();
            clearTimeout(jobStatusTimer);
            currentJobId = null;
        }
    }
}

// 任務完成處理
function jobCompleted(job) {
    // 啟用處理按鈕
    resetProcessButton();
    
    // 顯示結果區域
    elements.progressContainer.classList.add('d-none');
    elements.resultContainer.classList.remove('d-none');
    
    const result = job.result;
    
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
            elements.resultLink.innerHTML = '<i class="bi bi-link-45deg me-2"></i> 在 Notion 中查看';
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
            } else {
                elements.resultSpeakers.innerHTML = '<p><i class="bi bi-info-circle me-1"></i> 未識別說話人</p>';
            }
        }
    }
    
    // 顯示成功消息
    showSuccess('檔案處理完成！');
}

// 任務失敗處理
function jobFailed(job) {
    // 啟用處理按鈕
    resetProcessButton();
    
    // 顯示錯誤訊息
    const errorMsg = job.error || '未知錯誤';
    showError(`處理失敗: ${errorMsg}`);
    
    // 隱藏進度區域
    elements.progressContainer.classList.add('d-none');
    
    // 在控制台輸出詳細錯誤信息以便調試
    console.error('任務處理失敗:', job);
}

// ===== 活躍任務管理 =====

// 開始輪詢活躍任務
function startActiveJobsPolling() {
    // 先取得一次活躍任務
    fetchActiveJobs();
    
    // 設定定時器，每 2 秒更新一次
    activeJobsTimer = setInterval(fetchActiveJobs, 2000);
}

// 停止輪詢活躍任務
function stopActiveJobsPolling() {
    if (activeJobsTimer) {
        clearInterval(activeJobsTimer);
        activeJobsTimer = null;
    }
}

// 獲取活躍任務
async function fetchActiveJobs() {
    try {
        const response = await fetch(`${API_BASE_URL}/jobs?filter=active`);
        
        if (!response.ok) {
            // 如果是 404 或其他錯誤，不要立即更新 UI，而是保持當前狀態
            console.warn(`獲取活躍任務失敗，狀態碼: ${response.status}，保持當前狀態`);
            return;
        }
        
        const data = await response.json();
        
        if (data.success) {
            // 檢查數據是否真的發生變化
            const currentJobsData = JSON.stringify(data.active_jobs || {});
            if (currentJobsData === lastActiveJobsData) {
                return; // 如果數據沒有變化，不更新 UI
            }
            lastActiveJobsData = currentJobsData;
            
            // 使用防抖動更新 UI
            if (activeJobsUpdateTimeout) {
                clearTimeout(activeJobsUpdateTimeout);
            }
            
            activeJobsUpdateTimeout = setTimeout(() => {
                // 更新活躍任務按鈕顯示
                const activeJobsCount = Object.keys(data.active_jobs || {}).length;
                
                if (elements.showActiveJobsBtn) {
                    // 只有在數量真正改變時才更新按鈕文字
                    const currentText = elements.showActiveJobsBtn.textContent;
                    const newText = activeJobsCount > 0 ? `活躍任務 (${activeJobsCount})` : '活躍任務';
                    
                    if (currentText !== newText) {
                        elements.showActiveJobsBtn.textContent = newText;
                        elements.showActiveJobsBtn.classList.toggle('btn-outline-primary', activeJobsCount > 0);
                        elements.showActiveJobsBtn.classList.toggle('btn-outline-secondary', activeJobsCount === 0);
                    }
                }
                
                // 更新任務列表（如果已顯示）
                if (!elements.jobsList.classList.contains('d-none')) {
                    updateJobsList(data.active_jobs || {});
                }
            }, 300); // 300ms 的防抖動延遲
        }
    } catch (error) {
        console.error('獲取活躍任務失敗:', error);
        // 發生錯誤時不更新 UI，保持當前狀態
    }
}

// 更新任務列表
function updateJobsList(jobs) {
    if (!elements.jobsList) return;
    
    const jobIds = Object.keys(jobs);
    
    // 如果沒有任務，且當前列表為空，則不進行任何更新
    if (jobIds.length === 0 && elements.jobsList.querySelector('.alert-info')) {
        return;
    }
    
    // 如果沒有任務，顯示提示訊息
    if (jobIds.length === 0) {
        // 檢查是否已經顯示了相同的提示訊息
        const existingAlert = elements.jobsList.querySelector('.alert-info');
        if (existingAlert && existingAlert.textContent.includes('目前沒有活躍的任務')) {
            return;
        }
        
        elements.jobsList.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle-fill me-2"></i> 
                目前沒有活躍的任務
            </div>`;
        return;
    }
    
    // 創建新的容器來存放更新後的內容
    const newContent = document.createElement('div');
    
    // 為每個任務創建卡片
    jobIds.forEach(jobId => {
        const job = jobs[jobId];
        const card = document.createElement('div');
        card.className = 'card mb-3';
        card.id = `job-card-${jobId}`; // 添加唯一ID
        
        // 根據任務狀態設置卡片顏色
        let statusBadge = '';
        let statusIcon = '';
        
        if (job.status === 'pending') {
            statusBadge = '<span class="badge bg-warning" style="font-size: 0.75rem;">等待中</span>';
            statusIcon = '<i class="bi bi-hourglass me-1"></i>';
        } else if (job.status === 'processing') {
            statusBadge = '<span class="badge bg-info">處理中</span>';
            statusIcon = '<i class="bi bi-gear-fill me-1 spinning"></i>';
        }
        
        // 格式化時間
        const createdTime = new Date(job.created_at).toLocaleString();
        const updatedTime = new Date(job.updated_at).toLocaleString();
        
        const cardContent = `
            <div class="card-body">
                <h5 class="card-title">${statusIcon} 任務 ${statusBadge}</h5>
                <div class="progress mb-3">
                    <div class="progress-bar" role="progressbar" style="width: ${job.progress}%;" 
                         aria-valuenow="${job.progress}" aria-valuemin="0" aria-valuemax="100">
                        ${job.progress}%
                    </div>
                </div>
                <p class="card-text">${job.message || '處理中...'}</p>
                <p class="card-text">
                    <small class="text-muted">
                        <i class="bi bi-calendar-event me-1"></i> 創建於: ${createdTime}<br>
                        <i class="bi bi-clock me-1"></i> 更新於: ${updatedTime}
                    </small>
                </p>
            </div>
        `;
        
        // 檢查是否存在相同的卡片
        const existingCard = document.getElementById(`job-card-${jobId}`);
        if (existingCard) {
            // 如果卡片存在，只更新內容
            existingCard.innerHTML = cardContent;
        } else {
            // 如果卡片不存在，創建新的卡片
            card.innerHTML = cardContent;
            newContent.appendChild(card);
        }
    });
    
    // 如果沒有新的卡片需要添加，直接返回
    if (newContent.children.length === 0) {
        return;
    }
    
    // 一次性更新 DOM，減少閃爍
    elements.jobsList.appendChild(newContent);
}

// 切換顯示/隱藏活躍任務列表
function toggleActiveJobs() {
    const isVisible = !elements.jobsList.classList.contains('d-none');
    
    if (isVisible) {
        // 隱藏任務列表
        elements.jobsList.classList.add('d-none');
    } else {
        // 顯示任務列表並更新內容
        elements.jobsList.classList.remove('d-none');
        elements.jobsList.innerHTML = `
            <div class="loading-container">
                <div class="spinner-border" role="status">
                    <span class="visually-hidden">載入中...</span>
                </div>
                <p>正在載入活躍任務...</p>
            </div>
        `;
        fetchActiveJobs();
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