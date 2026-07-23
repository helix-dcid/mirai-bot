# ai/jurnal.py — Pencarian Referensi Jurnal Ilmiah
"""
Client async untuk pencarian jurnal akademik via CrossRef API.
Gratis, tanpa API key. Mencakup semua disiplin ilmu.
CrossRef: https://api.crossref.org/swagger-ui/index.html
"""

import asyncio
import aiohttp
from typing import Optional
from utils.logger import setup_logging

logger = setup_logging()

CROSSREF_BASE = "https://api.crossref.org/works"
TIMEOUT = 15
MAX_RESULTS = 5


class JurnalClient:
    """
    Pencarian referensi jurnal ilmiah via CrossRef API.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "MiraiHelix/4.3 (mailto:mirai@helix.my.id)",
                    "Accept": "application/json",
                }
            )
        return self._session

    async def search(self, query: str, max_results: int = MAX_RESULTS) -> Optional[dict]:
        """
        Cari referensi jurnal berdasarkan query.

        Args:
            query: Kata kunci pencarian (topik, judul, penulis).
            max_results: Maksimal hasil yang dikembalikan.

        Returns:
            Dict dengan daftar artikel, atau None jika gagal.
        """
        if not query or len(query.strip()) < 3:
            return None

        params = {
            "query": query.strip(),
            "rows": min(max_results, 10),
            "sort": "relevance",
            "order": "desc",
        }

        try:
            session = await self._get_session()
            async with session.get(
                CROSSREF_BASE, params=params, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[Jurnal] CrossRef HTTP {resp.status}")
                    return None

                data = await resp.json()
                items = data.get("message", {}).get("items", [])
                if not items:
                    return None

                results = []
                for item in items[:max_results]:
                    title = item.get("title", [""])[0] if item.get("title") else "No title"
                    authors = []
                    for author in item.get("author", []):
                        given = author.get("given", "")
                        family = author.get("family", "")
                        name = f"{given} {family}".strip()
                        if name:
                            authors.append(name)
                    container = item.get("container-title", [""])[0] if item.get("container-title") else ""
                    year = (item.get("published-print", {}) or item.get("published-online", {}) or {}).get("date-parts", [[None]])[0][0]
                    doi = item.get("DOI", "")
                    url = f"https://doi.org/{doi}" if doi else ""
                    abstract = item.get("abstract", "")
                    if abstract:
                        import re
                        abstract = re.sub(r"<[^>]+>", "", abstract)[:500]

                    results.append({
                        "title": title,
                        "authors": authors,
                        "journal": container,
                        "year": year,
                        "doi": doi,
                        "url": url,
                        "abstract": abstract,
                    })

                return {
                    "query": query.strip(),
                    "total_results": data.get("message", {}).get("total-results", 0),
                    "results": results,
                }

        except asyncio.TimeoutError:
            logger.warning("[Jurnal] CrossRef request timed out")
            return None
        except Exception as e:
            logger.warning(f"[Jurnal] Error: {e}")
            return None

    async def close(self):
        """Tutup session HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()
