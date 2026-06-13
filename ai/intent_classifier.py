"""
ai/intent_classifier.py — Intent Classifier untuk Search
────────────────────────────────────────────────────────
Mengklasifikasikan niat user: apakah pesannya butuh pencarian web atau tidak.

Menggunakan keyword matching yang diperluas + negative triggers sebagai fallback.
Bisa di-upgrade ke AI-based classifier di masa depan.
"""

from typing import Dict, Optional
from utils.logger import setup_logging

logger = setup_logging()


SEARCH_TRIGGERS = [
    "cari", "search", "google", "cariin", "carikan",
    "info terbaru", "berita terbaru", "update terbaru",
    "trending", "riset", "research",
    "rekomendasi", "review", "ulasan", "perbandingan", "bandingin",
    "mana yang", "lebih bagus", "yang terbaik", "daftar", "list",
    "harga", "beli dimana", "tips", "cara", "tutorial",
    "alternatif", "pengganti", "mirip", "kompetitor",
    "update", "perkembangan", "berita", "kabar terbaru",
    "boleh tahu", "ada yang tahu", "tolong cari",
    "bisa cari", "ada info", "kasih tahu", "jelasin",
]

QUESTION_WORDS = [
    "siapa", "apa itu", "kapan", "dimana", "mengapa",
    "bagaimana", "jelaskan tentang", "ceritakan tentang",
    "apa kabar", "berapa", "mana",
]

NEGATIVE_TRIGGERS = [
    "cari perhatian", "cari muka", "cari masalah",
    "cari mati", "cari perkara", "cari ribut",
    "cari teman", "cari pacar", "cari gebetan",
    "cari makan", "cari makan malam", "cari makan siang",
    "jangan cari", "gak usah cari", "nggak usah cari",
]


class IntentClassifier:
    """
    Klasifikasi intent user message.

    Return:
        {
            "intent": "search" | "chat",
            "confidence": 0.0-1.0,
            "reason": str
        }
    """

    def classify(self, message: str, conversation_history: Optional[list] = None) -> Dict:
        if not message or not message.strip():
            return {"intent": "chat", "confidence": 1.0, "reason": "empty"}

        msg_lower = message.lower().strip()

        for neg in NEGATIVE_TRIGGERS:
            if neg in msg_lower:
                return {"intent": "chat", "confidence": 0.8, "reason": f"negative trigger: {neg}"}

        has_trigger = False
        matched_trigger = ""
        for kw in SEARCH_TRIGGERS:
            if kw in msg_lower:
                has_trigger = True
                matched_trigger = kw
                break

        has_question = False
        for kw in QUESTION_WORDS:
            if kw in msg_lower:
                has_question = True
                break

        is_question_mark = message.strip().endswith("?")

        is_follow_up = self._detect_follow_up(message, conversation_history)

        if is_follow_up:
            return {
                "intent": "search",
                "confidence": 0.7,
                "reason": "follow-up question",
            }

        if has_trigger:
            return {
                "intent": "search",
                "confidence": 0.9,
                "reason": f"trigger: {matched_trigger}",
            }

        if has_question and is_question_mark:
            return {
                "intent": "search",
                "confidence": 0.75,
                "reason": "factual question with ?",
            }

        if is_question_mark and len(msg_lower.split()) > 3:
            return {
                "intent": "search",
                "confidence": 0.4,
                "reason": "question mark with multiple words",
            }

        return {"intent": "chat", "confidence": 0.8, "reason": "no search signal detected"}

    def _detect_follow_up(self, message: str, history: Optional[list]) -> bool:
        if not history or len(history) < 2:
            return False

        follow_up_patterns = [
            "lebih detail", "jelaskan lagi", "lanjut",
            "yang tadi", "yang sebelumnya", "tadi itu",
            "maksudnya", "contohnya", "misalnya",
            "yang nomor", "yang ke-", "nomor berapa",
            "coba cari lagi", "cari yang lain",
            "lebih murah", "lebih mahal", "lebih baik",
            "selain itu", "ada lagi", "yang lain",
        ]
        msg_lower = message.lower()
        return any(p in msg_lower for p in follow_up_patterns)


intent_classifier = IntentClassifier()
