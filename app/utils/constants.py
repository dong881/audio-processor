from enum import Enum


class JobStatus(str, Enum):
    """工作狀態定義，繼承 str 以便直接用於 JSON 序列化"""
    QUEUED = 'queued'           # 已排隊
    PENDING = 'pending'         # 等待處理
    PROCESSING = 'processing'   # 處理中
    COMPLETED = 'completed'     # 處理完成
    FAILED = 'failed'           # 處理失敗
    CANCELLED = 'cancelled'     # 已取消


# 向後相容：保留原有的 dict 介面
JOB_STATUS = {status.name: status.value for status in JobStatus}

# --- Notion API 常數 ---
MAX_BLOCKS_PER_REQUEST = 90       # Notion API 每次請求最多 100 個區塊，使用 90 作為安全界限
MAX_TOGGLE_CHILDREN = 90          # Toggle 區塊最多包含的子區塊數量

# --- 重試與逾時常數 ---
MAX_RETRIES = 3                   # API 請求最大重試次數
RETRY_BASE_DELAY = 2              # 重試基礎延遲秒數（指數退避）
NOTION_REQUEST_TIMEOUT = 30       # Notion API 請求逾時秒數

# --- Redis 常數 ---
REDIS_CREDENTIAL_EXPIRY_DAYS = 30   # Redis 憑證存儲過期天數
REDIS_CONNECT_TIMEOUT = 5          # Redis 連線逾時秒數
REDIS_SOCKET_TIMEOUT = 5           # Redis Socket 逾時秒數

# --- 音訊處理常數 ---
SAMPLE_DIALOGUE_LIMIT = 20         # 說話人識別時使用的最大段落數
TRANSCRIPT_MAX_LENGTH = 2000       # 逐字稿區塊最大字數
WHISPER_DEFAULT_MODEL = 'medium'   # Whisper 預設模型大小

# --- Gemini 模型常數 ---
DEFAULT_GEMINI_MODELS = [
    'gemini-2.5-pro-exp-03-25',
    'gemini-2.5-flash-preview-04-17',
    'gemini-1.5-pro',
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-2.0-flash-lite',
]
FAST_GEMINI_MODELS = [
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-2.0-flash-lite',
]
SUMMARY_GEMINI_MODELS = [
    'gemini-2.5-flash-preview-04-17',
    'gemini-1.5-pro',
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-2.0-flash-lite',
]

# --- 工作管理常數 ---
MAX_JOB_AGE_HOURS = 24             # 已完成工作最大保留時數
MAX_CANCELLED_JOBS = 1000          # cancelled_jobs 集合最大大小