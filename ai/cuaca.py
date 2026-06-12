# ai/cuaca.py - Integrasi API BMKG untuk Mirai
"""
Modul untuk mengambil data cuaca dari API Terbuka BMKG.
Mendukung pencarian cuaca berdasarkan nama lokasi menggunakan database
wilayah Indonesia (cahyadsn/wilayah) via aiosqlite.

FIXED:
- Ganti Emsifa REST API → lokal SQLite wilayah.db (aiosqlite, non-blocking)
- Hapus logging.basicConfig() — gunakan setup_logging() dari utils
- Tambah _ensure_wilayah_db() untuk setup DB otomatis dari wilayah.sql
- search_location_code() kini query SQLite secara async (LIKE fuzzy search)
- _CITY_FALLBACK diperluas: 16 → 50+ kota besar + alias populer
  (Solo→Surakarta, Jogja→Yogyakarta, dll)
- _search_db: kode non-adm4 tidak lagi dikembalikan; resolusi ke adm4 dipaksa
"""

import aiohttp
import sys, os
# Ensure utils package is importable when running as script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aiosqlite
import asyncio
import re
import os
import json
from typing import Any, Dict, Optional
from pathlib import Path

# Brotli opsional — fallback jika tidak terinstal
try:
    import brotli
    _HAS_BROTLI = True
except ImportError:
    _HAS_BROTLI = False

from utils.logger import setup_logging

logger = setup_logging()

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------
BMKG_API_URL = "https://api.bmkg.go.id/publik/prakiraan-cuaca"

# URL SQL dump wilayah (cahyadsn/wilayah di GitHub)
WILAYAH_SQL_URL = (
    "https://github.com/cahyadsn/wilayah/raw/refs/heads/master/db/wilayah.sql"
)

# Lokasi file DB (relatif ke root project)
_DATA_DIR  = Path(__file__).parent.parent / "data"
DB_PATH    = _DATA_DIR / "wilayah.db"
SQL_PATH   = _DATA_DIR / "wilayah.sql"

# Default kode adm4 (Kemayoran, Jakarta Pusat) — fallback jika lokasi tak ditemukan
DEFAULT_ADM4 = "31.71.03.1001"

