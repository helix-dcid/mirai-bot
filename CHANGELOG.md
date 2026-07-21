# Changelog - Mirai Helix

## [4.2.0] - 2026-07-22
### 🔄 Changed
- **YouTube Transcript migrasi ke function calling**: Dari deterministic pre-fetch (regex detect + inject ke prompt) menjadi 2-turn Gemini function calling. User kirim YT link → Gemini detect → `functionCall: get_youtube_transcript` → ToolExecutor fetch via yt-dlp → Turn 2 hasil. Konsisten dengan weather/search pattern. (`ai/tool_definitions.py`, `ai/tool_executor.py`, `ai/gemini.py`)

## [4.1.0] - 2026-07-21
### ✨ Added
- **Context Compaction** — Riwayat percakapan otomatis diringkas via Groq saat mencapai 15 pesan. Sistem kompaksi multi-level: ringkasan baru menggabungkan ringkasan lama + percakapan baru. Ringkasan disimpan ke `data/compacted_context.json` dan disuntikkan ke konteks Gemini. Request lain diblokir selama proses kompaksi. (`tools/context_compactor.py`, `memory.py`, `message_handler.py`)

### 🔧 Changed
- **Module Manager**: Modul `news` dihapus dari daftar modul (9 → 8 module). (`core/module_manager.py`)
- **Slash Commands**: Pilihan `News` dihapus dari `/module toggle`. (`commands/module_command.py`)

### 🧹 Cleanup
- **Hapus sistem news_summary**: File `ai/news_summary.py` dihapus. Tool `get_news` dihapus dari `TOOL_DECLARATIONS` dan `MODULE_TO_TOOL`. Method `_execute_news` dan `_load_news_summary` dihapus dari `ToolExecutor`. Scheduler `schedule_news_summary` dan import `run_summary` dihapus. 6 konstanta `NEWS_*` dihapus dari `config.py`. File data `summary.json` dan `berita.json` dibersihkan.
- **`README.md`**: Diperbarui — fitur news dihapus, context compaction ditambahkan, struktur direktori diperbarui.

## [4.0.0] - 2026-07-21
### 🐛 Fixed
- **`ai/gemini.py` — False positive `_simple_response()`**: Substring match `"berapa" in txt_lower` kena false positive dari kata "beberapa". Diperbaiki pakai `re.search(r'\b...\b')` word boundary agar hanya cocok kata utuh.
- **`memory.py` — Race condition disk write**: `add_message()` panggil `_save_history` dua kali (langsung + via `_compact_if_needed`). Sekarang `_save_history` async dipanggil sekali. `_compact_if_needed` dihapus (dead code — deque maxlen=15).
- **`memory.py` — `threading.Lock` blocking event loop**: Diganti `asyncio.Lock` untuk semua operasi cache. `_history_cache` + `_current_context_id` dilindungi `async with`.
- **`memory.py` — `_current_context_id` race condition**: Ditambahkan `_context_lock` (asyncio.Lock) agar tidak ada tabrakan antar user saat ganti context server/DM.
- **`memory.py` — `reset_on_context_change()` sync**: Diubah jadi `async`. Semua caller (message_handler, info_command, search_command) diupdate dengan `await`.
- **`utils/sentiment.py` — Dead code**: Modul tidak dipakai (usage di-comment-out). Import dan baris komentar dihapus dari `message_handler.py`.
- **`tools/search_session.py` — Memory leak**: `cleanup_expired()` tidak pernah dipanggil. Sekarang otomatis di `get_session()`.
- **`tools/file_reading.py` — Bare `except:`**: Diganti `except Exception:` agar tidak menangkap SystemExit/KeyboardInterrupt.
- **`core/module_manager.py` — Silent `except Exception: pass`**: Dua lokasi diganti `logger.debug()` agar error tidak ditelan.
- **`utils/cleanup.py` — Path lama qwen**: `data/qwen_results` → `data/deepseek_results`, `data/qwen_user` → `data/deepseek_user`, pattern `qwen_report_*` → `deepseek_report_*`.
- **`services/scheduler_service.py`**: `%%` typo di log message diperbaiki jadi `%`.

