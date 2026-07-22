"""
ai/youtube_transcript.py — YouTube Transcript Extractor
────────────────────────────────────────────────────────
Menggunakan yt-dlp untuk mengekstrak subtitle/closed captions
dari video YouTube tanpa mendownload video.

Mirip pola ai/web_scraper.py (Browserless client):
  - URL detection via regex
  - Extract subtitle via yt-dlp subprocess
  - Parse SRT/VTT ke teks bersih
  - Cache per video ID (TTL 1 jam)
  - SSRF protection (reuse pattern)

Dependency:
  yt-dlp>=2024.12.0  (pip install)
"""

import re
import time
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from urllib.parse import urlparse

from config import (
    YOUTUBE_TRANSCRIPT_CACHE_TTL,
    YOUTUBE_TRANSCRIPT_MAX_CHARS,
    YOUTUBE_TRANSCRIPT_SUB_LANGS,
)
from utils.logger import setup_logging

logger = setup_logging()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# YouTube URL patterns
YOUTUBE_URL_PATTERN = re.compile(
    r"(?:https?://)?"
    r"(?:(?:www\.)?youtube\.com/(?:watch\?v=|embed/|v/|shorts/|playlist\?)"
    r"|(?:www\.)?youtu\.be/)"
    r"([a-zA-Z0-9_-]{11})"
    r"(?:[?&](?:[^&\s]+))*?"
)

# Fallback subtitle languages (prioritas)
FALLBACK_LANGS = ["id", "en", "a-ID", "a-en"]

# yt-dlp output template: gunakan temp dir agar tidak meninggalkan file
_TEMP_DIR = Path(tempfile.gettempdir()) / "mirai_yt_transcript"
_TEMP_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SSRF Protection (reuse pattern from web_scraper.py)
# ---------------------------------------------------------------------------

_PRIVATE_IP_PATTERNS = {
    "localhost", "127.0.0.1", "0.0.0.0", "[::1]",
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.", "192.168.",
}


def _is_safe_url(url: str) -> Tuple[bool, str]:
    """Validasi URL agar aman dari SSRF. Returns (safe: bool, reason: str)."""
    if not url:
        return False, "URL kosong"
    if not url.startswith(("http://", "https://")):
        return False, f"Protokol tidak diizinkan: {url[:20]}..."
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL tidak valid: {e}"
    hostname = parsed.hostname or ""
    for pattern in _PRIVATE_IP_PATTERNS:
        if hostname.startswith(pattern) or hostname == pattern:
            return False, f"Akses ke alamat internal tidak diizinkan: {hostname}"
    ip_match = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", hostname)
    if ip_match:
        first = int(ip_match.group(1))
        second = int(ip_match.group(2))
        if first == 10:
            return False, f"Akses ke jaringan 10.x.x.x tidak diizinkan: {hostname}"
        if first == 172 and 16 <= second <= 31:
            return False, f"Akses ke jaringan 172.16-31.x.x tidak diizinkan: {hostname}"
        if first == 192 and second == 168:
            return False, f"Akses ke jaringan 192.168.x.x tidak diizinkan: {hostname}"
        if first == 127:
            return False, f"Akses ke localhost tidak diizinkan: {hostname}"
    return True, ""


# ---------------------------------------------------------------------------
# YouTube URL utilities
# ---------------------------------------------------------------------------

def extract_youtube_url(text: str) -> Optional[str]:
    """Ekstrak URL YouTube pertama dari teks.
    
    Args:
        text: Teks yang mungkin mengandung URL YouTube
    
    Returns:
        URL YouTube lengkap, atau None jika tidak ditemukan
    """
    match = YOUTUBE_URL_PATTERN.search(text)
    if not match:
        return None
    video_id = match.group(1)
    return f"https://www.youtube.com/watch?v={video_id}"


