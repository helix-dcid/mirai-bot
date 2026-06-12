# Changelog - Mirai Helix

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