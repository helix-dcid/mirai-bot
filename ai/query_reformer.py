"""
ai/query_reformer.py — Query Reformulation Engine
─────────────────────────────────────────────────
Mengubah pesan percakapan user menjadi query pencarian yang optimal.

Contoh:
  "Aku lagi pusing nih, ada tips nggak?" → "tips mengatasi pusing dan sakit kepala"
  "Tolong carikan harga iPhone 16 di Indonesia dong" → "harga iPhone 16 Indonesia 2026"
"""

import re
from typing import Optional, List
from utils.logger import setup_logging

logger = setup_logging()

CONVERSATIONAL_FILLERS = [
    "aku", "saya", "gue", "gw", "gua", "ane", "aq",
    "nih", "dong", "yuk", "sih", "deh", "lah", "kan",
    "tuh", "kok", "lho", "loh", "mah", "sih",
    "please", "tolong", "mohon", "bisa", "boleh",
    "nggak", "gak", "enggak", "kagak", "ndak", "gk",
    "ya", "yah", "yaa", "iyaa",
    "ada", "ada yang", "ada nggak",
    "pengen", "pingin", "pengen tahu", "penasaran",
    "mau tanya", "mau nanya", "mau tanya dong",
    "kasih tahu", "bisa kasih tahu",
]

STRIP_PATTERNS = [
    r"^@\w+\s*",
    r"^(hey|hai|halo|hello|hi|oy|woy|bro|sis|kak|gan)\s*[,!.\s]*",
]


class QueryReformer:
    """Reformulasi pesan percakapan menjadi query pencarian optimal."""

    def reformulate(
        self,
        user_message: str,
        conversation_history: Optional[List] = None,
        intent: Optional[dict] = None,
    ) -> str:
        if not user_message or not user_message.strip():
            return ""

        query = user_message.strip()

        for pattern in STRIP_PATTERNS:
            query = re.sub(pattern, "", query, flags=re.IGNORECASE).strip()

        query = re.sub(r"<@!?\d+>", "", query).strip()

        query_lower = query.lower()
        words = query_lower.split()
        filtered = []
        skip_next = False
        for i, word in enumerate(words):
            if skip_next:
                skip_next = False
                continue
            two_word = f"{word} {words[i+1]}" if i + 1 < len(words) else ""
            if two_word in CONVERSATIONAL_FILLERS:
                skip_next = True
                continue
            if word in CONVERSATIONAL_FILLERS and len(word) <= 4:
                continue
            filtered.append(word)

        query = " ".join(filtered)

        if conversation_history and intent and intent.get("reason") == "follow-up question":
            context_query = self._extract_context_from_history(conversation_history)
            if context_query:
                query = f"{context_query} {query}"

        query = re.sub(r"\s+", " ", query).strip()

        if len(query) > 500:
            query = query[:500]
        if len(query) < 2:
            query = user_message.strip()[:50]

        logger.debug(f"[QueryReformer] '{user_message[:60]}' → '{query[:60]}'")
        return query

    def _extract_context_from_history(self, history: List) -> str:
        for msg in reversed(history[-4:]):
            role = msg.get("role", "")
            text = ""
            if "parts" in msg and isinstance(msg["parts"], list) and msg["parts"]:
                part = msg["parts"][0]
                text = part.get("text", "") if isinstance(part, dict) else str(part)
            elif "content" in msg:
                text = msg["content"]

            if role == "user" and text:
                lines = text.strip().split("\n")
                for line in lines:
                    if line.lower().startswith("message:"):
                        return line[len("message:"):].strip()[:80]
                if not any(line.startswith(("Nama", "Channel", "User ID", "Server", "Timestamp"))
                           for line in lines[:5]):
                    return text.strip()[:80]

        return ""


query_reformer = QueryReformer()
