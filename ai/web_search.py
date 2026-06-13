"""
ai/web_search.py — Tavily + DuckDuckGo Web Search Client
─────────────────────────────────────────────────────────
Menyediakan pencarian web aktif untuk Mirai.

Primary: Tavily Search API (REST, aiohttp)
  POST https://api.tavily.com/search
  Body: { "api_key": "...", "query": "...", "max_results": 5, "search_depth": "basic" }

Fallback: DuckDuckGo via duckduckgo-search library (no API key needed)

Fitur:
  - Tavily: hasil bersih, AI-optimized, include_answer
  - DuckDuckGo: fallback gratis tanpa key
  - Cache per query (TTL 5 menit)
  - Result clipping ke max_chars
  - Format LLM-ready
"""

import os
import time
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple
from config import (
    TAVILY_API_KEY,
    TAVILY_BASE_URL,
    TAVILY_TIMEOUT,
    TAVILY_MAX_RESULTS,
    TAVILY_MAX_CHARS,
    TAVILY_CACHE_TTL,
    TAVILY_SEARCH_DEPTH,
)
from utils.logger import setup_logging

logger = setup_logging()

# ---------------------------------------------------------------------------
# WebSearchClient
# ---------------------------------------------------------------------------

class WebSearchClient:
    """
    Client async untuk pencarian web via Tavily API + DuckDuckGo fallback.

    Contoh:
        searcher = WebSearchClient()
        results = await searcher.search("apa itu diabetes")
    """

    def __init__(self):
        self.api_key = TAVILY_API_KEY
        self.base_url = TAVILY_BASE_URL.rstrip("/")
        self.timeout = TAVILY_TIMEOUT
        self.max_results = TAVILY_MAX_RESULTS
        self.max_chars = TAVILY_MAX_CHARS
        self.cache_ttl = TAVILY_CACHE_TTL
        self.search_depth = TAVILY_SEARCH_DEPTH

        self._cache: Dict[str, Tuple[float, dict]] = {}
        self._cache_lock = asyncio.Lock()

        if not self.api_key:
            logger.warning(
                "[WebSearch] TAVILY_API_KEY tidak ditemukan di .env! "
                "Fitur web search akan menggunakan fallback DuckDuckGo."
            )

    @property
    def enabled(self) -> bool:
        """Web search selalu available (Tavily atau DuckDuckGo fallback)."""
        return True

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _normalize_query(self, query: str) -> str:
        """Normalisasi query untuk cache key."""
        return query.strip().lower()

    async def _get_cached(self, query: str) -> Optional[dict]:
        """Ambil dari cache jika masih valid."""
        key = self._normalize_query(query)
        async with self._cache_lock:
            entry = self._cache.get(key)
            if entry:
                ts, data = entry
                if time.time() - ts < self.cache_ttl:
                    logger.debug(f"[WebSearch] Cache hit: {query[:60]}")
                    return data
                self._cache.pop(key, None)
        return None

    async def _set_cached(self, query: str, data: dict):
        """Simpan ke cache."""
        key = self._normalize_query(query)
        async with self._cache_lock:
            self._cache[key] = (time.time(), data)
            if len(self._cache) > 50:
                now = time.time()
                expired = [k for k, (ts, _) in self._cache.items()
                           if now - ts >= self.cache_ttl]
                for k in expired:
                    self._cache.pop(k, None)

    # ------------------------------------------------------------------
    # Tavily Search
    # ------------------------------------------------------------------

    async def _search_tavily(self, query: str) -> Optional[dict]:
        """
        Cari via Tavily REST API.

        Returns:
            dict dengan keys: results (list), answer (str|None)
            Atau None jika gagal.
        """
        if not self.api_key:
            return None

        endpoint = f"{self.base_url}/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": self.max_results,
            "search_depth": self.search_depth,
            "include_answer": True,
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = []
                        for r in data.get("results", []):
                            results.append({
                                "title": r.get("title", ""),
                                "url": r.get("url", ""),
                                "content": r.get("content", ""),
                            })

                        answer = data.get("answer", "")
                        logger.info(
                            f"[WebSearch] Tavily OK: '{query[:50]}' "
                            f"({len(results)} results)"
                        )
                        return {"results": results, "answer": answer}

                    elif resp.status == 401:
                        logger.error("[WebSearch] Tavily API key invalid (401)")
                        return None
                    elif resp.status == 429:
                        logger.warning("[WebSearch] Tavily rate limited (429)")
                        return None
                    else:
                        txt = await resp.text()
                        logger.error(f"[WebSearch] Tavily HTTP {resp.status}: {txt[:200]}")
                        return None

        except asyncio.TimeoutError:
            logger.warning(f"[WebSearch] Tavily timeout: {query[:50]}")
            return None
        except Exception as e:
            logger.warning(f"[WebSearch] Tavily error: {e}")
            return None

    # ------------------------------------------------------------------
    # DuckDuckGo Fallback
    # ------------------------------------------------------------------

    async def _search_duckduckgo(self, query: str) -> Optional[dict]:
        """
        Fallback: cari via DuckDuckGo (duckduckgo-search library).
        Hanya dipakai jika Tavily tidak tersedia atau gagal.
        """
        try:
            from duckduckgo_search import AsyncDDGS

            results = []
            async with AsyncDDGS() as ddgs:
                async for r in ddgs.atext(query, max_results=self.max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "content": r.get("body", ""),
                    })

            if results:
                logger.info(
                    f"[WebSearch] DuckDuckGo OK: '{query[:50]}' "
                    f"({len(results)} results)"
                )
                return {"results": results, "answer": ""}

            logger.warning(f"[WebSearch] DuckDuckGo: no results for '{query[:50]}'")
            return None

        except ImportError:
            logger.error("[WebSearch] duckduckgo-search library not installed")
            return None
        except Exception as e:
            logger.warning(f"[WebSearch] DuckDuckGo error: {e}")
            return None

    # ------------------------------------------------------------------
    # Public: search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Cari di web. Tavily primary, DuckDuckGo fallback.

        Args:
            query: Kata kunci pencarian
            max_results: Override max results (default dari config)

        Returns:
            dict: {"results": [...], "answer": "..."} atau None
        """
        if not query or not query.strip():
            return None

        if max_results:
            self.max_results = max_results

        cached = await self._get_cached(query)
        if cached is not None:
            return cached

        data = await self._search_tavily(query)

        if data is None:
            logger.info("[WebSearch] Tavily gagal, fallback ke DuckDuckGo")
            data = await self._search_duckduckgo(query)

        if data is None:
            return None

        data["results"] = self._clip_results(data["results"])
        await self._set_cached(query, data)
        return data

    # ------------------------------------------------------------------
    # Format helpers
    # ------------------------------------------------------------------

    def _clip_results(self, results: List[dict]) -> List[dict]:
        """Clip total konten agar tidak melebihi max_chars."""
        total = 0
        clipped = []
        for r in results:
            content = r.get("content", "")
            if total + len(content) > self.max_chars:
                remaining = self.max_chars - total
                if remaining > 50:
                    r["content"] = content[:remaining].rsplit(" ", 1)[0] + "..."
                    clipped.append(r)
                break
            clipped.append(r)
            total += len(content)
        return clipped

    def format_for_llm(self, data: dict, query: str) -> str:
        """
        Format hasil search menjadi konteks untuk LLM system prompt.
        """
        if not data or not data.get("results"):
            return ""

        lines = [f"\n\n[HASIL PENCARIAN WEB: \"{query}\"]"]

        answer = data.get("answer", "")
        if answer:
            lines.append(f"\nJawaban singkat: {answer}\n")

        for i, r in enumerate(data["results"], 1):
            title = r.get("title", "Tanpa judul")
            url = r.get("url", "")
            content = r.get("content", "")
            lines.append(f"{i}. [{title}] - {url}")
            if content:
                lines.append(f"   {content}")

        lines.append(
            "\nINSTRUKSI: Data di atas adalah hasil pencarian web REAL. "
            "Gunakan informasi ini untuk menjawab pertanyaan user secara akurat "
            "dan faktual. Selalu sebutkan sumber URL saat relevan."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quick test (python -m ai.web_search)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _test():
        client = WebSearchClient()
        print(f"Enabled: {client.enabled}")
        print(f"Tavily key: {'Yes' if client.api_key else 'No (DuckDuckGo fallback)'}")

        data = await client.search("apa itu diabetes melitus")
        if data:
            print(f"\nAnswer: {data.get('answer', '-')}")
            for i, r in enumerate(data["results"], 1):
                print(f"\n{i}. {r['title']}")
                print(f"   {r['url']}")
                print(f"   {r['content'][:150]}...")
        else:
            print("\nNo results.")

    asyncio.run(_test())
