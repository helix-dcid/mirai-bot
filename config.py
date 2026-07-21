import os
from dotenv import load_dotenv

# Load .env first so all os.getenv() calls below find environment variables
load_dotenv()

# config.py - Konfigurasi default untuk Mirai Bot

# ===== MEMORY CONFIG =====
MAX_HISTORY = 15  # Jumlah maksimal pesan yang disimpan
HISTORY_FILE = "history.json"  # File untuk menyimpan history

# ===== COOLDOWN CONFIG =====
COOLDOWN_SECONDS = 30  # Cooldown antar respons per channel
COOLDOWN_REPLY_DELAY = 3  # Waktu sebelum pesan cooldown dihapus

# ===== API CONFIG =====
GEMINI_MODEL = "gemini-2.5-flash"  # Model Gemini yang digunakan
GEMINI_API_VERSION = "v1beta"  # Versi API Gemini
MAX_RETRIES = 5  # Maksimal retry untuk API calls
REQUEST_TIMEOUT = 45  # Timeout untuk HTTP requests (detik)
GENERATE_DEADLINE = 180  # Deadline untuk generate respons (detik)

# ===== GENERATION CONFIG =====
TEMPERATURE = 0.7  # Kreativitas respons (0.0 - 1.0)
MAX_OUTPUT_TOKENS = 2048  # Maksimal output tokens per respons
TOP_P = 0.95  # Top-p sampling parameter

# ===== FILE PROCESSING CONFIG =====
SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".xlsx", ".pptx", ".txt"}
MAX_ATTACHMENTS = 5  # Maksimal file per pesan
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_TEXT_PER_FILE_CHARS = 8000  # Teks maksimal per file
MAX_TOTAL_CHARS = 20000  # Total teks maksimal dari semua file

# ===== RICH PRESENCE CONFIG =====
RPC_UPDATE_INTERVAL = 1800  # Update presence setiap 30 menit (detik)

# ===== KEY ROTATION CONFIG =====
MAX_KEY_WAIT = 120  # Maksimal tunggu semua key cooldown (detik)
KEY_COOLDOWN_DURATION = 60  # Durasi cooldown per key saat rate limit (detik)

# ===== NEWS SUMMARY CONFIG =====

# Webhook URL untuk monitoring sistem (opsional)
# Channel ID untuk mengirim embed peringatan CPU tinggi (opsional)
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
ALERT_CHANNEL_ID = int(os.getenv('ALERT_CHANNEL_ID', '0') or '0')
NEWS_SOURCE_URL = "https://raw.githubusercontent.com/harukayuka2/news-mirai/main/data/berita.json"
NEWS_JSON_PATH = "data/berita.json"
NEWS_SUMMARY_PATH = "data/summary.json"
NEWS_REFRESH_SECONDS = 3600  # Refresh berita dan summary setiap 1 jam
NEWS_MAX_ITEMS = 30  # Batasi jumlah berita yang dirangkum
NEWS_MAX_CHARS = 12000  # Batasi total karakter berita yang dikirim ke AI

# ===== WEB SCRAPER (BROWSERLESS) CONFIG =====
BROWSERLESS_API_KEY = os.getenv('BROWSERLESS_API_KEY', '')
BROWSERLESS_BASE_URL = os.getenv('BROWSERLESS_BASE_URL', 'https://chrome.browserless.io')
BROWSERLESS_TIMEOUT = 15  # Timeout per request (detik)
BROWSERLESS_MAX_CHARS = 8000  # Maks karakter konten web yang diekstrak
BROWSERLESS_CACHE_TTL = 300  # Cache scrap per URL, 5 menit

# ===== YOUTUBE TRANSCRIPT CONFIG =====
YOUTUBE_TRANSCRIPT_CACHE_TTL = 3600  # Cache transcript per video ID, 1 jam
YOUTUBE_TRANSCRIPT_MAX_CHARS = 10000  # Maks karakter transkrip yang diekstrak
YOUTUBE_TRANSCRIPT_SUB_LANGS = ["id", "en"]  # Prioritas bahasa subtitle

# ===== WEB SEARCH (TAVILY) CONFIG =====
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY', '')
TAVILY_BASE_URL = "https://api.tavily.com"
TAVILY_TIMEOUT = 15                # Timeout per request (detik)
TAVILY_MAX_RESULTS = 5             # Jumlah hasil pencarian maksimal
TAVILY_MAX_CHARS = 8000            # Maks karakter total konten hasil search
TAVILY_CACHE_TTL = 300             # Cache per query, 5 menit
TAVILY_SEARCH_DEPTH = "basic"      # "basic" atau "advanced" (lebih lambat, lebih dalam)

# ===== WEB SEARCH RATE LIMITER CONFIG =====
WEB_SEARCH_COOLDOWN_DAYS = 7  # 1x scrap per user per N hari

# ===== VLM (VISION) CONFIG =====
VLM_MONITOR_CHANNEL_ID = int(os.getenv('VLM_MONITOR_CHANNEL_ID', '1477420471770153263') or '1477420471770153263')
VLM_MAX_IMAGES = 1
VLM_MAX_IMAGE_SIZE = 4 * 1024 * 1024  # 4MB per image

# ===== FUNCTION CALLING CONFIG =====
TOOL_EXECUTION_TIMEOUT = 15  # Timeout per tool execution (detik)
FUNCTION_CALL_MAX_TURNS = 1  # Max function call rounds (1 = single tool, no chaining)