### ⚡ Improved
- **`.gitignore`**: Dirombak total — Python cache, data runtime, OS junk, IDE folder, backup git. 3 file config runtime dihapus dari tracking (`data/deepseek_config.json`, `greeting_config.json`, `module_config.json`).
- **`tools/greeting.py`**: 3 hardcoded Discord channel ID diganti `None` — fallback ke lookup by name.
- **`ai/deepseek_client.py`**: `ask_qwen = ask_deepseek` alias dihapus. Import `ask_qwen` di `tools/qwen_batch.py` diperbarui.
- **`LICENSE`**: Copyright holder diisi `H.E.L.I.X`.
- **Git history**: Semua commit direwrite — author `aditiya-saputra`, remote `github.com/helix-dcid/mirai-bot`, branch `main`.

## [3.7.0] - 2026-06-19
### ✨ Added
- **Gemini Function Calling** (`ai/gemini.py`): Migrasi dari keyword-trigger ke **native function calling (tool calling)**. Gemini sekarang memutuskan sendiri kapan butuh data cuaca, pencarian web, atau berita — tanpa daftar kata kunci.
  - **2-turn flow**: Turn 1 kirim pesan + tools → Gemini return `functionCall` → eksekusi tool → Turn 2 kirim hasil → Gemini generate jawaban final.
  - **3 semantic tools** terdaftar: `get_weather` (BMKG), `search_web` (Tavily/DDG), `get_news` (RSS summary).
  - **Deterministic URL detection**: URL (webpage + YouTube) tetap dideteksi via regex tanpa LLM round-trip — hemat 1 API call.
  - Jika tidak butuh tool → single API call (same latency as before).
- **Tool Definitions** (`ai/tool_definitions.py`): Deklarasi function calling tools untuk Gemini. Dynamic registration berdasarkan `ModuleManager` — hanya tools yang module-nya aktif yang dikirim ke Gemini.
- **Tool Executor** (`ai/tool_executor.py`): Mapping `functionCall` → async Python implementation. Timeout 15 detik per tool, error handling graceful (error dikirim balik ke Gemini sebagai `functionResponse`).
- **Browserless /scrape fallback** (`ai/web_scraper.py`): Jika `/content` mengembalikan teks <100 chars, fallback ke `/scrape` endpoint dengan CSS selectors untuk structured article extraction.
- **Browserless /search fallback** (`ai/web_search.py`): Tertiary fallback chain: Tavily → DuckDuckGo → Browserless `/search` (SearXNG). `WebSearchClient.enabled` sekarang juga mengecek Browserless availability.

### ⚡ Improved
- **`ai/gemini.py` — Hapus keyword triggers**: `_get_weather_context()` dan `_get_search_context()` dihapus. Weather dan search sekarang di-handle oleh Gemini function calling — lebih akurat, tidak perlu maintain keyword list.
- **`ai/gemini.py` — News on-demand**: `NEWS_SUMMARY` tidak lagi di-inject ke setiap prompt (hemat ~500-1000 token/pesan). News sekarang diakses via `get_news` tool hanya saat user memang tanya berita.
- **`ai/web_scraper.py` — Enhanced /content payload**: Ditambahkan `rejectResourceTypes` (blokir image/font/stylesheet/media), `rejectRequestPattern` (blokir tracker), `bestAttempt`, dan `gotoOptions` — mengurangi bandwidth dan mempercepat response.
- **`ai/gemini.py` — Refactor `_make_api_request()`**: Return type berubah dari `(bool, str)` ke `(bool, dict)` untuk mendeteksi `functionCall` vs text response.
- **`ai/gemini.py` — `_build_payload()` disederhanakan**: Tidak ada lagi `asyncio.gather()` 4 context getter di setiap pesan. Payload sekarang hanya berisi system_prompt + time + url_context + user_context + tools[].

