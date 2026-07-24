# Mirai Helix 🤖✨

![Discord](https://img.shields.io/badge/H.E.L.I.X-Mirai%20Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-FF7139?style=for-the-badge&logo=openaccess&logoColor=white)](LICENSE)
[![homepage](https://img.shields.io/badge/homepage-helix--dcid.pages.dev-FF7139?style=for-the-badge&logo=cloudflare&logoColor=white)](https://helix-dcid.pages.dev)
[![Disboard](https://img.shields.io/badge/Disboard-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://disboard.org/server/1388310480803598458)

> **Status**: Active Development — v4.4.0

Discord bot pintar dengan kepribadian "Mirai" yang bijaksana, kritis, namun tetap keibuan. Dibangun menggunakan `discord.py` dengan integrasi **Multi-Provider AI** (Gemini, Groq, DeepSeek V4 Pro/Flash), **Function Calling** untuk cuaca & web search, **Micro-RAG** memori jangka panjang, dan **Batch Analysis** otomatis.

## About H.E.L.I.X

**H.E.L.I.X** is an Indonesian Discord community focused on collaboration, learning, technology, and mental wellness.

**Mirai Helix** is the official AI assistant developed for the H.E.L.I.X community, designed to provide interactive conversations, utilities, and AI-powered features.

## ✨ Fitur Utama

- **💬 Gaya Bicara Natural**: Bahasa Indonesia semi-informal dengan partikel alami, micro-ekspresi, dan teknik echo untuk respons yang lebih natural dan suportif. 12+ mode adaptasi sesuai mood user (panik, sedih, bingung, marah, bahagia).
- **🧠 Multi-Provider AI**: Gemini 2.5 Flash (utama), Groq Llama 3.1 (fallback & kompaksi), DeepSeek V4 Pro/Flash via NVIDIA NIM (batch analysis).
- **⚡ Gemini Function Calling**: Cuaca, web search, dan YouTube transcript diakses via semantic tool calling — Gemini memutuskan sendiri kapan butuh data eksternal.
- **🌤️ Cuaca BMKG**: Data real-time dengan database offline 91.162 lokasi Indonesia. Download otomatis via `aiosqlite`.
- **🔍 Web Search 3-Tier**: Tavily (primary) → DuckDuckGo (fallback) → Browserless SearXNG (tertiary). Cache per query, rate limiter per-user.
- **📚 Journal Reference**: Pencarian jurnal ilmiah via CrossRef API — otomatis menyertakan sitasi jurnal untuk jawaban kesehatan & keilmuan.
- **👋 Auto-Welcome**: Sambutan member baru otomatis dengan teks plain (tanpa embed), template singkat yang merujuk ke #perkenalan dan #pedoman.
- **🌐 Web Scraper**: Scrap konten web via Browserless `/content` + `/scrape` fallback. SSRF protection, cache per URL.
- **🎬 YouTube Transcript**: Ekstrak subtitle via yt-dlp tanpa download video. Cache per video ID, keyword detection.
- **📂 File Attachment Processing**: Baca teks dari PDF, DOCX, XLSX, PPTX, dan TXT (plugin `file_reader`).
- **🧠 Micro-RAG Memory**: Profiling user jangka panjang via Groq — kepribadian, minat, mood, EXP system.
- **📄 Batch Analysis Otomatis**: DeepSeek V4 menganalisis percakapan harian, dikirim sebagai file TXT/PDF.
- **🔌 Plugin System**: Semua fitur adalah plugin independen di `plugins/`. Masing-masing punya lifecycle hooks, config persistent, dan bisa di-load/unload/reload runtime.
- **⚡ Dual Toggle System**: Module Manager (toggle per modul) + Plugin Manager (load/unload plugin penuh). Circuit breaker otomatis nonaktifkan plugin yang crash >3x dalam 5 menit.
- **⏰ Scheduler Cerdas**: Rich presence rotation, auto-batch, resource monitor (auto-pause modul saat CPU >70%).
- **🧠 Context Compaction**: Riwayat percakapan otomatis diringkas via Groq saat mencapai batas, memori terus berlanjut tanpa kehilangan konteks.

## 🧠 DeepSeek Model Selection

Bot mendukung **dua model DeepSeek V4** yang bisa dipilih langsung dari Discord:

| Model | ID | Cocok Untuk |
|-------|----|-------------|
| **DeepSeek V4 Pro** | `deepseek-ai/deepseek-v4-pro` | Analisis batch mendalam, butuh akurasi tinggi |
| **DeepSeek V4 Flash** | `deepseek-ai/deepseek-v4-flash` | Test cepat, butuh respons lebih ringan |

Gunakan perintah `/deepseek model` untuk melihat dan mengganti model aktif.

## 🛠️ Teknologi

- **Bahasa**: Python 3.11+
- **Core**: `discord.py`, `aiohttp`, `aiosqlite`
- **AI & LLM**:
  - Google Gemini API (Gemini 2.5 Flash)
  - Groq API (Llama 3.1)
  - NVIDIA NIM API (DeepSeek V4 Pro / V4 Flash)
- **File Parsing**: `pdfplumber`, `python-docx`, `openpyxl`, `python-pptx`
- **Web Scraping**: Browserless REST API (opsional)
- **Web Search**: Tavily Search API + DuckDuckGo fallback (opsional)
- **YouTube Transcript**: yt-dlp (subtitle extraction, lokal, gratis)
- **Data Persistence**: `json` dengan **Atomic Write** & **Thread Locking**

## 📋 Prasyarat

- Python 3.11+
- Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))
- API Keys: Google Gemini, Groq, NVIDIA (DeepSeek)

## ⚙️ Instalasi & Setup

### 1. Clone Repository
```bash
git clone https://github.com/helix-dcid/mirai-bot.git
cd mirai-bot
```

### 2. Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Konfigurasi Environment
```bash
cp .env.example .env
```
Lalu isi `.env` dengan token dan API key yang sesuai:
```env
DISCORD_TOKEN=your_discord_bot_token
GUILD_ID=your_discord_guild_id
NVIDIA_API_KEY=your_nvidia_api_key_here
GROQ_API_KEY=your_groq_key
GEMINI_KEYS=your_gemini_key_1,your_gemini_key_2
BROWSERLESS_API_KEY=your_browserless_api_key  # opsional, untuk web search
TAVILY_API_KEY=your_tavily_api_key  # opsional, untuk web search aktif (tavily.com)
```

> Lihat [.env.example](.env.example) untuk daftar lengkap variabel yang tersedia.

### 5. Jalankan Bot
```bash
python main.py
```

## 📖 Slash Commands

### Informasi & Utilitas
| Command | Deskripsi |
|---------|-----------|
| `/ask` | Tanya Mirai (kesehatan/curhat) |
| `/ping` | Cek latency bot |
| `/info` | Info tentang Mirai |
| `/status` | Status bot (history, model, latency) |
| `/clear` | Hapus riwayat percakapan (admin) |
| `/cuaca` | Cek prakiraan cuaca BMKG |
| `/report` | Upload laporan batch terbaru |
| `/readfile` | Baca teks dari file attachment manual |

### Web Search
| Command | Deskripsi |
|---------|-----------|
| `/search` | Cari informasi di web (hasil mentah dengan link) |
| `/search-ai` | Cari di web lalu minta Mirai jelaskan hasilnya |

### Kesehatan
| Command | Deskripsi |
|---------|-----------|
| `/bmi` | Hitung Body Mass Index |
| `/water` | Hitung kebutuhan air harian |

### DeepSeek Batch Processing
| Command | Deskripsi |
|---------|-----------|
| `/deepseek status` | Status modul & model aktif |
| `/deepseek model` | Lihat/ganti model (Pro/Flash) |
| `/deepseek toggle` | Aktifkan/nonaktifkan modul |
| `/deepseek add` | Tambah channel batch |
| `/deepseek remove` | Hapus channel batch |
| `/deepseek run` | Jalankan batch manual |
| `/deepseek test` | Tes prompt ke model |
| `/deepseek autorun` | Atur jadwal auto-run |
| `/deepseek forced_channel` | Set channel paksa hasil |

> ⚠️ `/qwen` grup commands adalah alias backward-compat untuk `/deepseek`.

### Plugin & Module
| Command | Deskripsi |
|---------|-----------|
| `/plugin list` | Daftar semua plugin dengan status |
| `/plugin load <name>` | Load plugin |
| `/plugin unload <name>` | Unload plugin runtime |
| `/plugin reload <name>` | Hot-reload plugin (importlib.reload) |
| `/plugin info <name>` | Detail metadata & konfigurasi plugin |
| `/module status` | Status toggle semua modul |
| `/module toggle` | Aktifkan/nonaktifkan modul (file_reader, greeting, weather, dll) |

## 📄 Struktur Direktori

```
mirai-helix/
├── ai/                       # AI provider clients & integrations
│   ├── gemini.py             # Client Google Gemini + function calling
│   ├── deepseek_client.py   # Client DeepSeek V4 Pro/Flash (NVIDIA NIM)
│   ├── cuaca.py             # BMKG weather (offline SQLite, 91k lokasi)
│   ├── web_scraper.py       # Browserless REST API client
│   ├── web_search.py        # Tavily + DuckDuckGo + Browserless search
│   ├── jurnal.py            # CrossRef academic journal search
│   ├── youtube_transcript.py# yt-dlp subtitle extraction
│   ├── intent_classifier.py # Klasifikasi search vs chat
│   ├── query_reformer.py    # Reformulasi query pencarian
│   ├── tool_definitions.py  # Gemini function calling schemas
│   ├── tool_executor.py     # Eksekusi functionCall Gemini
│   └── prompts/             # System prompt Mirai
├── commands/                 # Slash commands (modular)
│   ├── info_command.py      # /ask, /ping, /info, /clear, /status, /cuaca
│   ├── health_command.py    # /bmi, /water
│   ├── deepseek_command.py  # /deepseek (batch & model)
│   ├── qwen_command.py      # /qwen (backward compat)
│   ├── module_command.py    # /module
│   ├── plugin_command.py    # /plugin (list, load, unload, reload, info)
│   ├── greeting_command.py  # /greeting
│   ├── search_command.py    # /search, /search-ai
│   └── general.py           # /report
├── core/                     # Orchestrator
│   ├── bot.py               # Discord client factory
│   ├── router.py            # Main router (wires everything)
│   ├── command.py           # Slash command loader
│   ├── plugin_manager.py    # Plugin system: discover, load, circuit breaker
│   ├── module_manager.py    # Dynamic module toggle (hot-switch per plugin)
│   └── events/
│       └── message_handler.py # Pipeline pemrosesan pesan
├── services/                 # Service layer
│   ├── ai_service.py        # AI Service (Gemini + memory)
│   └── scheduler_service.py # Background scheduler
├── plugins/                  # Plugin system (auto-discovered)
│   ├── base.py              # Base Plugin class (config, hooks, API)
│   ├── greeting/            # Sambutan member baru
│   ├── search/              # Web Search (Tavily/DDG)
│   ├── deepseek_batch/      # DeepSeek Batch Analysis
│   ├── weather/             # Cuaca BMKG
│   ├── wellness/            # Wellness reminders
│   ├── youtube/             # YouTube Transcript
│   ├── journal/             # Journal Reference (CrossRef)
│   └── file_reader/         # File Attachment Reader
├── models/                   # Data models
│   └── plugin_data.py       # Thread-safe JSON store per plugin
├── tools/                    # Tool modules
│   ├── micro_rag.py         # Profiling user jangka panjang
│   ├── context_compactor.py # Kompaksi riwayat percakapan via Groq
│   ├── auto_greeting.py     # Auto-welcome (plain text, tanpa goodbye)
│   ├── qwen_batch.py        # Batch conversation analysis
│   ├── search_session.py    # Multi-turn search tracking
│   └── file_reading.py      # Attachment text extraction
├── managers/
│   └── cooldown_manager.py  # Per-channel cooldown
├── utils/
│   ├── logger.py            # Centralized logging
│   ├── identity.py          # Resolusi identitas user
│   ├── calculator.py        # Kalkulator kesehatan
│   ├── wellness.py          # Wellness reminders
│   ├── cleanup.py           # Pembersihan data lama
│   └── web_rate_limiter.py  # Rate limiter scraping
├── data/                     # Runtime data
│   ├── wilayah.db           # Database BMKG offline
│   ├── chat_log.json        # Chat log untuk Micro-RAG
│   ├── module_config.json   # Module toggle state
│   └── plugins/             # Per-plugin config & data
├── .env                     # Konfigurasi sensitif (JANGAN di-commit)
├── .env.example             # Template konfigurasi environment
├── requirements.txt         # Dependencies
├── main.py                  # Entry point
├── memory.py                # Conversation history system
├── config.py                # Application constants
├── CHANGELOG.md
└── README.md
```

## 🔄 Alur Kerja Batch

1. **Aktifkan modul**: `/deepseek toggle true`
2. **Setup channel**: `/deepseek add #channel`
3. **Pilih model** (opsional): `/deepseek model` → pilih Pro atau Flash
4. **Atur jadwal** (opsional): `/deepseek autorun 11 59`
5. **Atur channel paksa** (opsional): `/deepseek forced_channel set #channel`
6. **User diskusi** → pesan tersimpan otomatis
7. **Eksekusi**: otomatis sesuai jadwal, atau manual via `/deepseek run`
8. **Laporan**: file TXT dikirim ke channel tujuan

## 📝 Changelog
Lihat [CHANGELOG.md](CHANGELOG.md) untuk detail perubahan versi.

## 📜 Lisensi
MIT License — lihat [LICENSE](LICENSE) untuk detail.

---
*Dibuat dengan ❤️ untuk komunitas H.E.L.I.X.*
*Asisten: Mirai (Perawat Muda & Pendamping Emosional)*
