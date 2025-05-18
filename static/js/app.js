// 全局變數
const API_BASE_URL = '/api';
const RECORDINGS_FOLDER = 'WearNote_Recordings';
const DOCUMENTS_FOLDER = 'WearNote_Recordings/Documents';
const MAX_RETRY_COUNT = 5;
const INITIAL_RETRY_DELAY = 1000; // 初始重試延遲
const MAX_RETRY_DELAY = 30000; // 最大重試延遲
const POLLING_INTERVAL = 2000;
const MAX_POLLING_INTERVAL = 10000; // 最大輪詢間隔

let googleAuthInitialized = false;
let activeJobsTimer = null;
let currentJobId = null;
let jobStatusTimer = null;
let redirectBlocked = false;
let lastActiveJobsData = null;
let activeJobsUpdateTimeout = null;
let recordingsFilterEnabled = true;
let pdfFilterEnabled = true;
let currentPollingInterval = POLLING_INTERVAL;

// 任務列表更新相關
let jobUpdateInterval = null;
let lastUpdateTime = null;
const UPDATE_INTERVAL = 2000; // 2秒更新一次

// DOM 元素快取
const elements = {
    fileList: document.getElementById('file-list'),
    attachmentList: document.getElementById('attachment-list'),
    progressContainer: document.getElementById('progress-container'),
    processingBar: document.getElementById('processing-bar'),
    processingStatus: document.getElementById('processing-status'),
    resultContainer: document.getElementById('result-container'),
    authSection: document.getElementById('auth-section'),
    processingSection: document.getElementById('processing-section'),
    loginButtons: [
        document.getElementById('login-button'),
        document.getElementById('login-btn')
    ].filter(Boolean),
    logoutButton: document.getElementById('logout-button'),
    refreshFilesBtn: document.getElementById('refresh-files-btn'),
    processBtn: document.getElementById('process-btn'),
    showActiveJobsBtn: document.getElementById('show-active-jobs-btn'),
    jobsList: document.getElementById('jobs-list'),
    resultTitle: document.getElementById('result-title'),
    resultSummary: document.getElementById('result-summary'),
    resultTodos: document.getElementById('result-todos'),
    resultLink: document.getElementById('result-link'),
    resultSpeakers: document.getElementById('result-speakers'),
    progressPercentage: document.getElementById('progress-percentage'),
};

// 初始化頁面
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupEventListeners();
    initializeFilters();
    startJobUpdates();
});

// 初始化應用程式
async function initApp() {
    try {
        const isAuthenticated = await checkAuthStatus();
        if (isAuthenticated) {
            showAuthenticatedUI();
            await loadDriveFiles();
            startActiveJobsPolling();
        } else {
            showUnauthenticatedUI();
        }
    } catch (error) {
        console.error('初始化失敗:', error);
        showUnauthenticatedUI();
    }
}

// 設置事件監聽器
function setupEventListeners() {
    elements.loginButtons.forEach(button => button?.addEventListener('click', handleLogin));
    elements.logoutButton?.addEventListener('click', handleLogout);
    elements.refreshFilesBtn?.addEventListener('click', handleRefreshFiles);
    elements.processBtn?.addEventListener('click', processSelectedFile);
    elements.showActiveJobsBtn?.addEventListener('click', toggleActiveJobs);
    setupFilterToggles();
    initializeTooltips();
}

// 初始化過濾器
function initializeFilters() {
    recordingsFilterEnabled = localStorage.getItem('filter-recordings-enabled') !== 'false';
    pdfFilterEnabled = localStorage.getItem('filter-pdf-enabled') !== 'false';
}

// 設置過濾器開關
function setupFilterToggles() {
    const recordingsFilterToggle = document.getElementById('filter-recordings-toggle');
    const pdfFilterToggle = document.getElementById('filter-pdf-toggle');

    if (recordingsFilterToggle) {
        recordingsFilterToggle.checked = recordingsFilterEnabled;
        recordingsFilterToggle.addEventListener('change', e => handleFilterChange(e, 'recordings'));
    }

    if (pdfFilterToggle) {
        pdfFilterToggle.checked = pdfFilterEnabled;
        pdfFilterToggle.addEventListener('change', e => handleFilterChange(e, 'pdf'));
    }
}