### 🔧 Changed
- **`ai/gemini.py`**: Import `intent_classifier`, `query_reformer`, `search_session_manager` dihapus (tidak lagi digunakan oleh GeminiClient). `IntentClassifier` tetap ada untuk `/search` command.
- **`ai/gemini.py`**: `self.news_summary` dihapus dari `__init__`. News summary dibaca on-demand oleh `ToolExecutor._load_news_summary()`.
- **`config.py`**: Ditambahkan `TOOL_EXECUTION_TIMEOUT` (15s) dan `FUNCTION_CALL_MAX_TURNS` (1).
- **`ai/web_search.py`**: Fallback chain diperpanjang: Tavily → DuckDuckGo → Browserless `/search`.

### 🧹 Cleanup
- Hapus `_load_news_summary()` dan `NEWS_SUMMARY` module-level variable dari `ai/gemini.py`.
- Hapus `NEWS_SUMMARY_PATH` import dari `ai/gemini.py` (dipindah ke `ai/tool_executor.py`).

## [3.6.0] - 2026-06-13
### ✨ Added
- **Intent Classifier** (`ai/intent_classifier.py`): Klasifikasi niat user (search vs chat) menggunakan keyword matching yang diperluas + negative triggers.
  - 40+ search triggers (termasuk "rekomendasi", "review", "tips", "harga", "alternatif", dll).
  - Negative triggers untuk mengurangi false positive ("cari perhatian", "cari makan", dll).
  - Follow-up detection ("lebih detail", "yang tadi", "coba cari lagi", dll).
- **Query Reformer** (`ai/query_reformer.py`): Mengubah pesan percakapan menjadi query pencarian optimal.
  - Strip conversational fillers ("aku", "nih", "dong", "tolong", dll).
  - Strip mention & greeting patterns.
  - Context-aware: follow-up question menggunakan konteks dari history percakapan.
- **Search Session Tracker** (`core/search_session.py`): Melacak sesi pencarian per user (TTL 10 menit) untuk mendukung multi-turn search conversations.
- **Adaptive Search Depth**: Query kompleks (>8 kata atau mengandung `?`) otomatis menggunakan depth "advanced".

### 🐛 Fixed
- **`/search-ai` tidak memanggil web search**: Command sekarang secara eksplisit memanggil `web_search.search()` sebelum mengirim ke Gemini, bukan bergantung pada trigger keyword detection di GeminiClient.
- **Mutasi `self.max_results` secara permanen**: Sekarang menggunakan variabel lokal `effective_max` sehingga state instance tidak berubah.
- **Property `enabled` selalu True**: Sekarang mengecek ketersediaan Tavily key ATAU library `duckduckgo-search` secara realistis.
- **Naming modul membingungkan**: Modul `"web_search"` (Browserless scraping) di-rename ke `"web_scraper"`. Modul `"search"` tetap (Tavily/DDG). Auto-migrasi key di config JSON.
- **Modul search/scraper tidak muncul di `/module toggle`**: Ditambahkan Web Scraper, Web Search, DeepSeek, YouTube Transcript ke daftar choices.
- **Footer embed selalu "Powered by Tavily"**: Sekarang menampilkan engine yang sebenarnya dipakai (tavily/duckduckgo).
- **Error feedback kurang informatif**: Pesan error sekarang menjelaskan kemungkinan penyebab kegagalan.

### ⚡ Improved
- **Persistent aiohttp session**: `WebSearchClient` sekarang me-reuse satu `aiohttp.ClientSession` untuk semua request Tavily, mengurangi overhead TCP/TLS. Method `close()` ditambahkan untuk cleanup saat shutdown.
- **Retry dengan exponential backoff**: Tavily retry hingga 2x untuk transient errors (500, 502, 503, 504, timeout) sebelum fallback ke DuckDuckGo. Tidak retry untuk 401 (invalid key) atau 429 (rate limited).
- **Paralel context getter**: Empat context getter (weather, webpage, YouTube, search) di `_build_payload()` sekarang berjalan paralel via `asyncio.gather()`, mengurangi latency signifikan.
- **Query validation**: Query divalidasi — minimal 2 karakter, maksimal 500 karakter. Query kosong langsung return None.
- **Sitasi terstruktur**: `format_for_llm()` sekarang menginstruksikan AI untuk menyertakan nomor sumber [1][2] dan section "Sumber:" di akhir jawaban.
- **Follow-up suggestions**: AI diinstruksikan menawarkan 2-3 pertanyaan lanjutan setelah jawaban berbasis search.
- **`/search` dan `/search-ai` menggunakan Query Reformer**: Query percakapan user otomatis direformulasi sebelum dikirim ke search engine.
- **Search Session tracking**: Hasil search disimpan per user untuk mendukung context-aware follow-up questions.