def extract_video_id(url: str) -> Optional[str]:
    """Ekstrak video ID dari URL YouTube.
    
    Args:
        url: URL YouTube
    
    Returns:
        Video ID (11 karakter), atau None
    """
    match = YOUTUBE_URL_PATTERN.search(url)
    if match:
        return match.group(1)
    return None





# ---------------------------------------------------------------------------
# SRT/VTT Parser
# ---------------------------------------------------------------------------

def _parse_srt(content: str) -> str:
    """Parse SRT format ke teks bersih.
    
    SRT format:
        1
        00:00:01,000 --> 00:00:04,000
        Teks subtitle
    
    Returns: Teks bersih tanpa timestamp dan nomor urut.
    """
    lines = content.splitlines()
    text_parts = []
    
    for line in lines:
        line = line.strip()
        # Skip empty lines
        if not line:
            continue
        # Skip numeric sequence numbers (integer only)
        if line.isdigit():
            continue
        # Skip timestamp lines (contain -->)
        if "-->" in line:
            continue
        # Skip lines that are just timestamps like 00:00:01,000
        if re.match(r"^\d{1,2}:\d{2}:\d{2}", line):
            continue
        # Skip HTML tags like <font>, <c.xyz>
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if cleaned:
            text_parts.append(cleaned)
    
    return " ".join(text_parts)


def _parse_vtt(content: str) -> str:
    """Parse VTT format ke teks bersih.
    
    VTT format mirip SRT tapi dengan header WEBVTT dan
    timestamp format 00:00:01.000 (titik bukan koma).
    """
    lines = content.splitlines()
    text_parts = []
    
    for line in lines:
        line = line.strip()
        # Skip WEBVTT header and empty lines
        if not line or line == "WEBVTT":
            continue
        # Skip numeric sequence numbers
        if line.isdigit():
            continue
        # Skip timestamp lines (contain -->)
        if "-->" in line:
            continue
        # Skip lines that are just timestamps
        if re.match(r"^\d{1,2}:\d{2}:\d{2}", line):
            continue
        # Skip cue settings (Align:position:...)
        if re.match(r"^(Align|Position|Line|Size)", line, re.IGNORECASE):
            continue
        # Strip HTML tags
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if cleaned:
            text_parts.append(cleaned)
    
    return " ".join(text_parts)


def _parse_transcript(content: str, fmt: str) -> str:
    """Parse subtitle content ke teks bersih berdasarkan format."""
    if fmt == "srt":
        return _parse_srt(content)
    elif fmt == "vtt":
        return _parse_vtt(content)
    else:
        # Fallback: buang timestamp lines
        lines = content.splitlines()
        text_parts = []
        for line in lines:
            line = line.strip()
            if not line or "-->" in line or line.isdigit():
                continue
            if re.match(r"^\d{1,2}:\d{2}:\d{2}", line):
                continue
            cleaned = re.sub(r"<[^>]+>", "", line).strip()
            if cleaned:
                text_parts.append(cleaned)
        return " ".join(text_parts)


# ---------------------------------------------------------------------------
# yt-dlp Python API wrapper (no subprocess)
# ---------------------------------------------------------------------------

