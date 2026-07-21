import asyncio
from ai.gemini import GeminiClient
from memory import add_message, add_message_parts, get_history

class AIService:
    def __init__(self):
        self.gemini = GeminiClient()

    async def generate_reply(self, history, user_context: str = "") -> str:
        """Generate AI reply given history.
        
        FIXED: Removed asyncio.to_thread() since GeminiClient.generate() 
        is already an async method. Using asyncio.to_thread() on async 
        functions causes them to not execute properly.
        """
        reply = await self.gemini.generate(history, user_context=user_context)
        return reply

    async def add_to_history(self, role, content):
        """Add message to conversation history."""
        await add_message(role, content)

    async def add_to_history_parts(self, role, parts):
        """Add multi-part message (teks + gambar) ke history."""
        await add_message_parts(role, parts)

    def get_history(self):
        """Retrieve conversation history."""
        return get_history()