### 🔧 Changed
- **`core/module_manager.py`**: Modul `"web_search"` → `"web_scraper"`. Auto-migrasi config lama.
- **`core/events/message_handler.py`**: Update referensi `"web_search"` → `"web_scraper"`.
- **`commands/module_command.py`**: Ditambahkan 4 modul baru ke toggle choices (DeepSeek, Web Scraper, YouTube Transcript, Web Search).

## [3.5.0] - 2026-06-13
### ✨ Added
- **Web Search via Tavily + DuckDuckGo**: Pencarian web aktif untuk pertanyaan user tentang informasi terkini.
  - `ai/web_search.py` — `WebSearchClient` async: Tavily Search API (primary) + DuckDuckGo via `duckduckgo-search` (fallback).
  - Tavily: REST POST ke `api.tavily.com/search`, hasil AI-optimized, `include_answer` untuk ringkasan singkat.
  - DuckDuckGo fallback: otomatis aktif jika Tavily tidak tersedia/gagal, tanpa API key.
  - Cache per query (TTL 5 menit, in-memory, thread-safe via `asyncio.Lock`).
  - Result clipping ke 8000 karakter total untuk cegah token explosion.
  - Auto-detect pertanyaan faktual via keyword detection ("cari", "search", "siapa", "apa itu", "kapan", dll).
  - Module `search` (default aktif) via Module Manager — toggle terpisah dari `web_search` (Browserless scraping).
  - Integrasi otomatis ke konteks Gemini (`_get_search_context()` di `ai/gemini.py`).
- **Slash Commands**: `/search` (hasil mentah dengan embed) dan `/search-ai` (hasil search dijelaskan oleh Mirai).
  - `commands/search_command.py` — dua command baru terdaftar via `core/command.py`.
- **`config.py`** — Konfigurasi baru: `TAVILY_API_KEY`, `TAVILY_BASE_URL`, `TAVILY_TIMEOUT`, `TAVILY_MAX_RESULTS`, `TAVILY_MAX_CHARS`, `TAVILY_CACHE_TTL`, `TAVILY_SEARCH_DEPTH`.
- **`.env.example`** — Section baru `TAVILY_API_KEY` dengan dokumentasi.
- **`requirements.txt`** — Dependency baru: `duckduckgo-search>=7.0.0`.

## [3.4.0] - 2026-06-12
### ✨ Added
- **YouTube Transcript via yt-dlp**: Fitur ekstrak subtitle/closed captions dari video YouTube.
  - `ai/youtube_transcript.py` — Client async yt-dlp untuk download subtitle tanpa download video.
  - Satu panggilan yt-dlp (`--print title` + `--write-auto-subs`) untuk ambil judul & subtitle sekaligus.
  - Parse SRT/VTT ke teks bersih (stdlib, tanpa dependency baru).
  - Cache per video ID (TTL 1 jam, in-memory).
  - SSRF protection (reuse dari `web_scraper.py`).
  - Keyword detection: hanya inject transkrip jika user bertanya tentang video (cegah token waste).
  - Module `youtube_transcript` (default aktif) via Module Manager.
  - Integrasi otomatis ke konteks Gemini (mirip pola cuaca & web scraper).
- **`config.py`** — Konfigurasi baru: `YOUTUBE_TRANSCRIPT_CACHE_TTL`, `YOUTUBE_TRANSCRIPT_MAX_CHARS`, `YOUTUBE_TRANSCRIPT_SUB_LANGS`.
- **`requirements.txt`** — Dependency baru: `yt-dlp>=2024.12.0`.

### 🧹 Cleanup
- **`ai/youtube_transcript.py`**: Hapus dead code (`_get_video_title`, `import json`, `import shutil`, `import os`, `parse_qs`).

