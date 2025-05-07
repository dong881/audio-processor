// 全局變數
const API_BASE_URL = '';  // 空字串表示相對路徑
let googleAuthInitialized = false;
let activeJobsTimer = null;
let currentJobId = null;
let jobStatusTimer = null;

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
    loginButton: document.getElementById('login-button'),
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
                loadDriveFiles();
                startActiveJobsPolling();
            } else {
                showUnauthenticatedUI();
            }
        })
        .catch(error => {
            console.error('認證檢查失敗:', error);
            showUnauthenticatedUI();
            showError('檢查認證狀態時發生錯誤。請稍後再試。');
        });
}

// 設置事件監聽器
function setupEventListeners() {
    // 登入/登出按鈕
    if (elements.loginButton) {
        elements.loginButton.addEventListener('click', handleLogin);
    }
    
    if (elements.logoutButton) {
        elements.logoutButton.addEventListener('click', handleLogout);
    }
    
    // 刷新文件列表按鈕
    if (elements.refreshFilesBtn) {
        elements.refreshFilesBtn.addEventListener('click', loadDriveFiles);
    }
    
    // 處理檔案按鈕
    if (elements.processBtn) {
        elements.processBtn.addEventListener('click', processSelectedFile);
    }
    
    // 顯示活躍任務按鈕
    if (elements.showActiveJobsBtn) {
        elements.showActiveJobsBtn.addEventListener('click', toggleActiveJobs);
    }
}

// ===== 認證相關函數 =====