# ---------------------------------------------------------------------------
# Fallback statis: kota besar + kode adm4 (desa/kelurahan pertama di kota itu)
# Pakai ini agar kota populer langsung dapat tanpa query DB
# ---------------------------------------------------------------------------
_CITY_FALLBACK: Dict[str, str] = {
    # === PULAU JAWA ===
    "JAKARTA"         : "31.71.03.1001",  # Jakarta Pusat (Kemayoran)
    "BANDUNG"         : "32.73.01.1001",  # Kota Bandung
    "SURABAYA"        : "35.78.01.1001",  # Kota Surabaya
    "SEMARANG"        : "33.74.01.1001",  # Kota Semarang
    "YOGYAKARTA"      : "34.71.01.1001",  # Kota Yogyakarta
    "SURAKARTA"       : "33.72.01.1001",  # Kota Surakarta (Solo)
    "SOLO"            : "33.72.01.1001",  # Alias Surakarta
    "JOGJA"           : "34.71.01.1001",  # Alias Yogyakarta
    "JOGJAKARTA"      : "34.71.01.1001",  # Alias Yogyakarta

    # Jabodetabek
    "BEKASI"          : "32.75.01.1001",  # Kota Bekasi
    "TANGERANG"       : "36.71.01.1001",  # Kota Tangerang
    "TANGSEL"         : "36.74.01.1001",  # Kota Tangerang Selatan
    "DEPOK"           : "32.76.01.1001",  # Kota Depok
    "BOGOR"           : "32.71.01.1001",  # Kota Bogor

    # Jawa Barat lainnya
    "CIMAHI"          : "32.77.01.1001",  # Kota Cimahi
    "CIREBON"         : "32.74.01.1001",  # Kota Cirebon
    "SUKABUMI"        : "32.72.01.1001",  # Kota Sukabumi
    "TASIKMALAYA"     : "32.78.01.1001",  # Kota Tasikmalaya
    "BANJAR"          : "32.79.01.1001",  # Kota Banjar

    # Jawa Tengah lainnya
    "SALATIGA"        : "33.73.01.1001",  # Kota Salatiga
    "PEKALONGAN"      : "33.75.01.1001",  # Kota Pekalongan
    "TEGAL"           : "33.76.01.1001",  # Kota Tegal
    "MAGELANG"        : "33.71.01.1001",  # Kota Magelang

    # Jawa Timur lainnya
    "MALANG"          : "35.73.01.1001",  # Kota Malang
    "KEDIRI"          : "35.71.01.1001",  # Kota Kediri
    "BLITAR"          : "35.72.01.1001",  # Kota Blitar
    "MADIUN"          : "35.77.01.1001",  # Kota Madiun
    "MOJOKERTO"       : "35.76.01.1001",  # Kota Mojokerto
    "PASURUAN"        : "35.75.01.1001",  # Kota Pasuruan
    "PROBOLINGGO"     : "35.74.01.1001",  # Kota Probolinggo
    "BATU"            : "35.79.01.1001",  # Kota Batu

    # Banten
    "CILEGON"         : "36.72.01.1001",  # Kota Cilegon
    "SERANG"          : "36.73.01.1001",  # Kota Serang

    # === SUMATERA ===
    "MEDAN"           : "12.71.01.1001",  # Kota Medan
    "PADANG"          : "13.71.01.1001",  # Kota Padang
    "PALEMBANG"       : "16.71.01.1001",  # Kota Palembang
    "PEKANBARU"       : "14.71.01.1001",  # Kota Pekanbaru
    "BANDAR LAMPUNG"  : "18.71.01.1001",  # Kota Bandar Lampung
    "LAMPUNG"         : "18.71.01.1001",  # Alias Bandar Lampung
    "BATAM"           : "21.71.01.1001",  # Kota Batam
    "JAMBI"           : "15.71.01.1001",  # Kota Jambi
    "BENGKULU"        : "17.71.01.1001",  # Kota Bengkulu
    "PONTIANAK"       : "61.71.01.1001",  # Kota Pontianak

    # Sumatera lainnya
    "BANDA ACEH"      : "11.71.01.1001",  # Kota Banda Aceh
    "LHOKSEUMAWE"     : "11.73.01.1001",  # Kota Lhokseumawe
    "PEMATANGSIANTAR" : "12.72.01.1001",  # Kota Pematangsiantar
    "BUKITTINGGI"     : "13.75.01.1001",  # Kota Bukittinggi
    "DUMAI"           : "14.72.01.1001",  # Kota Dumai
    "TANJUNG PINANG"  : "21.72.01.1001",  # Kota Tanjung Pinang
    "LUBUKLINGGAU"    : "16.73.01.1001",  # Kota Lubuklinggau
    "PANGKAL PINANG"  : "19.71.01.1001",  # Kota Pangkal Pinang
    "METRO"           : "18.72.01.1001",  # Kota Metro

    # === KALIMANTAN ===
    "BALIKPAPAN"      : "64.71.01.1001",  # Kota Balikpapan
    "SAMARINDA"       : "64.72.01.1001",  # Kota Samarinda
    "BANJARMASIN"     : "63.71.01.1001",  # Kota Banjarmasin
    "BANJARBARU"      : "63.72.01.1001",  # Kota Banjarbaru
    "PALANGKA RAYA"   : "62.71.01.1001",  # Kota Palangka Raya
    "SINGKAWANG"      : "61.72.01.1001",  # Kota Singkawang
    "BONTANG"         : "64.74.01.1001",  # Kota Bontang
    "TARAKAN"         : "65.71.01.1001",  # Kota Tarakan

    # === SULAWESI ===
    "MAKASSAR"        : "73.71.01.1001",  # Kota Makassar
    "MANADO"          : "71.71.01.1001",  # Kota Manado
    "PALU"            : "72.71.01.1001",  # Kota Palu
    "KENDARI"         : "74.71.01.1001",  # Kota Kendari
    "GORONTALO"       : "75.71.01.1001",  # Kota Gorontalo
    "PAREPARE"        : "73.72.01.1001",  # Kota Parepare
    "PALOPO"          : "73.73.01.1001",  # Kota Palopo
    "BITUNG"          : "71.72.01.1001",  # Kota Bitung
    "TOMOHON"         : "71.73.01.1001",  # Kota Tomohon
    "KOTAMOBAGU"      : "71.74.01.1001",  # Kota Kotamobagu
    "BAUBAU"          : "74.72.01.1001",  # Kota Bau-Bau

    # === NUSA TENGGARA & BALI ===
    "DENPASAR"        : "51.71.01.1001",  # Kota Denpasar
    "MATARAM"         : "52.71.01.1001",  # Kota Mataram
    "KUPANG"          : "53.71.01.1001",  # Kota Kupang
    "BIMA"            : "52.72.01.1001",  # Kota Bima

    # === MALUKU & PAPUA ===
    "AMBON"           : "81.71.01.1001",  # Kota Ambon
    "TERNATE"         : "82.71.01.1001",  # Kota Ternate
    "TIDORE"          : "82.72.01.1001",  # Kota Tidore
    "JAYAPURA"        : "91.71.01.1001",  # Kota Jayapura
    "SORONG"          : "92.71.01.1001",  # Kota Sorong
    "MANOKWARI"       : "92.72.01.1001",  # Kota Manokwari (Perdema)
}