### 🐛 Fixed
- **`ai/youtube_transcript.py` — Timeout & fallback**: Tambah `--socket-timeout 15` ke argumen yt-dlp untuk cegah hanging. Fallback subtitle sekarang berjalan meskipun panggilan pertama gagal (retcode != 0). Tambah stderr logging untuk debugging.
- **`core/events/message_handler.py` — Cleanup**: Hapus import `module_manager` redundant di step 4.5 & 6.5 (sudah di-import di level module).

## [3.3.0] - 2026-06-12
### 🐛 Fixed
- **`main.py` & `config.py` — Timing `load_dotenv()`**: env vars (`NVIDIA_API_KEY`, `BROWSERLESS_API_KEY`) dibaca sebelum `.env` diload karena `load_dotenv()` dipanggil setelah import project modules. Sekarang dipanggil sebelum import apapun.
- **`core/router.py` — Guild-specific sync dinonaktifkan**: `GUILD_ID` tidak lagi digunakan untuk `copy_global_to` + `sync(guild=guild)` yang menyebabkan double slash command. Kini hanya global sync.
- **`ai/web_scraper.py` — Browserless HTTP 400**: Payload `rejectResourceTypes` dan `waitFor` tidak dikenali oleh skema endpoint `/content`. Disederhanakan menjadi hanya `{"url": url}`.

## [3.2.0] - 2026-06-11
### ✨ Added
- **Web Search via Browserless**: Fitur auto-search website jika user mengirim link dengan mention.
  - `ai/web_scraper.py` — Client Browserless REST API + HTML cleaner (stdlib) + cache per URL (5 menit).
  - `utils/web_rate_limiter.py` — Rate limiter per-user (1x/minggu) dengan persistent JSON (atomic write).
  - Deteksi URL otomatis + inject konten web ke konteks Gemini (mirip pola cuaca).
  - SSRF protection (blokir localhost/private IP).
  - Module `web_search` (default aktif) via Module Manager.
  - Env baru: `BROWSERLESS_API_KEY`, `BROWSERLESS_BASE_URL`.

### 🐛 Fixed
- **`ai/cuaca.py — search_location_code()`**: Perbaikan besar pencarian kota.
  - `_CITY_FALLBACK` diperluas dari 16 → 50+ kota besar + alias (Solo→Surakarta, Jogja→Yogyakarta, Lampung→Bandar Lampung).
  - Pencocokan fallback diperbaiki: dari substring `city in q_upper` → exact/word-boundary (cegah false match).
  - `_search_db` tidak lagi mengembalikan kode non-adm4 (1 titik) ke BMKG API — dipastikan selalu resolve ke kode desa (3 titik).
  - Province fallback: jika kota tidak memiliki child desa, cari desa lain di provinsi yang sama.

### 🧹 Cleanup
- **Hapus 5 file dead code**: `core/llm_handler.py`, `core/deepseek_batch.py`, `ai/qwen_client.py`, `utils/rag_utils.py`, `utils/helper.py`.
  - Tidak ada import yang merujuk ke file-file ini — aman dihapus.
  - `deepseek_batch.py` memiliki syntax error (koma hilang) — tidak pernah berfungsi.

## [3.1.0] - 2026-05-02
### ✨ Added
- **`.env.example`**: File template konfigurasi environment dengan dokumentasi lengkap untuk semua variabel yang dibutuhkan.

### ⚡ Improved
- **`ai/cuaca.py`**: Auto-download database wilayah dari GitHub (cahyadsn/wilayah), parse SQL dump, dan simpan ke SQLite via `aiosqlite` (async, non-blocking).
  - Download otomatis `wilayah.sql` (2.9 MB) saat pertama kali dibutuhkan.
  - Import 91.162 baris data wilayah ke `data/wilayah.db`.
  - File SQL otomatis dihapus setelah import berhasil (hemat disk).
  - Pencarian lokasi menggunakan `aiosqlite` dengan prioritas: Kota → Kabupaten → Kecamatan → Desa.
  - Lazy initialization: DB hanya di-download saat pertama kali cuaca diminta.
- **`README.md`**: Ditambahkan informasi tentang `.env.example` dan database wilayah otomatis.
- **`ai/cuaca.py -- BMKGClient.search_location_code()`**: Strategi pencarian ditingkatkan — "Bandung" sekarang mengarah ke **Kota Bandung** (32.73), bukan desa Bandung di Tulungagung.