// 檢查用戶認證狀態
async function checkAuthStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/status`);
        const data = await response.json();
        return data.authenticated === true;
    } catch (error) {
        console.error('檢查認證狀態失敗:', error);
        return false;
    }
}

// 處理登入
function handleLogin() {
    window.location.href = `${API_BASE_URL}/api/auth/google`;
}

// 處理登出
async function handleLogout() {
    try {
        await fetch(`${API_BASE_URL}/api/auth/logout`);
        window.location.reload();
    } catch (error) {
        console.error('登出失敗:', error);
        showError('登出失敗。請稍後再試。');
    }
}

// ===== UI 顯示相關函數 =====

// 顯示已認證用戶界面
function showAuthenticatedUI() {
    if (elements.authSection) elements.authSection.classList.add('d-none');
    if (elements.processingSection) elements.processingSection.classList.remove('d-none');
    if (elements.loginButton) elements.loginButton.classList.add('d-none');
    if (elements.logoutButton) elements.logoutButton.classList.remove('d-none');
}

// 顯示未認證用戶界面
function showUnauthenticatedUI() {
    if (elements.authSection) elements.authSection.classList.remove('d-none');
    if (elements.processingSection) elements.processingSection.classList.add('d-none');
    if (elements.loginButton) elements.loginButton.classList.remove('d-none');
    if (elements.logoutButton) elements.logoutButton.classList.add('d-none');
}

// 顯示錯誤訊息
function showError(message) {
    const errorAlert = document.createElement('div');
    errorAlert.className = 'alert alert-danger alert-dismissible fade show';
    errorAlert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // 添加到頁面頂部
    document.body.insertBefore(errorAlert, document.body.firstChild);
    
    // 5秒後自動消失
    setTimeout(() => {
        errorAlert.classList.remove('show');
        setTimeout(() => errorAlert.remove(), 300);
    }, 5000);
}

// 顯示成功訊息
function showSuccess(message) {
    const successAlert = document.createElement('div');
    successAlert.className = 'alert alert-success alert-dismissible fade show';
    successAlert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // 添加到頁面頂部
    document.body.insertBefore(successAlert, document.body.firstChild);
    
    // 5秒後自動消失
    setTimeout(() => {
        successAlert.classList.remove('show');
        setTimeout(() => successAlert.remove(), 300);
    }, 5000);
}

// ===== Google Drive 檔案操作 =====

// 載入 Google Drive 檔案
async function loadDriveFiles() {
    try {
        if (elements.fileList) {
            elements.fileList.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">載入中...</span></div> 載入中...';
        }
        
        if (elements.attachmentList) {
            elements.attachmentList.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">載入中...</span></div> 載入中...';
        }
        
        const response = await fetch(`${API_BASE_URL}/drive/files`);
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        // 填充音訊文件列表
        if (elements.fileList) {
            const audioFiles = data.files.filter(file => isAudioFile(file.mimeType));
            if (audioFiles.length === 0) {
                elements.fileList.innerHTML = '<div class="alert alert-info">未找到音訊檔案。請上傳音訊檔案到您的 Google Drive.</div>';
            } else {
                elements.fileList.innerHTML = '';
                audioFiles.forEach(file => {
                    const option = document.createElement('div');
                    option.className = 'form-check';
                    option.innerHTML = `
                        <input class="form-check-input" type="radio" name="audioFile" 
                               id="file-${file.id}" value="${file.id}" data-filename="${file.name}">
                        <label class="form-check-label" for="file-${file.id}">
                            ${file.name} (${formatFileSize(file.size)})
                        </label>
                    `;
                    elements.fileList.appendChild(option);
                });
            }
        }
        
        // 填充附件文件列表
        if (elements.attachmentList) {
            const pdfFiles = data.files.filter(file => file.mimeType === 'application/pdf');
            if (pdfFiles.length === 0) {
                elements.attachmentList.innerHTML = '<div class="alert alert-info">未找到 PDF 檔案。附件是選用的。</div>';
            } else {
                elements.attachmentList.innerHTML = '';
                // 添加"無附件"選項
                const noneOption = document.createElement('div');
                noneOption.className = 'form-check';
                noneOption.innerHTML = `
                    <input class="form-check-input" type="radio" name="attachmentFile" 
                           id="attachment-none" value="" checked>
                    <label class="form-check-label" for="attachment-none">
                        無附件
                    </label>
                `;
                elements.attachmentList.appendChild(noneOption);
                
                // 添加PDF檔案
                pdfFiles.forEach(file => {
                    const option = document.createElement('div');
                    option.className = 'form-check';
                    option.innerHTML = `
                        <input class="form-check-input" type="radio" name="attachmentFile" 
                               id="attachment-${file.id}" value="${file.id}" data-filename="${file.name}">
                        <label class="form-check-label" for="attachment-${file.id}">
                            ${file.name} (${formatFileSize(file.size)})
                        </label>
                    `;
                    elements.attachmentList.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('載入檔案失敗:', error);
        if (elements.fileList) {
            elements.fileList.innerHTML = '<div class="alert alert-danger">載入檔案失敗。請重試。</div>';
        }
        if (elements.attachmentList) {
            elements.attachmentList.innerHTML = '<div class="alert alert-danger">載入檔案失敗。請重試。</div>';
        }
    }
}

// 處理選擇的檔案
async function processSelectedFile() {
    // 獲取選擇的音訊檔案
    const selectedAudioElement = document.querySelector('input[name="audioFile"]:checked');
    if (!selectedAudioElement) {
        showError('請選擇一個音訊檔案進行處理');
        return;
    }
    
    const fileId = selectedAudioElement.value;
    const fileName = selectedAudioElement.dataset.filename;
    
    // 獲取選擇的附件檔案（如果有）
    const selectedAttachmentElement = document.querySelector('input[name="attachmentFile"]:checked');
    const attachmentFileId = selectedAttachmentElement && selectedAttachmentElement.value ? selectedAttachmentElement.value : null;
    const attachmentFileName = selectedAttachmentElement && selectedAttachmentElement.dataset.filename ? selectedAttachmentElement.dataset.filename : null;
    
    // 禁用按鈕，顯示處理進度
    elements.processBtn.disabled = true;
    elements.processBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 處理中...';
    
    try {
        // 提交處理請求
        const response = await fetch(`${API_BASE_URL}/process`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_id: fileId,
                attachment_file_id: attachmentFileId
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            // 顯示處理進度區域
            elements.progressContainer.classList.remove('d-none');
            elements.resultContainer.classList.add('d-none');
            
            // 設置文件名稱顯示
            const fileInfo = `處理檔案: ${fileName}`;
            const attachmentInfo = attachmentFileName ? ` (附件: ${attachmentFileName})` : '';
            elements.processingStatus.textContent = fileInfo + attachmentInfo;
            
            // 啟動狀態檢查
            currentJobId = data.job_id;
            checkJobStatus(data.job_id);
            
            // 顯示成功消息
            showSuccess('檔案處理已開始，請稍候...');
        } else {
            showError(data.message || '處理請求失敗');
            resetProcessButton();
        }
    } catch (error) {
        console.error('處理請求失敗:', error);
        showError('處理請求失敗。請稍後再試。');
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
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.job) {
            const job = data.job;
            
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
        showError('檢查任務狀態失敗。請稍後再試。');
        resetProcessButton();
        clearTimeout(jobStatusTimer);
        currentJobId = null;
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
        elements.resultTitle.textContent = result.title || '未知標題';
    }
    
    if (elements.resultSummary) {
        elements.resultSummary.textContent = result.summary || '未生成摘要';
    }
    
    if (elements.resultTodos) {
        elements.resultTodos.innerHTML = '';
        if (result.todos && result.todos.length > 0) {
            result.todos.forEach(todo => {
                const li = document.createElement('li');
                li.textContent = todo;
                elements.resultTodos.appendChild(li);
            });
        } else {
            elements.resultTodos.innerHTML = '<li>未找到待辦事項</li>';
        }
    }
    
    if (elements.resultLink) {
        if (result.notion_page_url) {
            elements.resultLink.href = result.notion_page_url;
            elements.resultLink.textContent = '在 Notion 中查看';
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
                elements.resultSpeakers.innerHTML = '<h5>識別的說話人:</h5><ul>';
                speakers.forEach(([id, name]) => {
                    elements.resultSpeakers.innerHTML += `<li>${name} (${id})</li>`;
                });
                elements.resultSpeakers.innerHTML += '</ul>';
            } else {
                elements.resultSpeakers.innerHTML = '<p>未識別說話人</p>';
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
    showError(`處理失敗: ${job.error || '未知錯誤'}`);
    
    // 隱藏進度區域
    elements.progressContainer.classList.add('d-none');
}

// ===== 活躍任務管理 =====

// 開始輪詢活躍任務
function startActiveJobsPolling() {
    // 先取得一次活躍任務
    fetchActiveJobs();
    
    // 設定定時器，每 10 秒更新一次
    activeJobsTimer = setInterval(fetchActiveJobs, 10000);
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
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            // 更新活躍任務按鈕顯示
            const activeJobsCount = Object.keys(data.active_jobs || {}).length;
            
            if (elements.showActiveJobsBtn) {
                if (activeJobsCount > 0) {
                    elements.showActiveJobsBtn.textContent = `活躍任務 (${activeJobsCount})`;
                    elements.showActiveJobsBtn.classList.remove('btn-outline-secondary');
                    elements.showActiveJobsBtn.classList.add('btn-outline-primary');
                } else {
                    elements.showActiveJobsBtn.textContent = '活躍任務';
                    elements.showActiveJobsBtn.classList.remove('btn-outline-primary');
                    elements.showActiveJobsBtn.classList.add('btn-outline-secondary');
                }
            }
            
            // 更新任務列表（如果已顯示）
            if (!elements.jobsList.classList.contains('d-none')) {
                updateJobsList(data.active_jobs || {});
            }
        }
    } catch (error) {
        console.error('獲取活躍任務失敗:', error);
    }
}

// 更新任務列表
function updateJobsList(jobs) {
    if (!elements.jobsList) return;
    
    elements.jobsList.innerHTML = '';
    
    const jobIds = Object.keys(jobs);
    
    if (jobIds.length === 0) {
        elements.jobsList.innerHTML = '<div class="alert alert-info">目前沒有活躍的任務</div>';
        return;
    }
    
    // 為每個任務創建卡片
    jobIds.forEach(jobId => {
        const job = jobs[jobId];
        const card = document.createElement('div');
        card.className = 'card mb-3';
        
        // 根據任務狀態設置卡片顏色
        let statusBadge = '';
        if (job.status === 'pending') {
            statusBadge = '<span class="badge bg-warning">等待中</span>';
        } else if (job.status === 'processing') {
            statusBadge = '<span class="badge bg-info">處理中</span>';
        }
        
        // 格式化時間
        const createdTime = new Date(job.created_at).toLocaleString();
        const updatedTime = new Date(job.updated_at).toLocaleString();
        
        card.innerHTML = `
            <div class="card-body">
                <h5 class="card-title">任務 ${statusBadge}</h5>
                <div class="progress mb-3">
                    <div class="progress-bar" role="progressbar" style="width: ${job.progress}%;" 
                         aria-valuenow="${job.progress}" aria-valuemin="0" aria-valuemax="100">
                        ${job.progress}%
                    </div>
                </div>
                <p class="card-text">${job.message || '處理中...'}</p>
                <p class="card-text"><small class="text-muted">創建於: ${createdTime}<br>更新於: ${updatedTime}</small></p>
            </div>
        `;
        
        elements.jobsList.appendChild(card);
    });
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
        elements.jobsList.innerHTML = '<div class="spinner-border" role="status"><span class="visually-hidden">載入中...</span></div>';
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