async def _get_video_data(
    video_id: str,
    output_dir: Path,
    sub_langs: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Ambil info video + subtitle via yt-dlp Python API.
    
    Menggunakan yt_dlp.YoutubeDL langsung tanpa subprocess,
    jadi tidak perlu binary yt-dlp di PATH (cocok untuk Docker minimal).
    
    Args:
        video_id: YouTube video ID
        output_dir: Direktori output untuk file subtitle
        sub_langs: Daftar bahasa subtitle (default: dari config)
    
    Returns:
        Tuple (title, file_path, format) — masing-masing bisa None
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    langs = sub_langs or YOUTUBE_TRANSCRIPT_SUB_LANGS
    outtmpl = str(output_dir / f"{video_id}.%(ext)s")

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": langs,
        "subtitlesformat": "srt",
        "outtmpl": {"default": outtmpl},
        "socket_timeout": 15,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        import yt_dlp

        def _sync_extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info

        info = await asyncio.to_thread(_sync_extract)

        title = info.get("title") or None

        # Cari file subtitle yang dihasilkan
        file_path = None
        sub_fmt = None

        # Cari SRT hasil convert dulu
        for suffix in [f"{video_id}.srt", f"{video_id}.{langs[0]}.srt",
                       f"{video_id}.{langs[0]}.vtt"]:
            fpath = output_dir / suffix
            if fpath.exists() and fpath.stat().st_size > 0:
                file_path = str(fpath)
                sub_fmt = "srt" if suffix.endswith(".srt") else "vtt"
                break

        if not file_path:
            for ext in ["vtt", "ttml", "ass", "srt"]:
                for f in output_dir.glob(f"{video_id}*.{ext}"):
                    if f.stat().st_size > 0:
                        file_path = str(f)
                        sub_fmt = ext
                        break
                if file_path:
                    break

        return title, file_path, sub_fmt

    except ImportError:
        logger.error("[YouTubeTranscript] yt-dlp tidak terinstall. Jalankan: pip install yt-dlp")
        return None, None, None
    except Exception as e:
        logger.warning(f"[YouTubeTranscript] yt-dlp error: {e}")
        return None, None, None


def _cleanup_temp(video_id: str, output_dir: Path):
    """Bersihkan file temporary untuk video_id tertentu."""
    for f in output_dir.glob(f"{video_id}*"):
        try:
            f.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# YouTubeTranscriptClient
# ---------------------------------------------------------------------------

class YouTubeTranscriptClient:
    """Client async untuk mengekstrak transkrip video YouTube via yt-dlp.
    
    Mirip pola BrowserlessClient di ai/web_scraper.py:
      - extract_urls() → ekstrak URL YouTube dari teks
      - get_transcript() → download & parse subtitle
      - Cache per video_id (TTL dari config)
    
    Contoh:
        client = YouTubeTranscriptClient()
        transcript = await client.get_transcript("https://youtube.com/watch?v=xxx")
    """
    
    def __init__(self):
        self.cache_ttl = YOUTUBE_TRANSCRIPT_CACHE_TTL
        self.max_chars = YOUTUBE_TRANSCRIPT_MAX_CHARS
        self.sub_langs = YOUTUBE_TRANSCRIPT_SUB_LANGS
        
        # Cek apakah yt-dlp tersedia
        self._check_available: Optional[bool] = None
        
        # Cache: { video_id: (timestamp, transcript_text, title) }
        self._cache: Dict[str, Tuple[float, str, str]] = {}
        self._cache_lock = asyncio.Lock()
    
    @property
    def enabled(self) -> bool:
        """Cek apakah YouTube Transcript siap digunakan."""
        return True  # yt-dlp sudah terinstal
    
    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    
    async def _get_cached(self, video_id: str) -> Optional[Tuple[str, str]]:
        """Ambil transkrip dari cache jika masih valid.
        
        Returns:
            Tuple (transcript_text, video_title) atau None
        """
        async with self._cache_lock:
            entry = self._cache.get(video_id)
            if entry:
                ts, text, title = entry
                if time.time() - ts < self.cache_ttl:
                    logger.debug(f"[YouTubeTranscript] Cache hit: {video_id}")
                    return text, title
                self._cache.pop(video_id, None)
        return None
    
    async def _set_cached(self, video_id: str, text: str, title: str):
        """Simpan transkrip ke cache."""
        async with self._cache_lock:
            self._cache[video_id] = (time.time(), text, title)
            if len(self._cache) > 50:
                now = time.time()
                expired = [k for k, (ts, _, _) in self._cache.items()
                          if now - ts >= self.cache_ttl]
                for k in expired:
                    self._cache.pop(k, None)
    
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    
    async def get_transcript(
        self,
        url: str,
        max_chars: Optional[int] = None,
    ) -> Optional[Dict]:
        """Ambil transkrip video YouTube.
        
        Args:
            url: URL video YouTube
            max_chars: Maks karakter (default dari config)
        
        Returns:
            Dict dengan keys:
              - video_id: str
              - title: str
              - transcript: str (teks bersih)
              - url: str
            Atau None jika gagal.
        """
        # SSRF check
        safe, reason = _is_safe_url(url)
        if not safe:
            logger.warning(f"[YouTubeTranscript] URL tidak aman: {reason}")
            return None
        
        # Ekstrak video ID
        video_id = extract_video_id(url)
        if not video_id:
            logger.warning(f"[YouTubeTranscript] Tidak dapat ekstrak video ID dari: {url[:60]}")
            return None
        
        max_chars = max_chars or self.max_chars
        
        # Cek cache
        cached = await self._get_cached(video_id)
        if cached is not None:
            text, title = cached
            return {
                "video_id": video_id,
                "title": title,
                "transcript": text,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        
        # Buat temp directory untuk video ini
        output_dir = _TEMP_DIR / video_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Satu panggilan yt-dlp: ambil info + subtitle sekaligus
            title, file_path, sub_fmt = await _get_video_data(video_id, output_dir)
            
            if not title:
                title = f"Video {video_id}"
            
            if file_path and sub_fmt:
                try:
                    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
                    text = _parse_transcript(content, sub_fmt)
                except Exception as e:
                    logger.error(f"[YouTubeTranscript] Gagal parse file {file_path}: {e}")
                    return None
                finally:
                    # Bersihkan file temp
                    _cleanup_temp(video_id, output_dir)
                
                if not text.strip():
                    logger.warning(f"[YouTubeTranscript] Transkrip kosong untuk {video_id}")
                    return None
                
                # Clip ke max_chars
                if len(text) > max_chars:
                    text = text[:max_chars].rsplit(" ", 1)[0] + "…"
                
                # Simpan ke cache
                await self._set_cached(video_id, text, title)
                
                logger.info(
                    f"[YouTubeTranscript] Sukses: {title[:40]} "
                    f"({len(text)} chars)"
                )
                
                return {
                    "video_id": video_id,
                    "title": title,
                    "transcript": text,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            else:
                # Tidak ada subtitle, return info video saja
                logger.info(
                    f"[YouTubeTranscript] Tidak ada subtitle untuk {video_id} "
                    f"({title[:40]}), hanya return info"
                )
                return {
                    "video_id": video_id,
                    "title": title,
                    "transcript": None,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
        
        except Exception as e:
            logger.exception(f"[YouTubeTranscript] Error untuk {video_id}: {e}")
            return None
        finally:
            # Bersihkan temp directory jika kosong
            try:
                if output_dir.exists() and not any(output_dir.iterdir()):
                    output_dir.rmdir()
            except Exception:
                pass
    
    def extract_urls(self, text: str) -> List[str]:
        """Ekstrak semua URL YouTube dari teks.
        
        Args:
            text: Teks yang mungkin mengandung URL YouTube
        
        Returns:
            List URL YouTube lengkap
        """
        matches = YOUTUBE_URL_PATTERN.findall(text)
        return [f"https://www.youtube.com/watch?v={vid}" for vid in matches]


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _test():
        client = YouTubeTranscriptClient()
        test_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
        ]
        for url in test_urls:
            print(f"\n=== Testing: {url} ===")
            result = await client.get_transcript(url)
            if result:
                print(f"Title: {result['title']}")
                has_transcript = result.get('transcript') is not None
                print(f"Has transcript: {has_transcript}")
                if has_transcript:
                    print(f"Transcript length: {len(result['transcript'])} chars")
                    print(f"Preview: {result['transcript'][:200]}...")
            else:
                print("Failed to get transcript")
    
    asyncio.run(_test())