// 處理過濾器變更
function handleFilterChange(event, type) {
    const isEnabled = event.target.checked;
    const storageKey = `filter-${type}-enabled`;
    
    if (type === 'recordings') {
        recordingsFilterEnabled = isEnabled;
    } else {
        pdfFilterEnabled = isEnabled;
    }
    
    localStorage.setItem(storageKey, isEnabled);
    loadDriveFiles();
}

// 初始化工具提示
function initializeTooltips() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    if (typeof bootstrap !== 'undefined') {
        tooltipTriggerList.forEach(el => {
            new bootstrap.Tooltip(el, {
                animation: true,
                trigger: 'hover focus',
                boundary: document.body,
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
    }
}

// 處理刷新文件
async function handleRefreshFiles() {
    const refreshIcon = document.getElementById('refresh-icon');
    if (refreshIcon) {
        refreshIcon.classList.add('rotating');
        setTimeout(() => refreshIcon.classList.remove('rotating'), 1000);
    }
    await loadDriveFiles();
}

// 檢查認證狀態
async function checkAuthStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/status`);
        if (!response.ok) return null;
        
        const data = await response.json();
        if (data.authenticated && (!data.user || data.user.id === "unknown")) {
            return await refreshUserInfo();
        }
        return data.user;
    } catch (error) {
        console.error('認證檢查失敗:', error);
        return null;
    }
}

// 刷新用戶資訊
async function refreshUserInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/userinfo`);
        if (!response.ok) return false;
        
        const userData = await response.json();
        if (userData.success && userData.user) {
            showAuthenticatedUI(userData.user);
            return true;
        }
        return false;
    } catch (error) {
        console.error('刷新用戶資訊失敗:', error);
        return false;
    }
}

// 處理登入
function handleLogin() {
    window.location.href = `${API_BASE_URL}/auth/google`;
}

// 處理登出
async function handleLogout() {
    try {
        await fetch(`${API_BASE_URL}/auth/logout`);
        window.location.reload();
    } catch (error) {
        console.error('登出失敗:', error);
        showError('登出失敗。請稍後再試。');
    }
}

// 顯示錯誤訊息
function showError(message) {
    removeAllAlerts();
    const errorAlert = createAlert('danger', message);
    document.body.insertBefore(errorAlert, document.body.firstChild);
}

// 顯示成功訊息
function showSuccess(message) {
    removeAllAlerts();
    const successAlert = createAlert('success', message);
    document.body.insertBefore(successAlert, document.body.firstChild);
}

// 創建提示訊息
function createAlert(type, message) {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show persistent-alert`;
    alert.innerHTML = `
        <i class="bi bi-${type === 'danger' ? 'exclamation-triangle' : 'check-circle'}-fill me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    return alert;
}

// 移除所有提示訊息
function removeAllAlerts() {
    document.querySelectorAll('.persistent-alert').forEach(alert => alert.remove());
}

// 顯示已認證用戶界面
function showAuthenticatedUI(userInfo) {
    elements.authSection?.classList.add('d-none');
    elements.processingSection?.classList.remove('d-none');
    elements.loginButtons.forEach(button => button?.classList.add('d-none'));
    elements.logoutButton?.classList.remove('d-none');

    const userProfileCard = document.getElementById('user-profile-card');
    if (userProfileCard && userInfo) {
        userProfileCard.innerHTML = `
            <div class="d-flex align-items-center">
                <img src="${userInfo.picture || '/static/img/default-avatar.png'}" 
                     alt="${userInfo.name || 'User'}" 
                     class="rounded-circle me-2" 
                     style="width: 32px; height: 32px;">
                <div>
                    <div class="fw-bold">${userInfo.name || 'User'}</div>
                    <div class="small text-muted">${userInfo.email || ''}</div>
                </div>
            </div>
        `;
    }
}

// 顯示未認證用戶界面
function showUnauthenticatedUI() {
    elements.authSection?.classList.remove('d-none');
    elements.processingSection?.classList.add('d-none');
    elements.loginButtons.forEach(button => button?.classList.remove('d-none'));
    elements.logoutButton?.classList.add('d-none');
}