### 🧹 Cleanup
- File SQL sementara (`wilayah.sql`) otomatis dihapus setelah di-import ke DB.

## [3.0.0] - 2026-05-01
### ✨ Added
- **Model DeepSeek V4 Flash**: Dukungan model `deepseek-ai/deepseek-v4-flash` sebagai alternatif lebih ringan & cepat dari `deepseek-v4-pro`.
- **Command `/deepseek model`**: Admin dapat mengganti model DeepSeek aktif (Pro / Flash) langsung dari Discord tanpa restart bot. Pilihan tersimpan di `data/deepseek_config.json`.
- **Refactor Slash Commands**: Seluruh command dipisah dari `core/command.py` (monolitik ~1000 baris) menjadi file-file terpisah di `commands/`:
  - `info_command.py` → `/ask`, `/ping`, `/info`, `/clear`, `/status`, `/cuaca`
  - `health_command.py` → `/bmi`, `/water`
  - `deepseek_command.py` → `/deepseek` (add, remove, status, toggle, run, autorun, forced_channel, test, model)
  - `qwen_command.py` → `/qwen` (add, remove, status, toggle, run, autorun, forced_channel, test, result)
  - `module_command.py` → `/module` (status, toggle)
  - `greeting_command.py` → `/greeting` (status, toggle, setchannel)
  - `bedtime_command.py` → `/bedtime` (on, off, status)
  - `online_counter_command.py` → `/online_counter` (on, off, status)
  - `general.py` → `/report` (sudah ada sebelumnya)
- **`core/command.py` sebagai loader**: File utama hanya menjadi entry point yang mengimpor dan mendaftarkan semua command dari folder `commands/`.

### 🔄 Changed
- **`core/command.py`**: Dari ~1000 baris menjadi ~80 baris (loader murni).
- **`ai/deepseek_client.py`**: Model tidak lagi hardcode. Menggunakan `get_active_model()` yang membaca dari config. Fungsi baru `set_active_model()`, `get_model_display_name()`.

### 🧹 Cleanup
- Hapus direktori duplikat `ref-deepseek-v4-pro/`.
- Hapus semua `__pycache__` dan file `.pyc`.
- Hapus file migrasi (`CLONING_*_TO_DEEPSEEK.md`).
- Hapus file hasil batch lama (`data/qwen_results/`, `data/deepseek_results/`).
- Hapus archive `mirai-fix.tar.gz` dan `mirai_deepseek_migration_report.pdf`.

## [2.5.0] - 2026-04-21
### ✨ Added
- **Channel Paksa (Forced Delivery Channel)**: Admin dapat menetapkan satu channel khusus untuk semua laporan Qwen dengan command `/setforcedchannel`.
- **Scheduler Dinamis**: Bot membaca konfigurasi jadwal secara real‑time; perubahan jam atau channel berlaku langsung setelah perintah `/qwen_set_time` atau `/setforcedchannel`.

### 🐛 Fixed
- Menangani `AttributeError` pada command handler ketika channel tidak valid.
- Validasi tambahan untuk ID channel yang tidak ada atau bot tidak memiliki permission.

### 🔄 Changed
- Prioritas pengiriman laporan kini: **Paksa > Channel yang dipilih user > Channel default**
- Menghilangkan emoji di awal respons AI (Gemini & Groq) untuk tampilan lebih kaku dan profesional.

## [2.4.0] - 2026-04-20
### ✨ Added
- **Voice Online Counter**: Fitur penghitung user aktif di channel voice yang mengupdate nama channel setiap 20 menit via `/online_counter_on`.
- **Robust Message Cleanup**: Mekanisme auto‑hapus pesan balasan (cooldown/reply) dengan penanganan error yang aman terhadap `Forbidden` dan `NotFound`.
- **Smart Channel Fallback**: Logika prioritas pengiriman laporan Qwen: (1) Channel khusus user, (2) Channel default global.
- **Config Auto-Repair**: Modul manager otomatis menambahkan modul baru ke file config JSON dengan default `True` saat update versi.

