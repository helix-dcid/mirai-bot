"""
utils/web_rate_limiter.py — Per-User Weekly Rate Limiter
─────────────────────────────────────────────────────────
Membatasi pengguna Discord untuk menggunakan fitur web scraping
hanya 1x per minggu (default 7 hari).

Fitur:
  - Persistent ke JSON (atomic write, thread-safe)
  - Per-user tracking berdasarkan user_id Discord
  - Auto-cleanup entry yang expired (>7 hari)
  - Hitung sisa hari sebelum bisa scrap lagi
"""

import json
import os
import time
import threading
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from config import WEB_SEARCH_COOLDOWN_DAYS
from utils.logger import setup_logging

logger = setup_logging()

COOLDOWN_PATH = Path("data/web_scrape_cooldown.json")
COOLDOWN_SECONDS = WEB_SEARCH_COOLDOWN_DAYS * 24 * 60 * 60  # Konversi hari ke detik
_lock = threading.RLock()  # Reentrant lock — aman dipanggil dari dalam metode yang sama


class WebRateLimiter:
    """
    Rate limiter per-user untuk fitur web scraping.

    Contoh:
        limiter = WebRateLimiter()
        if limiter.can_scrape(user_id):
            # Lakukan scraping
            limiter.mark_scraped(user_id)
        else:
            sisa = limiter.get_remaining_days(user_id)
            print(f"Tunggu {sisa} hari lagi")
    """

    def __init__(self):
        self._ensure_dir()
        self._data: dict[str, float] = {}  # {user_id_str: timestamp}
        self._load()

    # ------------------------------------------------------------------
    # Persistence (atomic write, thread-safe)
    # ------------------------------------------------------------------

    def _ensure_dir(self):
        """Pastikan direktori data ada."""
        COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """Muat data dari file JSON.
        
        TIDAK perlu lock manual karena self._clean_expired() sudah pakai RLock.
        """
        with _lock:
            if not COOLDOWN_PATH.exists():
                self._data = {}
                return

            try:
                raw = COOLDOWN_PATH.read_text(encoding="utf-8")
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    self._data = loaded
                else:
                    self._data = {}
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[WebRateLimiter] Gagal load: {e}")
                self._data = {}

            self._clean_expired_locked()

    def _save(self):
        """Simpan data ke JSON secara atomik."""
        with _lock:
            try:
                # Tulis ke file temp dulu
                fd, temp_path = tempfile.mkstemp(
                    suffix=".json",
                    dir=str(COOLDOWN_PATH.parent),
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
                # Ganti file asli secara atomik
                shutil.move(temp_path, str(COOLDOWN_PATH))
            except Exception as e:
                logger.error(f"[WebRateLimiter] Gagal save: {e}")
                # Hapus temp file jika ada
                if "temp_path" in locals():
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass

    def _clean_expired_locked(self):
        """
        Hapus entry yang sudah expired.
        ASUMSI: _lock sudah dipegang oleh pemanggil.
        """
        now = time.time()
        expired = [
            uid for uid, ts in self._data.items()
            if now - ts >= COOLDOWN_SECONDS
        ]
        if expired:
            for uid in expired:
                self._data.pop(uid, None)
            self._save()
            logger.debug(
                f"[WebRateLimiter] Cleaned {len(expired)} expired entries"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_scrape(self, user_id: int) -> bool:
        """
        Cek apakah user boleh melakukan web scraping.

        Args:
            user_id: ID Discord user

        Returns:
            True jika boleh, False jika masih dalam cooldown
        """
        uid = str(user_id)
        last_ts = self._data.get(uid)

        if last_ts is None:
            return True

        elapsed = time.time() - last_ts
        return elapsed >= COOLDOWN_SECONDS

    def mark_scraped(self, user_id: int):
        """
        Catat bahwa user baru saja melakukan scraping.
        Panggil SETELAH scraping berhasil, bukan sebelumnya.

        Args:
            user_id: ID Discord user
        """
        uid = str(user_id)
        self._data[uid] = time.time()
        self._save()
        logger.info(f"[WebRateLimiter] User {user_id} telah melakukan scraping")

    def get_remaining_days(self, user_id: int) -> int:
        """
        Hitung sisa hari sebelum user bisa scraping lagi.

        Args:
            user_id: ID Discord user

        Returns:
            Sisa hari (0 jika sudah bisa)
        """
        uid = str(user_id)
        last_ts = self._data.get(uid)

        if last_ts is None:
            return 0

        elapsed = time.time() - last_ts
        remaining_sec = COOLDOWN_SECONDS - elapsed

        if remaining_sec <= 0:
            return 0

        return max(1, int(remaining_sec // (24 * 60 * 60)) + 1)

    def get_remaining_seconds(self, user_id: int) -> int:
        """
        Hitung sisa detik sebelum user bisa scraping lagi.

        Args:
            user_id: ID Discord user

        Returns:
            Sisa detik (0 jika sudah bisa)
        """
        uid = str(user_id)
        last_ts = self._data.get(uid)

        if last_ts is None:
            return 0

        remaining = COOLDOWN_SECONDS - (time.time() - last_ts)
        return max(0, int(remaining))

    def reset_user(self, user_id: int):
        """
        Reset cooldown user (untuk admin/unblock).

        Args:
            user_id: ID Discord user
        """
        uid = str(user_id)
        self._data.pop(uid, None)
        self._save()
        logger.info(f"[WebRateLimiter] Cooldown di-reset untuk user {user_id}")