// 載入 Google Drive 檔案
async function loadDriveFiles() {
    if (!elements.fileList) return;
    
    try {
        const authStatus = await checkAuthStatus();
        if (!authStatus) {
            showUnauthenticatedUI();
            return;
        }
        
        showLoadingState();
        
        const queryParams = new URLSearchParams({
            recordingsFilter: recordingsFilterEnabled ? 'enabled' : 'disabled',
            pdfFilter: pdfFilterEnabled ? 'enabled' : 'disabled'
        });
        
        if (recordingsFilterEnabled) {
            queryParams.append('recordingsFolderName', RECORDINGS_FOLDER);
        }
        if (pdfFilterEnabled) {
            queryParams.append('pdfFolderName', DOCUMENTS_FOLDER);
        }
        
        const response = await fetch(`${API_BASE_URL}/drive/files?${queryParams.toString()}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        
        const data = await response.json();
        updateFileLists(data.files);
        
    } catch (error) {
        console.error('載入檔案失敗:', error);
        showFileLoadError(error);
    }
}

// 顯示載入狀態
function showLoadingState() {
    const loadingHTML = `
        <div class="text-center">
            <div class="spinner-border" role="status"></div> 
            <p class="mt-3">正在載入您的檔案...</p>
        </div>`;
    
    elements.fileList.innerHTML = loadingHTML;
    if (elements.attachmentList) {
        elements.attachmentList.innerHTML = loadingHTML;
    }
}

// 更新檔案列表
function updateFileLists(files) {
    const audioFiles = files.filter(file => isAudioFile(file.mimeType));
    const pdfFiles = files.filter(file => file.mimeType === 'application/pdf');
    
    updateAudioFileList(audioFiles);
    updateAttachmentList(pdfFiles);
}

// 更新音訊檔案列表
function updateAudioFileList(audioFiles) {
    if (!elements.fileList) return;
    
    if (audioFiles.length === 0) {
        elements.fileList.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle-fill me-2"></i>
                ${recordingsFilterEnabled ? 
                    `未在 ${RECORDINGS_FOLDER} 資料夾中找到音訊檔案。請上傳音訊檔案到此資料夾。` : 
                    '未找到音訊檔案。請上傳音訊檔案到您的 Google Drive.'}
            </div>`;
        return;
    }
    
    elements.fileList.innerHTML = '';
    audioFiles.forEach(file => {
        const option = createFileOption(file, 'audio');
        elements.fileList.appendChild(option);
    });
}

// 更新附件列表
function updateAttachmentList(pdfFiles) {
    if (!elements.attachmentList) return;
    
    if (pdfFiles.length === 0) {
        elements.attachmentList.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle-fill me-2"></i>
                ${pdfFilterEnabled ? 
                    `未在 ${DOCUMENTS_FOLDER} 資料夾中找到 PDF 檔案。附件是選用的。` : 
                    '未找到 PDF 檔案。附件是選用的。'}
            </div>`;
        return;
    }
    
    elements.attachmentList.innerHTML = '';
    const noneOption = createNoneOption();
    elements.attachmentList.appendChild(noneOption);
    
    pdfFiles.forEach(file => {
        const option = createFileOption(file, 'pdf');
        elements.attachmentList.appendChild(option);
    });
}

// 創建檔案選項
function createFileOption(file, type) {
    const option = document.createElement('div');
    option.className = `${type === 'audio' ? 'file' : 'attachment'}-option`;
    
    const inputType = type === 'audio' ? 'radio' : 'checkbox';
    const iconClass = type === 'audio' ? 'file-earmark-music' : 'file-earmark-pdf';
    
    option.innerHTML = `
        <input type="${inputType}" 
               name="${type === 'audio' ? 'audioFile' : 'attachment'}" 
               id="${type}-${file.id}" 
               value="${file.id}" 
               data-filename="${file.name}">
        <div class="file-icon">
            <i class="bi bi-${iconClass}"></i>
        </div>
        <div class="file-details">
            <div class="file-name">${file.name}</div>
            <div class="file-size">${formatFileSize(file.size)}</div>
        </div>
    `;
    
    option.addEventListener('click', () => handleFileOptionClick(option, type));
    return option;
}

// 創建無附件選項
function createNoneOption() {
    const option = document.createElement('div');
    option.className = 'attachment-option none-option selected';
    option.innerHTML = `
        <input type="checkbox" id="attachment-none" value="" data-none="true" checked>
        <div class="file-icon">
            <i class="bi bi-slash-circle"></i>
        </div>
        <div class="file-details">
            <div class="file-name">無附件</div>
            <div class="file-size">不選擇附件檔案</div>
        </div>
    `;
    
    option.addEventListener('click', handleNoneOptionClick);
    return option;
}

// 處理檔案選項點擊
function handleFileOptionClick(option, type) {
    const input = option.querySelector('input');
    const isAudio = type === 'audio';
    
    if (isAudio) {
        document.querySelectorAll('.file-option').forEach(el => el.classList.remove('selected'));
        input.checked = true;
        option.classList.add('selected');
    } else {
        input.checked = !input.checked;
        option.classList.toggle('selected', input.checked);
        
        if (input.checked) {
            const noneOption = document.querySelector('.attachment-option.none-option');
            if (noneOption) {
                noneOption.classList.remove('selected');
                noneOption.querySelector('input').checked = false;
            }
        } else {
            const anyPdfSelected = Array.from(document.querySelectorAll('.attachment-option:not(.none-option) input[type="checkbox"]'))
                .some(el => el.checked);
            
            if (!anyPdfSelected) {
                const noneOption = document.querySelector('.attachment-option.none-option');
                if (noneOption) {
                    noneOption.classList.add('selected');
                    noneOption.querySelector('input').checked = true;
                }
            }
        }
    }
}

// 處理無附件選項點擊
function handleNoneOptionClick() {
    const input = this.querySelector('input');
    input.checked = true;
    this.classList.add('selected');
    
    document.querySelectorAll('.attachment-option:not(.none-option)').forEach(el => {
        el.classList.remove('selected');
        el.querySelector('input').checked = false;
    });
}

// 顯示檔案載入錯誤
function showFileLoadError(error) {
    const displayErrorMessage = error.message?.startsWith('401') ?
        '載入 Google Drive 檔案失敗，您的登入可能已失效。請嘗試重新登入。' :
        '載入檔案失敗。請重試。';
    
    const errorHTML = `
        <div class="alert alert-danger">
            <i class="bi bi-exclamation-triangle-fill me-2"></i>
            ${displayErrorMessage}
        </div>`;
    
    elements.fileList.innerHTML = errorHTML;
    if (elements.attachmentList) {
        elements.attachmentList.innerHTML = errorHTML;
    }
    
    if (error.message?.startsWith('401')) {
        showUnauthenticatedUI();
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
    
    if (elements.processBtn) {
        elements.processBtn.disabled = true;
        elements.processBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 處理中...';
    }
    
    try {
        const requestBody = {
            file_id: fileId,
            ...(attachmentFileIds.length > 0 && { attachment_file_ids: attachmentFileIds })
        };
        
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
            if (elements.progressContainer) {
                elements.progressContainer.classList.remove('d-none');
            }
            if (elements.resultContainer) {
                elements.resultContainer.classList.add('d-none');
            }
            
            const fileInfo = `處理檔案: ${fileName}`;
            const attachmentInfo = attachmentFileNames.length > 0 ? ` (附件: ${attachmentFileNames.join(', ')})` : '';
            if (elements.processingStatus) {
                elements.processingStatus.innerHTML = `<i class="bi bi-cpu me-2"></i>${fileInfo}${attachmentInfo}`;
            }
            
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

// 檢查任務狀態
async function checkJobStatus(jobId) {
    if (!window.activeJobs) {
        window.activeJobs = new Map();
    }
    
    let job = window.activeJobs.get(jobId) || {
        retryCount: 0,
        lastError: null,
        lastErrorTime: null,
        lastStatus: null,
        lastProgress: 0
    };
    
    try {
        const response = await fetch(`${API_BASE_URL}/job/${jobId}`);
        
        if (response.status === 404) {
            if (currentJobId === jobId) {
                job.retryCount++;
                job.lastError = '404 Not Found';
                job.lastErrorTime = Date.now();
                
                if (job.retryCount > MAX_RETRY_COUNT) {
                    handleJobError(jobId, '任務重試次數過多，認為任務已失效');
                    return;
                }
                
                const retryDelay = Math.min(RETRY_DELAY * Math.pow(2, job.retryCount - 1), 30000);
                console.warn(`任務 ${jobId} 暫時無法獲取狀態，第 ${job.retryCount} 次重試...`);
                jobStatusTimer = setTimeout(() => checkJobStatus(jobId), retryDelay);
                return;
            } else {
                window.activeJobs.delete(jobId);
                return;
            }
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}: ${data.error || '未知錯誤'}`);
        }
        
        if (data.success && data.job) {
            handleJobUpdate(jobId, data.job);
        } else {
            handleJobError(jobId, data.message || '獲取任務狀態失敗');
        }
    } catch (error) {
        console.error('檢查任務狀態失敗:', error);
        handleJobError(jobId, error.message);
    }
}

