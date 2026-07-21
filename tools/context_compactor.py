import os
from groq import AsyncGroq
from typing import List, Dict
from config import COMPACTION_MODEL
from utils.logger import setup_logging

logger = setup_logging()

class ContextCompactor:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("[Compactor] GROQ_API_KEY tidak ditemukan. Fitur kompaksi dinonaktifkan.")
            self.client = None
        else:
            self.client = AsyncGroq(api_key=api_key)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def compact(self, history: List[Dict], existing_context: str = "") -> str:
        if not self.client:
            return ""

        messages_text = self._format_history(history)
        if not messages_text.strip():
            return ""

        if existing_context:
            prompt = (
                "Kamu adalah perangkum percakapan yang handal dan cermat.\n\n"
                "Tugasmu: Perbarui ringkasan percakapan berikut dengan informasi baru.\n"
                "Fokus pada:\n"
                "1. Topik utama yang dibahas\n"
                "2. Mood atau emosi lawan bicara\n"
                "3. Informasi penting, keputusan, atau fakta yang disebutkan\n"
                "4. Hal-hal yang perlu diingat untuk kelanjutan percakapan\n\n"
                "Ringkasan sebelumnya:\n"
                f"{existing_context}\n\n"
                "Percakapan baru:\n"
                f"{messages_text}\n\n"
                "Buat ringkasan 3-5 kalimat dalam Bahasa Indonesia yang padat dan informatif. "
                "Gabungkan informasi dari ringkasan sebelumnya dengan percakapan baru. "
                "Hapus detail yang sudah tidak relevan, pertahankan yang penting."
            )
        else:
            prompt = (
                "Kamu adalah perangkum percakapan yang handal dan cermat.\n\n"
                "Tugasmu: Ringkas percakapan berikut dengan fokus pada:\n"
                "1. Topik utama yang dibahas\n"
                "2. Mood atau emosi lawan bicara\n"
                "3. Informasi penting, keputusan, atau fakta yang disebutkan\n"
                "4. Hal-hal yang perlu diingat untuk kelanjutan percakapan\n\n"
                "Percakapan:\n"
                f"{messages_text}\n\n"
                "Buat ringkasan 3-5 kalimat dalam Bahasa Indonesia yang padat dan informatif. "
                "Fokus pada informasi yang relevan untuk kelanjutan percakapan."
            )

        try:
            completion = await self.client.chat.completions.create(
                model=COMPACTION_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )

            if not completion.choices:
                logger.warning("[Compactor] Groq return 0 choices")
                return ""

            content = completion.choices[0].message.content
            if not content or not content.strip():
                logger.warning("[Compactor] Groq return konten kosong")
                return ""

            logger.info(f"[Compactor] Kompaksi berhasil ({len(content)} chars)")
            return content.strip()

        except Exception as e:
            logger.error(f"[Compactor] Gagal kompaksi: {e}")
            return ""

    def _format_history(self, history: List[Dict]) -> str:
        lines = []
        for msg in history:
            role = msg.get("role", "unknown")
            if role == "model":
                label = "Mirai"
            else:
                label = "User"

            parts = msg.get("parts", [])
            text = ""
            for part in parts:
                if isinstance(part, dict):
                    if "text" in part:
                        text = part["text"]
                        break
                    if "functionCall" in part:
                        text = f"[FunctionCall: {part['functionCall'].get('name', 'unknown')}]"
                        break
                    if "functionResponse" in part:
                        text = f"[FunctionResponse: {part['functionResponse'].get('name', 'unknown')}]"
                        break
                else:
                    text = str(part)
                    break

            if text:
                lines.append(f"{label}: {text[:500]}")

        return "\n".join(lines)
