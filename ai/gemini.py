# ai/gemini.py
"""Klien async untuk Google Gemini dengan Function Calling.

Fitur utama:
- Gemini native function calling (tool calling) untuk weather, search
- Deterministic URL detection (webpage + YouTube) tanpa LLM
- 2-turn flow: Turn 1 → functionCall detection → execute → Turn 2
- Semaphore (max 3 concurrent requests)
- Circuit‑breaker (threshold 5×503, cooldown 30 s)
- Cache TTL 5 menit
- Rotasi API‑key dengan cooldown per key
- Dynamic temperature (lebih rendah untuk pertanyaan faktual)
"""

import os
import re
import json
import copy
import time
import asyncio
import aiohttp
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional, Tuple
from ai.time import get_wib_time, get_wib_time_str
from ai.cuaca import BMKGClient
from ai.web_scraper import BrowserlessClient
from ai.youtube_transcript import YouTubeTranscriptClient
from ai.web_search import WebSearchClient
from core.module_manager import module_manager
from ai.tool_definitions import get_active_tools
from ai.tool_executor import ToolExecutor
from config import (
    GEMINI_MODEL,
    GEMINI_API_VERSION,
    TEMPERATURE,
    MAX_OUTPUT_TOKENS,
    TOP_P,
    REQUEST_TIMEOUT,
    KEY_COOLDOWN_DURATION,
)
from utils.logger import setup_logging

load_dotenv()
logger = setup_logging()

# ----------------------------------------------------------------------
# 1️⃣  System prompt
# ----------------------------------------------------------------------
BASE_URL = f"https://generativelanguage.googleapis.com/{GEMINI_API_VERSION}/models"
PROMPT_PATH = Path(__file__).parent / "prompts" / "mirai_system_prompt.txt"

def _load_system_prompt() -> str:
    """Load system prompt from file with fallback."""
    if PROMPT_PATH.exists():
        try:
            txt = PROMPT_PATH.read_text(encoding="utf-8").strip()
            if txt:
                logger.info("[Gemini] Loaded system prompt from %s", PROMPT_PATH)
                return txt
        except Exception as e:
            logger.exception("[Gemini] Gagal baca system prompt: %s", e)
    
    logger.warning("[Gemini] Fallback system prompt (minimal).")
    return (
        "Kamu adalah Mirai, asisten kesehatan dan pendamping emosional. "
        "Dewasa, ramah, peka, profesional. Tidak memberi diagnosis atau resep. "
        "Gaya bicara semi‑informal Jakarta, hangat, sesekali keibuan."
    )

SYSTEM_PROMPT = _load_system_prompt()

# ----------------------------------------------------------------------
# 2️⃣  Circuit‑breaker & semaphore
# ----------------------------------------------------------------------
_gemini_semaphore = asyncio.Semaphore(3)
_circuit_breaker_until = 0
_circuit_breaker_failures = 0
_circuit_breaker_lock = asyncio.Lock()  # FIXED: Added lock for thread safety
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN = 30

async def _increase_503_counter():
    """Increase 503 failure counter with thread safety."""
    global _circuit_breaker_failures, _circuit_breaker_until
    async with _circuit_breaker_lock:
        _circuit_breaker_failures += 1
        if _circuit_breaker_failures >= CIRCUIT_BREAKER_THRESHOLD:
            _circuit_breaker_until = time.time() + CIRCUIT_BREAKER_COOLDOWN
            logger.critical(
                f"[CircuitBreaker] Aktif! Istirahat {CIRCUIT_BREAKER_COOLDOWN}s karena "
                f"{_circuit_breaker_failures}x 503 berturut‑turut."
            )

async def _reset_503_counter():
    """Reset 503 failure counter with thread safety."""
    global _circuit_breaker_failures
    async with _circuit_breaker_lock:
        _circuit_breaker_failures = 0

async def _is_circuit_breaker_active() -> bool:
    """Check if circuit breaker is currently active with lock safety."""
    async with _circuit_breaker_lock:
        return time.time() < _circuit_breaker_until

