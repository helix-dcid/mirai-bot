"""
ai/web_search.py — Tavily + DuckDuckGo Web Search Client
─────────────────────────────────────────────────────────
Menyediakan pencarian web aktif untuk Mirai.

Primary: Tavily Search API (REST, aiohttp)
  POST https://api.tavily.com/search

Fallback: DuckDuckGo via duckduckgo-search library (no API key needed)

Fitur:
  - Persistent aiohttp session (reuse connections)
  - Retry with exponential backoff untuk transient errors
  - Adaptive search depth (basic/advanced based on query)
  - Query validation & length limit
  - Cache per query (TTL 5 menit)
  - Result clipping ke max_chars
  - Format LLM-ready dengan instruksi sitasi
  - Engine tracking (tavily/duckduckgo)
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
        self._session: Optional[aiohttp.ClientSession] = None

        if not self.api_key:
            logger.warning(
                "[WebSearch] TAVILY_API_KEY tidak ditemukan di .env! "
                "Fitur web search akan menggunakan fallback DuckDuckGo."
            )

    @property
    def enabled(self) -> bool:
        """Cek apakah search tersedia (Tavily key ATAU duckduckgo-search ter-install)."""
        if self.api_key:
            return True
        try:
            from duckduckgo_search import AsyncDDGS
            return True
        except ImportError:
            return False

    async def close(self):
        """Close persistent aiohttp session. Panggil saat bot shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create persistent aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _normalize_query(self, query: str) -> str:
        return query.strip().lower()

    async def _get_cached(self, query: str) -> Optional[dict]:
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
    # Adaptive search depth
    # ------------------------------------------------------------------

    def _determine_search_depth(self, query: str) -> str:
        words = query.split()
        if len(words) > 8 or "?" in query:
            return "advanced"
        return self.search_depth

    # ------------------------------------------------------------------
    # Tavily Search (with retry)
    # ------------------------------------------------------------------

    async def _search_tavily(self, query: str, max_results: int,
                             max_retries: int = 2) -> Optional[dict]:
        if not self.api_key:
            return None

        endpoint = f"{self.base_url}/search"
        depth = self._determine_search_depth(query)
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": depth,
            "include_answer": True,
        }

        session = await self._get_session()

        for attempt in range(max_retries + 1):
            try:
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
                            f"({len(results)} results, depth={depth})"
                        )
                        return {"results": results, "answer": answer, "engine": "tavily"}

                    elif resp.status == 401:
                        logger.error("[WebSearch] Tavily API key invalid (401)")
                        return None
                    elif resp.status == 429:
                        logger.warning("[WebSearch] Tavily rate limited (429)")
                        return None
                    elif resp.status in (500, 502, 503, 504):
                        logger.warning(f"[WebSearch] Tavily HTTP {resp.status} (attempt {attempt+1})")
                        if attempt < max_retries:
                            await asyncio.sleep(min(2 ** attempt, 10))
                            continue
                        return None
                    else:
                        txt = await resp.text()
                        logger.error(f"[WebSearch] Tavily HTTP {resp.status}: {txt[:200]}")
                        return None

            except asyncio.TimeoutError:
                logger.warning(f"[WebSearch] Tavily timeout (attempt {attempt+1}): {query[:50]}")
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))
                    continue
                return None
            except Exception as e:
                logger.warning(f"[WebSearch] Tavily error: {e}")
                return None

        return None

    # ------------------------------------------------------------------
    # DuckDuckGo Fallback
    # ------------------------------------------------------------------

    async def _search_duckduckgo(self, query: str, max_results: int) -> Optional[dict]:
        try:
            from duckduckgo_search import AsyncDDGS

            results = []
            async with AsyncDDGS() as ddgs:
                async for r in ddgs.atext(query, max_results=max_results):
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
                return {"results": results, "answer": "", "engine": "duckduckgo"}

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
            dict: {"results": [...], "answer": "...", "engine": "tavily"|"duckduckgo"}
                  atau None
        """
        if not query or not query.strip():
            return None

        query = query.strip()
        if len(query) > 500:
            query = query[:500]
        if len(query) < 2:
            return None

        effective_max = max_results or self.max_results

        cached = await self._get_cached(query)
        if cached is not None:
            return cached

        data = await self._search_tavily(query, effective_max)

        if data is None:
            logger.info("[WebSearch] Tavily gagal, fallback ke DuckDuckGo")
            data = await self._search_duckduckgo(query, effective_max)

        if data is None:
            return None

        data["results"] = self._clip_results(data["results"])
        await self._set_cached(query, data)
        return data

    # ------------------------------------------------------------------
    # Format helpers
    # ------------------------------------------------------------------

    def _clip_results(self, results: List[dict]) -> List[dict]:
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
        Termasuk instruksi sitasi terstruktur.
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

        engine = data.get("engine", "web")
        lines.append(
            f"\nINSTRUKSI SITASI: Data di atas adalah hasil pencarian web REAL dari {engine}. "
            "Setiap klaim faktual WAJIB diikuti nomor sumber [1], [2], dst. "
            "Di akhir jawaban, buat section 'Sumber:' yang berisi daftar URL bernomor. "
            "Bedakan dengan jelas antara pengetahuanmu sendiri dan informasi dari pencarian web. "
            "Di akhir jawaban, tawarkan 2-3 pertanyaan lanjutan yang mungkin menarik bagi user "
            "dengan format: 'Mau tahu lebih lanjut? Coba tanya: ...'"
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
            print(f"\nEngine: {data.get('engine', '-')}")
            print(f"Answer: {data.get('answer', '-')}")
            for i, r in enumerate(data["results"], 1):
                print(f"\n{i}. {r['title']}")
                print(f"   {r['url']}")
                print(f"   {r['content'][:150]}...")
        else:
            print("\nNo results.")

        await client.close()

    asyncio.run(_test())