// 處理任務更新
function handleJobUpdate(jobId, jobData) {
    const job = window.activeJobs.get(jobId);
    if (!job) return;
    
    job.retryCount = 0;
    job.lastError = null;
    job.lastErrorTime = null;
    job.lastStatus = jobData.status;
    job.lastProgress = jobData.progress;
    
    updateProgressUI(jobData);
    
    if (jobData.status === 'completed') {
        jobCompleted(jobData);
        clearTimeout(jobStatusTimer);
        currentJobId = null;
        window.activeJobs.delete(jobId);
    } else if (jobData.status === 'failed') {
        jobFailed(jobData);
        clearTimeout(jobStatusTimer);
        currentJobId = null;
        window.activeJobs.delete(jobId);
    } else {
        jobStatusTimer = setTimeout(() => checkJobStatus(jobId), POLLING_INTERVAL);
    }
}

// 更新進度 UI
function updateProgressUI(jobData) {
    elements.processingBar.style.width = `${jobData.progress}%`;
    elements.processingBar.setAttribute('aria-valuenow', jobData.progress);
    elements.progressPercentage.textContent = `${jobData.progress}%`;
    
    if (jobData.message) {
        elements.processingStatus.textContent = jobData.message;
    }
}

// 處理任務錯誤
function handleJobError(jobId, errorMessage) {
    if (currentJobId === jobId) {
        showError(`任務狀態檢查失敗，請重新提交處理請求`);
        resetProcessButton();
        clearTimeout(jobStatusTimer);
        currentJobId = null;
    }
    window.activeJobs.delete(jobId);
}

