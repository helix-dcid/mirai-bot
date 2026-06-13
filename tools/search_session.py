"""
core/search_session.py — Search Session Tracker
───────────────────────────────────────────────
Melacak sesi pencarian per user untuk mendukung multi-turn search conversations.
"""

import time
from typing import Dict, Optional, List
from utils.logger import setup_logging

logger = setup_logging()

SESSION_TTL = 600  # 10 menit


class SearchSession:
    """State sesi pencarian untuk satu user."""

    __slots__ = (
        "user_id", "original_query", "reformulated_query",
        "results", "turn_count", "last_search_time",
        "engine", "results_shown",
    )

    def __init__(self, user_id: int, original_query: str,
                 reformulated_query: str = "", engine: str = ""):
        self.user_id = user_id
        self.original_query = original_query
        self.reformulated_query = reformulated_query or original_query
        self.results: List[dict] = []
        self.turn_count = 1
        self.last_search_time = time.time()
        self.engine = engine
        self.results_shown = 0


class SearchSessionManager:
    """Kelola sesi pencarian per user."""

    def __init__(self):
        self._sessions: Dict[int, SearchSession] = {}

    def get_session(self, user_id: int) -> Optional[SearchSession]:
        session = self._sessions.get(user_id)
        if session and time.time() - session.last_search_time < SESSION_TTL:
            return session
        if session:
            self._sessions.pop(user_id, None)
        return None

    def create_or_update_session(
        self,
        user_id: int,
        original_query: str,
        reformulated_query: str = "",
        results: Optional[List[dict]] = None,
        engine: str = "",
    ) -> SearchSession:
        existing = self.get_session(user_id)
        if existing:
            existing.turn_count += 1
            existing.original_query = original_query
            existing.reformulated_query = reformulated_query or original_query
            existing.results = results or []
            existing.last_search_time = time.time()
            existing.engine = engine
            existing.results_shown = 0
            return existing

        session = SearchSession(
            user_id=user_id,
            original_query=original_query,
            reformulated_query=reformulated_query,
            engine=engine,
        )
        session.results = results or []
        self._sessions[user_id] = session
        return session

    def cleanup_expired(self):
        now = time.time()
        expired = [
            uid for uid, s in self._sessions.items()
            if now - s.last_search_time >= SESSION_TTL
        ]
        for uid in expired:
            self._sessions.pop(uid, None)


search_session_manager = SearchSessionManager()
