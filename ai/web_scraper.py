"""
ai/web_scraper.py — Browserless REST API Client
────────────────────────────────────────────────
Menggunakan Browserless /content endpoint untuk mengambil konten website.

REST API (tanpa Playwright):
  POST https://chrome.browserless.io/content?token=API_KEY
  Body: { "url": "...", "waitFor": 2000, "rejectResourceTypes": [...] }
  Response: HTML halaman (text/html)

Fitur:
  - POST /content → dapat HTML mentah
  - Parse HTML dengan html.parser (stdlib, tanpa dependency baru)
  - Filter readability: buang <script>, <style>, <nav>, <footer>, <header>
  - Ambil <article>, <main>, atau <body>
  - Clip ke max_chars
  - SSRF protection (blokir localhost / private IP)
  - Cache per URL (TTL 5 menit)
"""

import os
import re
import time
import asyncio
import aiohttp
from html.parser import HTMLParser
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urlparse
from config import (
    BROWSERLESS_API_KEY,
    BROWSERLESS_BASE_URL,
    BROWSERLESS_TIMEOUT,
    BROWSERLESS_MAX_CHARS,
    BROWSERLESS_CACHE_TTL,
)
from utils.logger import setup_logging

logger = setup_logging()

# ---------------------------------------------------------------------------
# SSRF Protection — blokir akses ke internal network
# ---------------------------------------------------------------------------

_PRIVATE_IP_PATTERNS: Set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "[::1]",
    "10.",       # 10.0.0.0/8
    "172.16.",   # 172.16.0.0/12
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",  # 192.168.0.0/16
}


def _is_safe_url(url: str) -> Tuple[bool, str]:
    """
    Validasi URL agar aman dari SSRF.
    Returns (safe: bool, reason: str)
    """
    if not url:
        return False, "URL kosong"

    # Hanya izinkan http / https
    if not url.startswith(("http://", "https://")):
        return False, f"Protokol tidak diizinkan: {url[:20]}..."

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL tidak valid: {e}"

    hostname = parsed.hostname or ""

    # Blokir localhost / IP pribadi
    for pattern in _PRIVATE_IP_PATTERNS:
        if hostname.startswith(pattern) or hostname == pattern:
            return False, f"Akses ke alamat internal tidak diizinkan: {hostname}"

    # Blokir IP numeric yang termasuk range pribadi (cek tambahan)
    # Ini menangkap 10.x.x.x, 172.16-31.x.x, 192.168.x.x
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
# HTML Cleaner — ekstrak teks bacaan dari HTML
# ---------------------------------------------------------------------------

class _HTMLReadabilityParser(HTMLParser):
    """
    Parse HTML dan ekstrak teks bacaan utama.
    - Skip <script>, <style>, <nav>, <footer>, <header>, <aside>, dll
    - Sisipkan newline setelah block-level tags (<p>, <div>, <h1>-<h6>, <li>, <br>)
    - Buang semua tag, ambil text saja
    """

    _SKIP_TAGS: Set[str] = {
        "script", "style", "nav", "footer", "header", "aside",
        "noscript", "iframe", "svg", "form", "select", "option",
    }

    # Tag setelahnya kita sisipkan newline (pemisah paragraf)
    _BLOCK_TAGS: Set[str] = {
        "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "tr", "blockquote", "section", "br", "hr",
    }

    def __init__(self):
        super().__init__()
        self._skip_depth: int = 0       # sedalam apa kita di tag yang di-skip
        self._current_text: str = ""

    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        if tag_lower in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        # Sisipkan newline setelah block-level tags (kecuali <br> yang self-closing)
        if tag_lower in self._BLOCK_TAGS and tag_lower != "br":
            self._current_text += "\n"

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        # Sisipkan newline setelah block-level tags ditutup
        if tag_lower in self._BLOCK_TAGS:
            self._current_text += "\n"

    def handle_data(self, data: str):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._current_text += text + " "

    def handle_entityref(self, name):
        # Sederhanakan entity HTML
        char_map = {
            "amp": "&", "lt": "<", "gt": ">", "quot": '"',
            "apos": "'", "nbsp": " ",
        }
        self._current_text += char_map.get(name, f"&{name};")

    def get_clean_text(self) -> str:
        """Kembalikan teks bersih."""
        return self._current_text.strip()