### 🐛 Fixed
- **Graceful Config Failure**: Sistem modul sekarang tetap berjalan (semua aktif) jika file config JSON rusak atau hilang, mencegah bot crash saat startup.
- **Channel Validation**: Memastikan channel fallback yang dipilih masih dalam daftar `enabled_channels` sebelum digunakan.

## [2.3.0] - 2026-04-19
### ✨ Added
- **Custom Auto-Run Scheduler**: Fitur untuk mengatur jam eksekusi batch analisis secara custom via `/qwen_set_time` (format 24 jam).
- **Dedicated Result Channel**: Fitur untuk menentukan channel khusus penerimaan laporan via `/qwen_set_channel` agar hasil tidak menyebar di chat.
- **Dual Format Export**: Laporan batch sekarang digenerate dalam format **PDF** (rapi, siap cetak) dan **TXT** (ringkas, mudah dibaca) sekaligus.
- **Manual Batch Trigger**: Slash command `/qwen_run_now` untuk menjalankan analisis batch secara instan tanpa menunggu jadwal.
- **Thread-Safe RAG**: Implementasi `threading.Lock` pada `utils/rag_utils.py` untuk mencegah race condition saat banyak user berinteraksi.
- **Atomic File Writes**: Mekanisme penulisan file JSON yang aman (write-to-temp-then-move) untuk mencegah korupsi data jika bot crash.
- **TTL Auto-Cleanup**: Sistem pembersihan otomatis profil user yang tidak aktif > 3 hari untuk menghemat storage.

### 🔄 Changed
- **Qwen Batch Logic**: Migrasi dari pengiriman teks panjang di chat menjadi pengiriman file attachment (PDF/TXT) dengan embed ringkasan.
- **Scheduler Robustness**: Perbaikan logika scheduler agar tidak melewatkan waktu eksekusi (menggunakan `timedelta` dan pengecekan tanggal).
- **RAG Performance**: Optimasi fungsi `update_profile` dan `clean_old_profiles` dengan penguncian data yang lebih efisien.
- **Error Handling**: Penambahan validasi channel ID dan penanganan error yang lebih detail pada command Qwen.

### 🐛 Fixed
- **Race Condition**: Memperbaiki potensi data hilang saat dua pesan user diproses bersamaan.
- **Scheduler Miss**: Memperbaiki bug di mana auto-run bisa terlewat jika bot sedang sibuk saat jam target tiba.
- **File Corruption**: Mencegah file `user_profiles.json` rusak akibat penulisan yang terputus mendadak.
- **Channel Validation**: Menambahkan validasi agar command tidak crash jika channel tujuan tidak ditemukan.

## [2.2.0] - 2026-04-18
### ✨ Added
- **Qwen Batch Processor**: Integrasi NVIDIA Qwen API untuk analisis refleksi harian user yang mendalam.
- **PDF Report Generation**: Otomatisasi pembuatan laporan PDF refleksi harian menggunakan library `fpdf2`.
- **Multi-File Attachment Support**: Ekstraksi teks dari PDF, DOCX, XLSX, PPTX, dan TXT.
- **DeepSeek Batch Processor**: Alternatif analisis percakapan menggunakan DeepSeek API.
- **Micro-RAG Integration**: Sistem profiling user jangka panjang di `data/user_profiles.json`.
- **Module Manager Enhancement**: Dukungan modul `qwen` dan `deepseek`.
- **Persistent Chat Storage**: Penyimpanan riwayat percakapan per user.

### 🔄 Changed
- **API Provider Diversifikasi**: Multi-provider (Gemini, Groq, NVIDIA Qwen, DeepSeek) dengan fallback otomatis.
- **Linguistic Style Update**: Gaya bicara semi-informal, partikel natural, teknik *echo*.

## [2.1.0] - 2026-03-15
### Added
- Integrasi awal BMKG API untuk data cuaca.
- Dasar struktur `core/file_reading.py`.

### Changed
- Migrasi dari command prefix ke Slash Commands penuh.

---
*Catatan: Format Changelog mengikuti standar [Keep a Changelog](https://keepachangelog.com/).*