# ---------------------------------------------------------------------------
# Setup database wilayah (download sekali, simpan lokal)
# ---------------------------------------------------------------------------

async def _download_wilayah_sql() -> bool:
    """Download wilayah.sql dari GitHub ke data/wilayah.sql."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(WILAYAH_SQL_URL) as resp:
                if resp.status != 200:
                    logger.error(f"[Cuaca] Gagal download wilayah.sql: HTTP {resp.status}")
                    return False
                content = await resp.read()
                SQL_PATH.write_bytes(content)
                logger.info(f"[Cuaca] wilayah.sql berhasil diunduh ({len(content):,} bytes)")
                return True
    except Exception as e:
        logger.error(f"[Cuaca] Error download wilayah.sql: {e}")
        return False


async def _import_sql_to_db() -> bool:
    """
    Parse wilayah.sql dan import ke wilayah.db via aiosqlite.

    Format SQL dump dari cahyadsn/wilayah:
        INSERT INTO wilayah (kode, nama)
        VALUES
        ('11','Aceh'),
        ('11.01','Kabupaten Aceh Selatan'),
        ...;

    Tabel target:
        wilayah(kode TEXT PRIMARY KEY, nama TEXT NOT NULL)
    """
    if not SQL_PATH.exists():
        logger.error("[Cuaca] wilayah.sql tidak ditemukan, tidak bisa import.")
        return False

    sql_text = SQL_PATH.read_text(encoding="utf-8", errors="replace")

    # Ekstrak baris dari INSERT ... VALUES (...), (...), ...;
    # Format: INSERT INTO wilayah (kode, nama)\\nVALUES\\n('kode','nama'),\\n('kode','nama');
    pattern = re.compile(
        r"INSERT\s+INTO\s+wilayah\s*\([^)]+\)\s*VALUES\s*(.*?);",
        re.IGNORECASE | re.DOTALL,
    )

    # Parse row: ('kode','nama') — handle escaped single quotes inside nama
    row_pat = re.compile(r"\('([^']+)',\s*'((?:[^'\\]|\\.)*)'\)")

    rows: list[tuple[str, str]] = []
    for match in pattern.finditer(sql_text):
        values_block = match.group(1).strip()
        for row in row_pat.finditer(values_block):
            rows.append((row.group(1), row.group(2)))

    if not rows:
        logger.error("[Cuaca] Tidak ada baris ditemukan di wilayah.sql.")
        return False

    try:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS wilayah "
                "(kode TEXT PRIMARY KEY, nama TEXT NOT NULL)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_nama ON wilayah(nama)"
            )
            await db.executemany(
                "INSERT OR REPLACE INTO wilayah(kode, nama) VALUES (?, ?)", rows
            )
            await db.commit()
        logger.info(f"[Cuaca] Import selesai: {len(rows):,} baris ke wilayah.db")
        return True
    except Exception as e:
        logger.error(f"[Cuaca] Error import ke DB: {e}")
        DB_PATH.unlink(missing_ok=True)
        return False


async def ensure_wilayah_db() -> bool:
    """
    Pastikan wilayah.db tersedia dan terisi.
    Download + import otomatis jika belum ada.
    Dipanggil sekali saat startup atau saat pertama kali dibutuhkan.
    """
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        return True

    logger.info("[Cuaca] wilayah.db belum ada, memulai setup...")

    if not SQL_PATH.exists():
        ok = await _download_wilayah_sql()
        if not ok:
            return False

    ok = await _import_sql_to_db()

    # Hapus file SQL setelah berhasil import untuk hemat disk
    if ok and SQL_PATH.exists():
        SQL_PATH.unlink()
        logger.info("[Cuaca] wilayah.sql dihapus setelah import.")

    return ok


# ---------------------------------------------------------------------------
# Pencarian wilayah via aiosqlite
# ---------------------------------------------------------------------------

def _count_dots(kode: str) -> int:
    """Hitung level hirarki berdasarkan jumlah titik di kode."""
    return kode.count(".")


async def _search_db(query: str) -> Optional[str]:
    """
    Cari kode adm4 (desa/kelurahan, 3 titik) di wilayah.db berdasarkan nama.

    Strategi prioritas:
    1. Exact match (case-insensitive) di level **kota/kabupaten** (1 titik)
       → ambil kelurahan pertama di bawahnya → PASTIKAN adm4
    2. Exact match di level **kecamatan** (2 titik) → ambil kelurahan pertama
    3. Exact match di level **desa** (3 titik)
    4. Fuzzy LIKE di semua level → paling spesifik → pastikan adm4

    FIXED: Fungsi ini TIDAK PERNAH mengembalikan kode non-adm4 (kurang dari 3 titik).
    Jika kelurahan tidak ditemukan, gunakan DEFAULT_ADM4.
    """
    if not DB_PATH.exists():
        return None

    q_upper = query.upper().strip()

    try:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row

            # Helper: cari kelurahan/desa pertama di bawah kode tertentu
            async def _first_child(kode_prefix: str) -> Optional[str]:
                async with db.execute(
                    "SELECT kode FROM wilayah "
                    "WHERE kode LIKE ? AND LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 3 "
                    "LIMIT 1",
                    (f"{kode_prefix}.%",),
                ) as cur:
                    row = await cur.fetchone()
                    return row["kode"] if row else None

            # 1) Exact match di level kota/kabupaten (1 titik)
            #    Cari "Kota {query}" dulu, lalu "Kabupaten {query}"
            for prefix in ("KOTA", "KABUPATEN"):
                async with db.execute(
                    "SELECT kode FROM wilayah "
                    "WHERE UPPER(nama) = ? "
                    "AND LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 1 "
                    "LIMIT 1",
                    (f"{prefix} {q_upper}",),
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        child = await _first_child(row["kode"])
                        if child:
                            return child  # ✅ adm4
                        # Jika tidak ada child, coba cari adm4 lain di provinsi yg sama
                        prov_code = row["kode"].split(".")[0]
                        async with db.execute(
                            "SELECT kode FROM wilayah "
                            "WHERE kode LIKE ? AND LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 3 "
                            "LIMIT 1",
                            (f"{prov_code}.%",),
                        ) as cur2:
                            fallback = await cur2.fetchone()
                            if fallback:
                                return fallback["kode"]

            # Coba exact match tanpa prefix di level kota
            async with db.execute(
                "SELECT kode FROM wilayah "
                "WHERE UPPER(nama) = ? "
                "AND LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 1 "
                "LIMIT 1",
                (q_upper,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    child = await _first_child(row["kode"])
                    if child:
                        return child

            # 2) Exact match di level kecamatan (2 titik)
            async with db.execute(
                "SELECT kode FROM wilayah "
                "WHERE UPPER(nama) = ? AND LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 2 "
                "LIMIT 1",
                (q_upper,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    child = await _first_child(row["kode"])
                    if child:
                        return child

            # 3) Exact match di level desa (3 titik)
            async with db.execute(
                "SELECT kode FROM wilayah "
                "WHERE UPPER(nama) = ? AND LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 3 "
                "LIMIT 1",
                (q_upper,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    return row["kode"]

            # 4) Fuzzy LIKE → prioritaskan kota, kabupaten, kecamatan, lalu desa
            async with db.execute(
                "SELECT kode, nama FROM wilayah "
                "WHERE UPPER(nama) LIKE ? "
                "ORDER BY "
                "  CASE "
                "    WHEN UPPER(nama) LIKE 'KOTA %' THEN 1 "
                "    WHEN UPPER(nama) LIKE 'KABUPATEN %' THEN 2 "
                "    WHEN LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 1 THEN 3 "
                "    WHEN LENGTH(kode) - LENGTH(REPLACE(kode,'.','')) = 2 THEN 4 "
                "    ELSE 5 "
                "  END, "
                "LENGTH(kode) ASC "
                "LIMIT 30",
                (f"%{q_upper}%",),
            ) as cur:
                rows = await cur.fetchall()

            if not rows:
                return None

            # Kelompokkan berdasarkan level — ambil yang paling tinggi (paling spesifik)
            adm4 = [r for r in rows if _count_dots(r["kode"]) == 3]  # desa
            adm3 = [r for r in rows if _count_dots(r["kode"]) == 2]  # kecamatan
            adm2 = [r for r in rows if _count_dots(r["kode"]) == 1]  # kota/kab

            # Prioritaskan: desa (sudah adm4) → kecamatan (cari child) → kota (cari child)
            if adm4:
                return adm4[0]["kode"]
            elif adm3:
                child = await _first_child(adm3[0]["kode"])
                if child:
                    return child
            elif adm2:
                child = await _first_child(adm2[0]["kode"])
                if child:
                    return child

            return None  # Gagal semua

    except Exception as e:
        logger.error(f"[Cuaca] Error query wilayah.db: {e}")
        return None


# ---------------------------------------------------------------------------
# BMKGClient
# ---------------------------------------------------------------------------

class BMKGClient:
    """Klien async untuk mengambil data cuaca dari API BMKG."""

    def __init__(self):
        self._db_ready: Optional[bool] = None   # None = belum dicek
        self._session: Optional[aiohttp.ClientSession] = None

    async def close(self):
        """Tutup session aiohttp jika masih terbuka."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_db(self) -> bool:
        """Pastikan wilayah.db siap (lazy init)."""
        if self._db_ready is None:
            self._db_ready = await ensure_wilayah_db()
        return self._db_ready

    async def _get_json(self, url: str, **kwargs) -> Optional[Dict]:
        """GET JSON via aiohttp dengan timeout."""
        timeout = aiohttp.ClientTimeout(total=10)
        # Session di-reuse untuk performa lebih baik
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=timeout, auto_decompress=False)
        try:
            async with self._session.get(url, **kwargs) as resp:
                if resp.status != 200:
                    logger.error(f"[BMKG] HTTP {resp.status} untuk {url}")
                    return None
                raw = await resp.read()
                encoding = resp.headers.get("Content-Encoding", "")
                if encoding == "br":
                    if not _HAS_BROTLI:
                        logger.warning("[BMKG] Brotli tidak terinstal, coba dekompresi aiohttp fallback...")
                        # Fallback: buat session baru dengan auto_decompress=True
                        async with aiohttp.ClientSession(timeout=timeout) as s2:
                            async with s2.get(url, **kwargs) as resp2:
                                raw = await resp2.read()
                    else:
                        raw = brotli.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except asyncio.TimeoutError:
            logger.error(f"[BMKG] Timeout saat akses {url}")
            return None
        except Exception as e:
            logger.error(f"[BMKG] Error GET {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_location_code(self, query: str) -> Optional[str]:
        """
        Mencari kode adm4 BMKG berdasarkan nama lokasi.

        Urutan prioritas:
        1. Fallback statis (_CITY_FALLBACK) untuk kota populer → cepat
        2. Query ke wilayah.db via aiosqlite → akurat & lengkap
        3. DEFAULT_ADM4 (Jakarta Pusat) jika semua gagal

        FIXED: Fallback statis sekarang mencakup 50+ kota + alias.
               Pencarian DB tidak lagi mengembalikan kode non-adm4.
        """
        if not query:
            return DEFAULT_ADM4

        q_upper = query.strip().upper()

        # 1) Cek fallback statis — cocokkan EXACT atau sebagai kata utuh
        #    Agar "BANDUNG" tidak false-match dengan "CIBANDUNG"
        for city, code in _CITY_FALLBACK.items():
            if q_upper == city:
                logger.debug(f"[Cuaca] Fallback exact: {city} → {code}")
                return code
            # Juga cek jika query mengandung nama kota sebagai kata terpisah
            if f" {city} " in f" {q_upper} " or q_upper.startswith(f"{city} ") or q_upper.endswith(f" {city}"):
                logger.debug(f"[Cuaca] Fallback fuzzy: {city} in {q_upper} → {code}")
                return code

        # 2) Query DB
        await self._ensure_db()
        if self._db_ready:
            code = await _search_db(q_upper)
            if code:
                logger.info(f"[Cuaca] DB match: '{query}' → {code}")
                return code

        # 3) Default
        logger.warning(f"[Cuaca] Lokasi '{query}' tidak ditemukan, pakai default.")
        return DEFAULT_ADM4

    async def get_weather_raw(self, adm4: str = DEFAULT_ADM4) -> Optional[Dict[str, Any]]:
        """Mengambil data mentah prakiraan cuaca dari BMKG."""
        data = await self._get_json(BMKG_API_URL, params={"adm4": adm4})
        if not data or "data" not in data or not data["data"]:
            return None

        location_info = data.get("lokasi", {})
        weather_list  = data["data"][0].get("cuaca", [])
        if not weather_list:
            return None

        # Ambil 3 slot prakiraan terdekat (tiap slot = list, ambil elemen pertama)
        forecasts: list = []
        for slot in weather_list[:3]:
            if isinstance(slot, list) and slot:
                forecasts.append(slot[0])
            elif isinstance(slot, dict):
                forecasts.append(slot)

        if not forecasts:
            return None

        return {
            "lokasi": {
                "desa"      : location_info.get("desa"),
                "kecamatan" : location_info.get("kecamatan"),
                "kotkab"    : location_info.get("kotkab"),
                "provinsi"  : location_info.get("provinsi"),
            },
            "prakiraan": forecasts,
            "sumber"   : "BMKG",
        }

    def extract_location_from_text(self, text: str) -> Optional[str]:
        """Ekstrak nama lokasi dari teks natural language."""
        # Kata yang TIDAK boleh jadi bagian nama lokasi (stop-words).
        _STOP_PAT = (
            r"hari\s+ini|besok|sekarang|malam\s+ini|minggu\s+ini"
            r"|gimana|berapa|nggak|tidak|enggak|ga\b|gak\b"
            r"|cuaca|cuacanya|dong|yuk|ya\b|nih|deh"
        )

        # _LOC mencocokkan 1 atau lebih kata nama tempat
        _WORD = (
            r"(?!(?:" + _STOP_PAT + r")(?:\s|$))"
            r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF][A-Za-z\u00C0-\u024F\u1E00-\u1EFF\-]*"
        )
        _LOC = rf"{_WORD}(?:[\s']{_WORD})*"

        # Kata kondisi cuaca
        _COND = r"(?:cuaca|hujan|ujan|panas|mendung|gerimis|cerah|suhu|dingin|angin|berawan|lembab|prakiraan|badai)"

        _TIME = r"(?:\s+(?:hari\s+ini|besok|sekarang|malam\s+ini|minggu\s+ini))?"
        _TAIL = r"\s*\??\s*$"

        patterns = [
            # 1. "[kondisi] di/ke/wilayah/daerah [lokasi] [waktu]?"
            rf"{_COND}\s+(?:di|ke|wilayah|daerah)\s+({_LOC}){_TIME}{_TAIL}",
            # 2. "bagaimana/gimana/kayak gimana cuaca (di) [lokasi] [waktu]?"
            rf"(?:bagaimana|gimana|kayak\s+gimana)\s+cuaca\s+(?:di\s+)?({_LOC}){_TIME}{_TAIL}",
            # 3. "cek/lihat/info/infokan/tanya/tampilkan cuaca (di) [lokasi] [waktu]"
            rf"(?:cek|lihat|info|infokan|tanya|tampilkan)\s+cuaca\s+(?:di\s+)?({_LOC}){_TIME}{_TAIL}",
            # 4. "cuaca [lokasi] [gimana/hari ini/besok/?]"
            rf"cuaca\s+({_LOC})(?:\s+(?:hari\s+ini|besok|gimana|sekarang|malam\s+ini))?\s*\??\s*$",
            # 5. "prakiraan cuaca (di) [lokasi] [waktu]?"
            rf"prakiraan\s+cuaca\s+(?:di\s+)?({_LOC}){_TIME}{_TAIL}",
            # 6. "[hujan/panas] nggak/tidak/ga/gak/enggak (di) [lokasi] [waktu]?"
            rf"(?:hujan|ujan|panas)\s+(?:nggak|tidak|ga|gak|enggak)\s+(?:di\s+)?({_LOC}){_TIME}{_TAIL}",
            # 7. "(apa) bakal/akan/mau [hujan/panas] (di) [lokasi] [waktu]?"
            rf"(?:apa\s+)?(?:bakal|akan|mau)\s+(?:hujan|ujan|panas)\s+(?:di\s+)?({_LOC}){_TIME}{_TAIL}",
            # 8. "suhu (di) [lokasi] berapa?"
            rf"suhu\s+(?:di\s+)?({_LOC})\s+berapa{_TAIL}",
            # 9. "berapa suhu/temperatur (di) [lokasi] [waktu]?"
            rf"berapa\s+(?:suhu|temperatur|temperature)\s+(?:di\s+)?({_LOC}){_TIME}{_TAIL}",
            # 10. "[lokasi] hujan/panas nggak [waktu]?"
            rf"({_LOC})\s+(?:hujan|ujan|panas)\s+(?:nggak|tidak|ga|gak|enggak){_TIME}{_TAIL}",
            # 11. "[lokasi] cuaca [gimana/hari ini/besok]?"
            rf"({_LOC})\s+cuaca(?:\s+(?:gimana|hari\s+ini|besok|sekarang))?\s*\??\s*$",
            # 12. "mau/pergi/berangkat ke [lokasi] cuaca/cuacanya [gimana]?"
            rf"(?:mau|pergi|berangkat)\s+ke\s+({_LOC})[\s,]+(?:cuaca|cuacanya){_TAIL}",
        ]

        # Kata yang tidak dianggap nama lokasi (fallback cek setelah regex)
        _SKIP = {
            "hari ini", "besok", "sekarang", "malam ini", "minggu ini",
            "yuk", "saja", "gimana", "dong", "ya", "nih", "deh",
            "aku", "kamu", "kita", "sini", "sana",
        }

        for pat in patterns:
            m = re.search(pat, text.strip(), re.IGNORECASE)
            if m:
                loc = m.group(1).strip()
                if loc.lower() in _SKIP or not loc:
                    continue
                return loc
        return None


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _main():
        client = BMKGClient()
        queries = [
            "Gimana cuaca di Bandung hari ini?",
            "cuaca di Kemayoran",
            "cek cuaca Surabaya",
            "cuaca Malang",
            "cuaca Solo",
            "cuaca di Jogja",
            "cuaca Makassar",
            "cuaca Pekanbaru",
        ]
        for q in queries:
            loc = client.extract_location_from_text(q)
            print(f"\nQuery   : {q}")
            print(f"Lokasi  : {loc}")
            if loc:
                code = await client.search_location_code(loc)
                print(f"Kode ADM: {code}")
                raw = await client.get_weather_raw(code)
                if raw:
                    print(f"Lokasi  : {raw['lokasi']}")
                else:
                    print(f"Lokasi  : None (data tidak tersedia)")

    asyncio.run(_main())
