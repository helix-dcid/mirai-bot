# ai/tool_executor.py — Tool Executor for Gemini Function Calling
"""
Maps Gemini functionCall responses to async Python implementations.
Each handler calls existing client code (BMKGClient, WebSearchClient, etc.)
and returns a dict suitable for Gemini's functionResponse.
"""

import asyncio

from config import TOOL_EXECUTION_TIMEOUT
from utils.logger import setup_logging

logger = setup_logging()


class ToolExecutor:
    """Execute Gemini function calls by delegating to existing client instances."""

    def __init__(self, gemini_client):
        self._bmkg = gemini_client.bmkg
        self._web_search = gemini_client.web_search
        self._youtube_transcript = gemini_client.youtube_transcript
        self._handlers = {
            "get_weather": self._execute_weather,
            "search_web": self._execute_search,
            "get_youtube_transcript": self._execute_youtube_transcript,
        }

    async def execute(self, function_call: dict) -> dict:
        """
        Execute a function call and return the response dict.

        Args:
            function_call: {"name": str, "args": dict}

        Returns:
            {"name": str, "response": dict}
        """
        name = function_call.get("name", "")
        args = function_call.get("args", {})

        handler = self._handlers.get(name)
        if not handler:
            logger.warning(f"[ToolExecutor] Unknown tool: {name}")
            return {"name": name, "response": {"error": f"Unknown tool: {name}"}}

        try:
            result = await asyncio.wait_for(
                handler(args),
                timeout=TOOL_EXECUTION_TIMEOUT,
            )
            logger.info(f"[ToolExecutor] {name} OK")
            return {"name": name, "response": result}
        except asyncio.TimeoutError:
            logger.warning(f"[ToolExecutor] {name} timed out ({TOOL_EXECUTION_TIMEOUT}s)")
            return {
                "name": name,
                "response": {"error": f"Tool {name} timed out after {TOOL_EXECUTION_TIMEOUT}s"},
            }
        except Exception as e:
            logger.warning(f"[ToolExecutor] {name} failed: {e}")
            return {
                "name": name,
                "response": {"error": f"Tool execution failed: {str(e)[:200]}"},
            }

    # ------------------------------------------------------------------
    # Weather handler
    # ------------------------------------------------------------------

    async def _execute_weather(self, args: dict) -> dict:
        location = args.get("location", "Jakarta")
        logger.info(f"[ToolExecutor] get_weather('{location}')")

        code = await self._bmkg.search_location_code(location)
        if not code:
            return {"error": f"Location '{location}' not found in BMKG database."}

        data = await self._bmkg.get_weather_raw(code)
        if not data:
            return {"error": f"No weather data available for '{location}'."}

        return {
            "location": data.get("lokasi", {}),
            "forecasts": data.get("prakiraan", []),
            "source": "BMKG (Badan Meteorologi, Klimatologi, dan Geofisika)",
        }

    # ------------------------------------------------------------------
    # Search handler
    # ------------------------------------------------------------------

    async def _execute_search(self, args: dict) -> dict:
        query = args.get("query", "")
        if not query:
            return {"error": "No search query provided."}

        logger.info(f"[ToolExecutor] search_web('{query[:60]}')")
        data = await self._web_search.search(query)

        if not data or not data.get("results"):
            return {"error": f"No search results found for '{query}'."}

        return {
            "results": data["results"],
            "answer": data.get("answer", ""),
            "engine": data.get("engine", "web"),
        }

    async def _execute_youtube_transcript(self, args: dict) -> dict:
        video_url = args.get("video_url", "")
        if not video_url:
            return {"error": "No video URL provided."}

        logger.info(f"[ToolExecutor] get_youtube_transcript('{video_url[:60]}')")
        result = await self._youtube_transcript.get_transcript(video_url)

        if not result:
            return {"error": f"Failed to fetch transcript for: {video_url}"}

        transcript = result.get("transcript")
        if not transcript:
            return {
                "video_id": result["video_id"],
                "title": result.get("title", "Unknown"),
                "transcript": None,
                "note": "Video ini tidak memiliki subtitle/closed captions yang bisa diekstrak.",
                "url": result["url"],
            }

        return {
            "video_id": result["video_id"],
            "title": result.get("title", "Unknown"),
            "transcript": transcript,
            "url": result["url"],
        }