// 任務完成處理
function jobCompleted(job) {
    resetProcessButton();
    if (elements.progressContainer) {
        elements.progressContainer.classList.add('d-none');
    }
    if (elements.resultContainer) {
        elements.resultContainer.classList.remove('d-none');
    }
    
    const result = job.result;
    
    if (elements.resultTitle) {
        elements.resultTitle.innerHTML = `<i class="bi bi-file-text me-2"></i>${result.title || '未知標題'}`;
    }
    
    if (elements.resultSummary) {
        elements.resultSummary.textContent = result.summary || '未生成摘要';
    }
    
    if (elements.resultTodos) {
        elements.resultTodos.innerHTML = '';
        if (result.todos?.length > 0) {
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
    
    showSuccess('檔案處理完成！');
}

// 任務失敗處理
function jobFailed(job) {
    resetProcessButton();
    if (elements.progressContainer) {
        elements.progressContainer.classList.add('d-none');
    }
    showError(`處理失敗: ${job.error || '未知錯誤'}`);
    console.error('任務處理失敗:', job);
}

// 開始輪詢活躍任務
function startActiveJobsPolling() {
    if (activeJobsTimer) {
        clearInterval(activeJobsTimer);
    }
    
    fetchActiveJobs();
    activeJobsTimer = setInterval(() => {
        fetchActiveJobs().catch(error => {
            console.error('Error in active jobs polling:', error);
        });
    }, POLLING_INTERVAL);
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
        
        if (!response) {
            console.warn('Empty response from server when fetching active jobs');
            return;
        }
        
        if (!response.ok) {
            if (response.status === 503) {
                console.warn('Server is temporarily unavailable');
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch active jobs');
        }
        
        updateActiveJobsList(data.jobs);
        
    } catch (error) {
        console.error('Error fetching active jobs:', error);
        showLoadingState();
    }
}

// 更新活躍任務列表
function updateActiveJobsList(jobs) {
    if (!elements.jobsList) return;
    
    if (!jobs || Object.keys(jobs).length === 0) {
        elements.jobsList.innerHTML = `
            <div class="empty-state">
                <i class="bi bi-inbox"></i>
                <p>目前沒有活躍的任務</p>
            </div>`;
        return;
    }
    
    const tempContainer = document.createElement('div');
    
    Object.entries(jobs).forEach(([jobId, job]) => {
        const jobElement = createJobElement(jobId, job);
        tempContainer.appendChild(jobElement);
    });
    
    elements.jobsList.innerHTML = '';
    elements.jobsList.appendChild(tempContainer);
}

// 創建任務元素
function createJobElement(jobId, job) {
    const jobElement = document.createElement('div');
    jobElement.className = 'job-item';
    jobElement.id = `job-${jobId}`;
    
    const statusClass = getStatusBadgeClass(job.status);
    const statusText = getStatusText(job.status);
    const statusIcon = getStatusIcon(job.status);
    
    const stopButton = job.status === 'processing' ? `
        <button class="btn btn-danger btn-sm ms-2" onclick="stopJob('${jobId}')">
            <i class="bi bi-stop-circle"></i> 停止
        </button>
    ` : '';
    
    jobElement.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <div class="d-flex align-items-center">
                <span class="badge ${statusClass} me-2">
                    <i class="bi ${statusIcon} me-1"></i>${statusText}
                </span>
                <span class="text-truncate" style="max-width: 200px;">${job.message || '處理中...'}</span>
            </div>
            <div class="d-flex align-items-center">
                <small class="text-muted me-2">${formatTimestamp(job.updated_at)}</small>
                ${stopButton}
            </div>
        </div>
    `;
    
    return jobElement;
}

// 獲取狀態徽章類別
function getStatusBadgeClass(status) {
    const statusClasses = {
        pending: 'bg-secondary',
        processing: 'bg-primary',
        completed: 'bg-success',
        failed: 'bg-danger'
    };
    return statusClasses[status] || 'bg-secondary';
}

// 獲取狀態文字
function getStatusText(status) {
    const statusTexts = {
        pending: '等待中',
        processing: '處理中',
        completed: '已完成',
        failed: '失敗'
    };
    return statusTexts[status] || status;
}

// 獲取狀態圖標
function getStatusIcon(status) {
    const statusIcons = {
        pending: 'bi-hourglass-split',
        processing: 'bi-arrow-repeat',
        completed: 'bi-check-circle',
        failed: 'bi-x-circle'
    };
    return statusIcons[status] || 'bi-question-circle';
}

// 格式化時間戳
function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleTimeString();
}

// 切換顯示/隱藏活躍任務列表
function toggleActiveJobs() {
    const isVisible = !elements.jobsList.classList.contains('d-none');
    
    if (isVisible) {
        elements.jobsList.classList.add('d-none');
    } else {
        elements.jobsList.classList.remove('d-none');
        elements.jobsList.innerHTML = `
            <div class="loading-state">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-2 mb-0 text-muted">正在載入活躍任務...</p>
            </div>
        `;
        fetchActiveJobs();
    }
}

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

// 停止任務
async function stopJob(jobId) {
    const result = await Swal.fire({
        title: '確定要停止這個任務嗎？',
        text: '停止後將無法恢復，需要重新處理檔案。',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        cancelButtonColor: '#6c757d',
        confirmButtonText: '確定停止',
        cancelButtonText: '取消',
        reverseButtons: true,
        customClass: {
            confirmButton: 'btn btn-danger',
            cancelButton: 'btn btn-secondary'
        }
    });

    if (!result.isConfirmed) {
        return;
    }

    const jobElement = document.getElementById(`job-${jobId}`);
    if (jobElement) {
        jobElement.classList.add('removing');
    }

    try {
        // 先發送停止請求
        const stopResponse = await fetch(`${API_BASE_URL}/job/${jobId}/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!stopResponse.ok) {
            const errorData = await stopResponse.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP error! status: ${stopResponse.status}`);
        }

        const stopData = await stopResponse.json();

        if (stopData.success) {
            // 等待一小段時間確保任務已停止
            await new Promise(resolve => setTimeout(resolve, 500));

            // 再次檢查任務狀態以確認已停止
            const statusResponse = await fetch(`${API_BASE_URL}/job/${jobId}`);
            const statusData = await statusResponse.json();

            if (statusData.success && statusData.job.status === 'failed') {
                Swal.fire({
                    title: '任務已停止',
                    text: '任務已成功停止。',
                    icon: 'success',
                    timer: 2000,
                    showConfirmButton: false
                });

                // 等待動畫完成後再更新列表
                setTimeout(() => {
                    fetchActiveJobs();
                }, 300);
            } else {
                throw new Error('任務未能成功停止');
            }
        } else {
            throw new Error(stopData.error || '停止任務失敗');
        }
    } catch (error) {
        console.error('停止任務失敗:', error);
        Swal.fire({
            title: '停止任務失敗',
            text: error.message || '請稍後再試。',
            icon: 'error',
            confirmButtonColor: '#dc3545'
        });
        
        if (jobElement) {
            jobElement.classList.remove('removing');
        }
    }
}

function startJobUpdates() {
    if (jobUpdateInterval) {
        clearInterval(jobUpdateInterval);
    }
    
    // 立即執行一次更新
    updateActiveJobsList();
    
    // 設置定時更新
    jobUpdateInterval = setInterval(updateActiveJobsList, UPDATE_INTERVAL);
}

function stopJobUpdates() {
    if (jobUpdateInterval) {
        clearInterval(jobUpdateInterval);
        jobUpdateInterval = null;
    }
}

async function updateActiveJobsList() {
    try {
        const response = await fetch('/api/jobs/active');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        if (data.status !== 'success') {
            throw new Error(data.message || '獲取任務列表失敗');
        }
        
        const jobs = data.data.jobs;
        const jobsList = document.getElementById('jobs-list');
        
        if (!jobsList) {
            console.warn('找不到任務列表元素');
            return;
        }
        
        // 檢查是否需要更新
        const currentTime = new Date().getTime();
        if (lastUpdateTime && currentTime - lastUpdateTime < UPDATE_INTERVAL) {
            return; // 避免過於頻繁的更新
        }
        lastUpdateTime = currentTime;
        
        // 更新任務列表
        if (Object.keys(jobs).length === 0) {
            jobsList.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-inbox"></i>
                    <p>目前沒有活躍的任務</p>
                </div>
            `;
        } else {
            jobsList.innerHTML = Object.values(jobs).map(job => `
                <div class="job-item" data-job-id="${job.id}">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <div>
                            <span class="badge ${getStatusBadgeClass(job.status)}">${getStatusText(job.status)}</span>
                            <small class="text-muted ms-2">${formatDate(job.created_at)}</small>
                        </div>
                        ${job.status === 'processing' || job.status === 'pending' ? `
                            <button class="btn btn-danger btn-sm" onclick="stopJob('${job.id}')">
                                <i class="bi bi-stop-circle"></i> 停止
                            </button>
                        ` : ''}
                    </div>
                    ${job.status === 'processing' ? `
                        <div class="progress mb-2">
                            <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                 role="progressbar" 
                                 style="width: ${job.progress}%" 
                                 aria-valuenow="${job.progress}" 
                                 aria-valuemin="0" 
                                 aria-valuemax="100">
                                ${job.progress}%
                            </div>
                        </div>
                    ` : ''}
                    ${job.error ? `
                        <div class="alert alert-danger py-2 mb-0">
                            <i class="bi bi-exclamation-circle"></i> ${job.error}
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('更新任務列表失敗:', error);
        // 不要在這裡顯示錯誤提示，避免頻繁彈出
    }
}

function getStatusBadgeClass(status) {
    switch (status) {
        case 'pending': return 'bg-warning';
        case 'processing': return 'bg-primary';
        case 'completed': return 'bg-success';
        case 'failed': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'pending': return '等待中';
        case 'processing': return '處理中';
        case 'completed': return '已完成';
        case 'failed': return '失敗';
        default: return '未知';
    }
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 在頁面卸載時停止任務更新
window.addEventListener('beforeunload', () => {
    stopJobUpdates();
});