def _clean_html(html: str, max_chars: int) -> str:
    """
    Bersihkan HTML mentah menjadi teks bacaan.
    - Parse HTML
    - Ambil teks dari tag yang bermakna
    - Normalisasi whitespace
    - Clip ke max_chars
    """
    if not html or not html.strip():
        return ""

    parser = _HTMLReadabilityParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as e:
        logger.warning(f"[WebScraper] HTML parse error: {e}")
        # Fallback: buang tag dengan regex sederhana
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]

    text = parser.get_clean_text()

    # Pisah baris dulu, filter baris pendek (navigasi/menu), baru normalisasi
    raw_lines = text.split("\n")
    filtered = [l.strip() for l in raw_lines if len(l.strip()) > 20]
    text = "\n".join(filtered) if filtered else text.strip()

    # Normalisasi whitespace per baris
    text = re.sub(r"\s+", " ", text).strip()

    # Clip
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"

    return text


# ---------------------------------------------------------------------------
# BrowserlessClient
# ---------------------------------------------------------------------------

_CONTENT_ENDPOINT = "/content"


class BrowserlessClient:
    """
    Client async untuk Browserless REST API.

    Contoh:
        scraper = BrowserlessClient()
        text = await scraper.scrape_url("https://example.com/article")
    """

    def __init__(self):
        self.api_key = BROWSERLESS_API_KEY
        self.base_url = BROWSERLESS_BASE_URL.rstrip("/")
        self.timeout = BROWSERLESS_TIMEOUT
        self.max_chars = BROWSERLESS_MAX_CHARS
        self.cache_ttl = BROWSERLESS_CACHE_TTL

        # Cache: { url: (timestamp, content) }
        self._cache: Dict[str, Tuple[float, str]] = {}
        self._cache_lock = asyncio.Lock()

        if not self.api_key:
            logger.warning(
                "[WebScraper] BROWSERLESS_API_KEY tidak ditemukan di .env! "
                "Fitur web scraping tidak akan berfungsi."
            )

    @property
    def enabled(self) -> bool:
        """Cek apakah BrowserClient siap digunakan."""
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    async def _get_cached(self, url: str) -> Optional[str]:
        """Ambil dari cache jika masih valid (berdasarkan TTL)."""
        async with self._cache_lock:
            entry = self._cache.get(url)
            if entry:
                ts, content = entry
                if time.time() - ts < self.cache_ttl:
                    logger.debug(f"[WebScraper] Cache hit: {url[:60]}")
                    return content
                # Expired
                self._cache.pop(url, None)
        return None

    async def _set_cached(self, url: str, content: str):
        """Simpan ke cache."""
        async with self._cache_lock:
            self._cache[url] = (time.time(), content)
            # Bersihkan cache lama jika terlalu besar
            if len(self._cache) > 50:
                now = time.time()
                expired = [k for k, (ts, _) in self._cache.items()
                           if now - ts >= self.cache_ttl]
                for k in expired:
                    self._cache.pop(k, None)

    # ------------------------------------------------------------------
    # Scrape via REST API
    # ------------------------------------------------------------------

    async def scrape_url(
        self,
        url: str,
        max_chars: Optional[int] = None,
    ) -> Optional[str]:
        """
        Ambil konten website via Browserless REST API.

        Args:
            url: URL website yang akan di-scrap
            max_chars: Maks karakter (default dari config)

        Returns:
            Teks bersih dari website, atau None jika gagal
        """
        if not self.enabled:
            logger.warning("[WebScraper] Tidak aktif (API key missing)")
            return None

        # SSRF check
        safe, reason = _is_safe_url(url)
        if not safe:
            logger.warning(f"[WebScraper] URL tidak aman: {reason}")
            return None

        max_chars = max_chars or self.max_chars

        # Cek cache dulu
        cached = await self._get_cached(url)
        if cached is not None:
            return cached

        # Bangun endpoint
        endpoint = f"{self.base_url}{_CONTENT_ENDPOINT}"
        params = {"token": self.api_key} if self.api_key else {}

        payload = {
            "url": url,
            "bestAttempt": True,
            "gotoOptions": {
                "waitUntil": "domcontentloaded",
                "timeout": self.timeout * 1000,
            },
            "rejectResourceTypes": ["image", "font", "stylesheet", "media"],
            "rejectRequestPattern": [
                ".*google-analytics.*",
                ".*googletagmanager.*",
                ".*facebook\\.com/tr.*",
                ".*doubleclick\\.net.*",
            ],
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    endpoint,
                    params=params,
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        text = _clean_html(html, max_chars)

                        if text and len(text) > 100:
                            await self._set_cached(url, text)
                            logger.info(
                                f"[WebScraper] Sukses: {url[:60]} "
                                f"({len(text)} chars)"
                            )
                            return text

                        # Fallback: /content returned empty/short, try /scrape
                        logger.info(
                            f"[WebScraper] /content short ({len(text) if text else 0} chars), "
                            f"fallback ke /scrape: {url[:60]}"
                        )
                        structured = await self._scrape_structured(url, max_chars)
                        if structured:
                            await self._set_cached(url, structured)
                            return structured
                        return text or None

                    elif resp.status == 402:
                        logger.error(
                            "[WebScraper] Kuota Browserless habis (402)"
                        )
                        return None
                    elif resp.status == 429:
                        logger.warning(
                            "[WebScraper] Rate limited (429), skip"
                        )
                        return None
                    else:
                        txt = await resp.text()
                        logger.error(
                            f"[WebScraper] HTTP {resp.status}: {txt[:200]}"
                        )
                        return None

        except asyncio.TimeoutError:
            logger.warning(f"[WebScraper] Timeout: {url[:60]}")
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"[WebScraper] Connection error: {e}")
            return None
        except Exception as e:
            logger.exception(f"[WebScraper] Unexpected error: {e}")
            return None

    def extract_urls(self, text: str) -> list[str]:
        """
        Ekstrak URL dari teks.
        """
        pattern = r"https?://[^\s<>\"']+"
        return re.findall(pattern, text)

    # ------------------------------------------------------------------
    # Structured scrape fallback — /scrape endpoint
    # ------------------------------------------------------------------

    async def _scrape_structured(
        self,
        url: str,
        max_chars: Optional[int] = None,
    ) -> Optional[str]:
        """
        Fallback scraper menggunakan endpoint /scrape dengan CSS selectors.
        Dipanggil ketika /content mengembalikan teks terlalu pendek (<100 chars).
        """
        if not self.enabled:
            return None

        max_chars = max_chars or self.max_chars
        endpoint = f"{self.base_url}/scrape"
        params = {"token": self.api_key} if self.api_key else {}

        payload = {
            "url": url,
            "elements": [
                {
                    "selector": "article, .article-body, .entry-content, .post-content, main, .main-content",
                    "timeout": 5000,
                },
                {
                    "selector": "h1, .article-title, .entry-title, .post-title",
                    "timeout": 3000,
                },
            ],
            "bestAttempt": True,
            "gotoOptions": {
                "waitUntil": "domcontentloaded",
                "timeout": self.timeout * 1000,
            },
            "rejectResourceTypes": ["image", "font", "stylesheet", "media"],
            "setJavaScriptEnabled": True,
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout + 5)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    endpoint,
                    params=params,
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"[WebScraper] /scrape HTTP {resp.status}: {url[:60]}"
                        )
                        return None

                    data = await resp.json()
                    texts = []

                    for item in data.get("data", []):
                        for result in item.get("results", []):
                            text = result.get("text", "").strip()
                            if text and len(text) > 20:
                                texts.append(text)

                    if not texts:
                        return None

                    combined = "\n\n".join(texts)
                    combined = re.sub(r"\s+", " ", combined).strip()

                    if len(combined) > max_chars:
                        combined = combined[:max_chars].rsplit(" ", 1)[0] + "..."

                    logger.info(
                        f"[WebScraper] /scrape OK: {url[:60]} ({len(combined)} chars)"
                    )
                    return combined

        except Exception as e:
            logger.warning(f"[WebScraper] /scrape failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Search via Browserless /search endpoint (SearXNG)
    # ------------------------------------------------------------------

    async def search_via_browserless(
        self,
        query: str,
        max_results: int = 5,
    ) -> Optional[dict]:
        """
        Search the web using Browserless /search endpoint (SearXNG).
        Tertiary fallback when both Tavily and DuckDuckGo fail.
        """
        if not self.enabled:
            return None

        endpoint = f"{self.base_url}/search"
        params = {"token": self.api_key} if self.api_key else {}
        payload = {"query": query}

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    endpoint,
                    params=params,
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"[WebScraper] /search HTTP {resp.status}"
                        )
                        return None

                    data = await resp.json()
                    results = []
                    for r in data if isinstance(data, list) else data.get("results", []):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", r.get("link", "")),
                            "content": r.get("content", r.get("snippet", "")),
                        })

                    if results:
                        logger.info(
                            f"[WebScraper] /search OK: '{query[:50]}' "
                            f"({len(results)} results)"
                        )
                        return {
                            "results": results[:max_results],
                            "answer": "",
                            "engine": "browserless",
                        }
                    return None

        except Exception as e:
            logger.warning(f"[WebScraper] /search failed: {e}")
            return None


# ---------------------------------------------------------------------------
# Quick test (python -m ai.web_scraper)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _test():
        client = BrowserlessClient()
        print(f"Enabled: {client.enabled}")
        if client.enabled:
            text = await client.scrape_url("https://example.com")
            print(f"\nContent:\n{text[:500]}")
        else:
            print("Set BROWSERLESS_API_KEY di .env untuk test.")

    asyncio.run(_test())
