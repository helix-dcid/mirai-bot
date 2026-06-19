# ai/tool_definitions.py — Gemini Function Calling Tool Declarations
"""
Deklarasi tools untuk Gemini function calling.
Hanya tools yang module-nya aktif yang dikirim ke Gemini.

Tools yang didaftarkan (semantic — butuh LLM routing):
  - get_weather: BMKG weather data
  - search_web: Tavily / DuckDuckGo web search
  - get_news: RSS news summary

Tools yang TIDAK didaftarkan (deterministic — regex detection):
  - scrape_webpage: URL terdeteksi → Browserless scrape
  - get_youtube_transcript: YouTube URL terdeteksi → yt-dlp
"""

from core.module_manager import module_manager

TOOL_DECLARATIONS = {
    "get_weather": {
        "name": "get_weather",
        "description": (
            "Get real-time weather forecast for an Indonesian city from BMKG "
            "(Badan Meteorologi, Klimatologi, dan Geofisika). "
            "Use this when the user asks about weather, temperature, rain, "
            "or climate conditions in any Indonesian location, or when weather "
            "information would help answer their question (e.g., trip planning, "
            "outdoor activities). Do NOT use for general knowledge about weather "
            "patterns — only for current real-time forecasts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "City or region name in Indonesia, e.g. 'Bandung', "
                        "'Jakarta', 'Surabaya', 'Yogyakarta'. Use the most "
                        "specific location mentioned by the user."
                    ),
                }
            },
            "required": ["location"],
        },
    },
    "search_web": {
        "name": "search_web",
        "description": (
            "Search the web for current, real-time information. "
            "Use this when the user asks about recent events, current prices, "
            "trending topics, product comparisons, or any factual question "
            "that requires up-to-date data beyond your training knowledge. "
            "Do NOT use this for general knowledge questions you can answer "
            "directly from your training data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A concise, well-formed search query. Extract the core "
                        "information need from the user's message. "
                        "Example: 'harga iPhone 16 Indonesia 2025' not "
                        "'tolong carikan harga hp'."
                    ),
                }
            },
            "required": ["query"],
        },
    },
    "get_news": {
        "name": "get_news",
        "description": (
            "Get the latest Indonesian news summary, refreshed hourly from "
            "10 major media sources (Antara, Tempo, CNN Indonesia, Republika, "
            "Tribunnews, BBC Indonesia, etc.). "
            "Use this when the user asks about latest news, current events, "
            "what's happening in Indonesia, or when news context is relevant. "
            "Optionally filter by topic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "Optional topic to filter news by, e.g. 'kesehatan', "
                        "'politik', 'ekonomi', 'teknologi'. Omit or use empty "
                        "string for general news."
                    ),
                }
            },
            "required": [],
        },
    },
}

MODULE_TO_TOOL = {
    "weather": "get_weather",
    "search": "search_web",
    "news": "get_news",
}


def get_active_tools() -> list[dict] | None:
    """
    Return the tools array for the Gemini payload.
    Only includes tools whose backing module is enabled.
    Returns None if no semantic tools are active (skip function calling).
    """
    active = []
    for module_name, tool_name in MODULE_TO_TOOL.items():
        if module_manager.is_enabled(module_name):
            active.append(tool_name)

    if not active:
        return None

    return [{"functionDeclarations": [TOOL_DECLARATIONS[n] for n in active]}]