# ----------------------------------------------------------------------
# 3️⃣  GeminiClient (async)
# ----------------------------------------------------------------------
class GeminiClient:
    """Async client for Google Gemini API with advanced features."""
    
    def __init__(self):
        raw_keys = os.getenv("GEMINI_KEYS", "")
        self.api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        if not self.api_keys:
            raise ValueError("❌ Tidak ada GEMINI_KEYS di .env!")
        self.key_index = 0
        self.api_key = self.api_keys[0]
        self.endpoint = f"{BASE_URL}/{GEMINI_MODEL}:generateContent"
        self.bmkg = BMKGClient()
        self.web_scraper = BrowserlessClient()
        self.youtube_transcript = YouTubeTranscriptClient()
        self.web_search = WebSearchClient()
        self.system_prompt = SYSTEM_PROMPT
        self._tool_executor: Optional[ToolExecutor] = None
        self._cache = {}
        self._CACHE_TTL = 300
        self._KEY_COOLDOWN = {}
        self._cache_lock = asyncio.Lock()
        logger.info(f"[Gemini] Initialized with {len(self.api_keys)} API key(s)")
        logger.info("[Gemini] Function calling mode: active (weather, search via tool calling)")

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _make_cache_key(self, history: List[Dict], user_context: str, temperature: float, tools_state: str = "") -> int:
        """Create cache key from request parameters.
        Includes tools_state to invalidate cache when modules are toggled.
        """
        try:
            payload = json.dumps(
                {"h": history, "c": user_context, "t": temperature, "ts": tools_state},
                sort_keys=True
            )
            return hash(payload)
        except Exception as e:
            logger.warning(f"[Gemini] Failed to create cache key: {e}")
            return hash(str(time.time()))  # Fallback to time-based key

    async def _get_cached(self, key: int) -> Optional[str]:
        """Get cached response if still valid."""
        async with self._cache_lock:
            entry = self._cache.get(key)
            if entry:
                ts, val = entry
                if time.time() - ts < self._CACHE_TTL:
                    logger.debug("[Gemini] Cache hit")
                    return val
                # Expired cache entry
                self._cache.pop(key, None)
        return None

    async def _set_cached(self, key: int, val: str):
        """Store response in cache."""
        async with self._cache_lock:
            self._cache[key] = (time.time(), val)
            # FIXED: Clean old cache entries to prevent memory leak
            if len(self._cache) > 100:
                await self._clean_old_cache()

    async def _clean_old_cache(self):
        """Remove expired cache entries."""
        now = time.time()
        expired_keys = [
            k for k, (ts, _) in self._cache.items() 
            if now - ts >= self._CACHE_TTL
        ]
        for k in expired_keys:
            self._cache.pop(k, None)
        logger.debug(f"[Gemini] Cleaned {len(expired_keys)} expired cache entries")

    # ------------------------------------------------------------------
    # Simple fallback (jam / tanggal)
    # ------------------------------------------------------------------
    def _simple_response(self, history: List[Dict], user_context: str) -> Optional[str]:
        """Provide simple responses for time/date queries without API call."""
        search_noise = [
            "cari", "carikan", "berita", "info", "kabar", "update",
            "search", "google", "riset", "research", "trending",
            "tentang", "soal", "mengenai", "terkait",
        ]

        for msg in reversed(history):
            if msg.get("role") == "user":
                txt = self._extract_text_from_message(msg)
                txt_lower = txt.lower()

                if any(kw in txt_lower for kw in search_noise):
                    break

                if "jam" in txt_lower and "berapa" in txt_lower:
                    return f"Sekarang jam {get_wib_time().strftime('%H:%M')} WIB."
                if "tanggal" in txt_lower and ("berapa" in txt_lower or "hari ini" in txt_lower):
                    return f"Hari ini tanggal {get_wib_time().strftime('%d-%m-%Y')} WIB."
                break
        return None

    def _extract_text_from_message(self, msg: Dict) -> str:
        """Extract text content from message dict."""
        if "parts" in msg and isinstance(msg["parts"], list) and msg["parts"]:
            part = msg["parts"][0]
            raw = part.get("text", "") if isinstance(part, dict) else str(part)
            return raw
        return msg.get("content", "")

    def _extract_user_message_only(self, raw: str) -> str:
        """Extract just the 'Message: ' portion from wrapped metadata message.
        
        handle() wraps messages with metadata (nama, channel, dll).
        URL/keyword detection needs to run on the actual user message only.
        Stops at attachment section if present.
        """
        match = re.search(r"^Message:\s*(.*?)(?:\n\n\[|\Z)", raw, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r"^Message:\s*(.*)", raw, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return raw

    # ------------------------------------------------------------------
    # Dynamic temperature
    # ------------------------------------------------------------------
    def _smart_temperature(self, history: List[Dict]) -> float:
        """Adjust temperature based on query type."""
        for msg in reversed(history):
            if msg.get("role") == "user":
                txt = self._extract_text_from_message(msg).lower()
                
                # Lower temperature for factual questions
                factual_keywords = ["apa", "siapa", "berapa", "kapan", "jam", "tanggal", "dimana", "mengapa"]
                if any(kw in txt for kw in factual_keywords):
                    return 0.3
                break
        return TEMPERATURE

    # ------------------------------------------------------------------
    # Webpage context (Browserless)
    # ------------------------------------------------------------------
    async def _get_webpage_context(self, user_message: str) -> str:
        """
        Deteksi URL dalam pesan user, scrap via Browserless, return konteks.
        Mirip pola _get_weather_context().
        """
        if not self.web_scraper.enabled:
            return ""

        # Ekstrak URL dari pesan (pakai clean message, buang metadata wrapper)
        clean_msg = self._extract_user_message_only(user_message)
        urls = self.web_scraper.extract_urls(clean_msg)
        if not urls:
            return ""

        # Ambil URL pertama saja (untuk sekarang)
        url = urls[0]

        try:
            content = await self.web_scraper.scrape_url(url)
            if not content:
                return ""

            ctx = (
                f"\n\n[KONTEN WEBSITE: {url}]\n"
                f"{content}\n"
                "\n⚠️ INSTRUKSI: Konten di atas adalah data REAL dari website yang user kirim. "
                "Gunakan data ini untuk menjawab pertanyaan user tentang website tersebut. "
                "Jangan bilang kamu tidak punya akses ke website — karena data sudah tersedia di atas. "
                "Jawab dengan gaya ramah Mirai dan berikan ringkasan informatif."
            )
            return ctx
        except Exception as e:
            logger.warning(f"[Gemini] Failed to get webpage context: {e}")
            return ""

    # ------------------------------------------------------------------
    # Deterministic URL context (webpage only)
    # ------------------------------------------------------------------
    async def _detect_and_fetch_url_context(self, user_message: str) -> str:
        """
        Regex-detect webpage URLs and fetch context deterministically.
        YouTube transcript is now handled via function calling, not pre-fetch.
        """
        if module_manager.is_enabled("web_scraper"):
            web_ctx = await self._get_webpage_context(user_message)
            if web_ctx:
                return web_ctx

        return ""

    # ------------------------------------------------------------------
    # Build payload (system instruction + contents)
    # ------------------------------------------------------------------
    async    def _build_payload(
        self,
        history: List[Dict],
        temperature: float,
        user_context: str,
        url_context: str = "",
        tools: list[dict] | None = None,
    ) -> Dict:
        """Build API request payload.

        Args:
            history: Conversation history messages.
            temperature: Sampling temperature.
            user_context: Micro-RAG user profile context.
            url_context: Pre-fetched webpage/youtube context (deterministic).
            tools: Gemini function declarations (only enabled modules).
        """
        full_system = (
            self.system_prompt +
            f"\n\nInformasi waktu saat ini: {get_wib_time_str()}\n" +
            url_context +
            user_context
        )
        system_instruction = {"parts": [{"text": full_system}]}

        trimmed = history[-6:] if isinstance(history, list) else []
        contents = []

        for msg in trimmed:
            role = msg.get("role")
            if role == "assistant":
                role = "model"

            parts = msg.get("parts", [])
            if parts:
                # Pass through ALL parts (text, functionCall, functionResponse)
                contents.append({"role": role, "parts": parts})
            else:
                text = msg.get("content", "")
                if text:
                    contents.append({"role": role, "parts": [{"text": text}]})

        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Halo"}]})

        payload = {
            "system_instruction": system_instruction,
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "topP": TOP_P,
            },
        }

        if tools:
            payload["tools"] = tools

        return payload

    # ------------------------------------------------------------------
    # API request with retry logic
    # ------------------------------------------------------------------
    async def _make_api_request(
        self,
        payload: Dict,
        attempt: int
    ) -> Tuple[bool, Optional[dict]]:
        """
        Make API request with current key.

        Returns:
            (success, response_dict) where response_dict is:
              {"type": "text", "text": "..."}          — plain text response
              {"type": "functionCall", "name": ..., "args": ...}  — tool call
        """
        if (
            self.api_key in self._KEY_COOLDOWN and
            time.time() < self._KEY_COOLDOWN[self.api_key]
        ):
            return False, None

        params = {"key": self.api_key}

        try:
            async with _gemini_semaphore:
                timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                async with aiohttp.ClientSession(timeout=timeout) as sess:
                    async with sess.post(
                        self.endpoint,
                        params=params,
                        json=payload,
                    ) as resp:
                        if resp.status == 503:
                            await _increase_503_counter()
                            logger.warning(f"[Gemini] 503 error with key #{self.key_index+1}")
                            await asyncio.sleep(min(2 ** attempt, 60))
                            return False, None

                        if 400 <= resp.status < 500:
                            txt = await resp.text()
                            logger.error(f"[Gemini] Client error {resp.status}: {txt}")
                            return False, None

                        if resp.status >= 500:
                            txt = await resp.text()
                            logger.error(f"[Gemini] Server error {resp.status}: {txt}")
                            return False, None

                        data = await resp.json()
                        await _reset_503_counter()

                        candidates = data.get("candidates", [])
                        if not candidates:
                            return True, {"type": "text", "text": "[Gemini] Tidak ada kandidat."}

                        parts = candidates[0].get("content", {}).get("parts", [])
                        if not parts:
                            return True, {"type": "text", "text": "[Gemini] Response kosong."}

                        for part in parts:
                            if "functionCall" in part:
                                fc = part["functionCall"]
                                return True, {
                                    "type": "functionCall",
                                    "name": fc.get("name", ""),
                                    "args": fc.get("args", {}),
                                }

                        text = "".join(p.get("text", "") for p in parts).strip()
                        return True, {"type": "text", "text": text}

        except asyncio.TimeoutError:
            logger.warning(f"[Gemini] Timeout dengan key #{self.key_index+1}")
            self._KEY_COOLDOWN[self.api_key] = time.time() + KEY_COOLDOWN_DURATION
            return False, None
        except Exception as e:
            logger.warning(f"[Gemini] Error dengan key #{self.key_index+1}: {e}")
            self._KEY_COOLDOWN[self.api_key] = time.time() + KEY_COOLDOWN_DURATION
            return False, None

    async def _rotate_to_next_key(self):
        """Rotate to the next available API key, menunggu cooldown bila diperlukan."""
        self.key_index = (self.key_index + 1) % len(self.api_keys)
        self.api_key = self.api_keys[self.key_index]
        # Jika key baru masih dalam cooldown, tunggu hingga tersedia
        if self.api_key in self._KEY_COOLDOWN:
            wait = max(0, self._KEY_COOLDOWN[self.api_key] - time.time())
            if wait:
                logger.info(f"[Gemini] Menunggu {wait:.1f}s untuk key selanjutnya")
                await asyncio.sleep(wait)

    # ------------------------------------------------------------------
    # Helper: try all keys with retry
    # ------------------------------------------------------------------
    async def _try_all_keys(self, payload: Dict) -> Optional[dict]:
        """Try all API keys with retry logic. Returns response dict or None."""
        attempts = 0
        max_attempts = len(self.api_keys) * 2

        while attempts < max_attempts:
            success, response = await self._make_api_request(payload, attempts)
            if success and response:
                return response
            await self._rotate_to_next_key()
            attempts += 1

        await _increase_503_counter()
        logger.error("[Gemini] Semua API key gagal setelah semua attempts")
        return None

    # ------------------------------------------------------------------
    # Helper: build Turn 2 payload with function response
    # ------------------------------------------------------------------
    @staticmethod
    def _build_turn2_payload(
        original_payload: Dict,
        function_call: dict,
        function_response: dict,
    ) -> Dict:
        """Append functionCall + functionResponse to contents, remove tools."""
        payload = copy.deepcopy(original_payload)

        payload["contents"].append({
            "role": "model",
            "parts": [{"functionCall": {
                "name": function_call["name"],
                "args": function_call["args"],
            }}],
        })

        payload["contents"].append({
            "role": "user",
            "parts": [{"functionResponse": {
                "name": function_response["name"],
                "response": function_response["response"],
            }}],
        })

        payload.pop("tools", None)
        return payload

    # ------------------------------------------------------------------
    # Helper: fallback text when Turn 2 fails
    # ------------------------------------------------------------------
    @staticmethod
    def _format_tool_fallback(function_call: dict, function_response: dict) -> str:
        """Format a human-readable fallback when Turn 2 API call fails."""
        name = function_call.get("name", "tool")
        resp = function_response.get("response", {})
        if isinstance(resp, dict) and resp.get("error"):
            return f"Hmm, sepertinya {name} gagal: {resp['error']}. Coba lagi nanti ya."
        return f"Data dari {name} berhasil diambil tapi aku gagal memproses jawabannya. Coba tanya lagi ya."

    # ------------------------------------------------------------------
    # Public async generate (2-turn function calling flow)
    # ------------------------------------------------------------------
    async def generate(
        self,
        history: List[Dict],
        temperature: float = TEMPERATURE,
        user_context: str = "",
    ) -> str:
        """
        Generate AI response with optional function calling.

        Flow:
          1. Detect URLs deterministically (webpage/youtube)
          2. Get active tools from module manager
          3. Turn 1: POST to Gemini with tools[]
          4. If text → done (1 API call)
          5. If functionCall → execute tool → Turn 2 → done (2 API calls)
        """
        if await _is_circuit_breaker_active():
            logger.warning("[Gemini] Circuit breaker active, request blocked")
            return "[Gemini] Service overload, coba lagi nanti."

        quick = self._simple_response(history, user_context)
        if quick:
            logger.debug("[Gemini] Using quick response")
            return quick

        dyn_temp = self._smart_temperature(history)

        # Step 1: Get active tools FIRST (cheap — dict lookup)
        # Include tools_state in cache key so module toggle invalidates cache
        tools = get_active_tools()
        tools_state = ""
        if tools:
            tool_names = [d["name"] for d in tools[0].get("functionDeclarations", [])]
            tools_state = ",".join(sorted(tool_names))
            logger.info("[Gemini] Active tools: %s", tools_state)
        else:
            logger.debug("[Gemini] No semantic tools active (pure text mode)")

        cache_key = self._make_cache_key(history, user_context, dyn_temp, tools_state)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        # Step 2: Deterministic URL detection
        last_msg = ""
        if history and history[-1].get("role") == "user":
            last_msg = self._extract_text_from_message(history[-1])

        url_context = await self._detect_and_fetch_url_context(last_msg)
        if url_context:
            logger.info("[Gemini] URL context detected (%d chars)", len(url_context))

        # Step 3: Build payload
        payload = await self._build_payload(
            history, dyn_temp, user_context,
            url_context=url_context,
            tools=tools,
        )

        # Step 4: Turn 1
        logger.debug("[Gemini] Turn 1: sending to API...")
        turn1 = await self._try_all_keys(payload)
        if not turn1:
            return "[Gemini] Semua API key gagal, silakan coba lagi nanti."

        # Step 5: Check response type
        if turn1["type"] == "text":
            logger.info("[Gemini] Turn 1 → text (single call, no tool needed)")
            text = turn1.get("text", "")
            if text:
                await self._set_cached(cache_key, text)
            return text or "[Gemini] Response kosong."

        # Step 6: Function call — execute tool
        if turn1["type"] == "functionCall":
            fc_name = turn1.get("name", "")
            fc_args = turn1.get("args", {})
            logger.info("[Gemini] Turn 1 → functionCall: %s(%s)", fc_name, fc_args)

            if self._tool_executor is None:
                self._tool_executor = ToolExecutor(self)

            function_response = await self._tool_executor.execute({
                "name": fc_name,
                "args": fc_args,
            })

            # Step 7: Turn 2
            turn2_payload = self._build_turn2_payload(
                payload,
                {"name": fc_name, "args": fc_args},
                function_response,
            )

            turn2 = await self._try_all_keys(turn2_payload)

            if turn2 and turn2["type"] == "text":
                text = turn2.get("text", "")
                logger.info("[Gemini] Turn 2 → text (tool result processed)")
                if text:
                    await self._set_cached(cache_key, text)
                return text or "[Gemini] Response kosong."

            logger.warning("[Gemini] Turn 2 failed, using fallback")
            return self._format_tool_fallback(
                {"name": fc_name, "args": fc_args},
                function_response,
            )

        return "[Gemini] Response tidak dikenali."

    # ------------------------------------------------------------------
    # Convenience async methods
    # ------------------------------------------------------------------
    async def generate_welcome(self, user_name: str) -> str:
        """Generate welcome message for new member."""
        prompt = (
            f"Buatkan pesan sambutan hangat, ramah, dan sedikit puitis untuk member baru "
            f"bernama '{user_name}' yang baru bergabung di server Helix. "
            "Gunakan gaya bicara Mirai (dewasa, empati, semi‑informal Jakarta). "
            "Maksimal 3 kalimat."
        )
        return await self.generate([{"role": "user", "parts": [{"text": prompt}]}])

    async def generate_goodbye(self, user_name: str) -> str:
        """Generate goodbye message for leaving member."""
        prompt = (
            f"Buatkan pesan perpisahan menyentuh dan penuh doa untuk member "
            f"bernama '{user_name}' yang meninggalkan server Helix. "
            "Gunakan gaya Mirai (dewasa, empati, hangat). "
            "Maksimal 3 kalimat."
        )
        return await self.generate([{"role": "user", "parts": [{"text": prompt}]}])

# ----------------------------------------------------------------------
# Test block (debug)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    async def _test():
        client = GeminiClient()
        res = await client.generate([{"role": "user", "content": "Halo"}])
        print(res)
    asyncio.run(_test())