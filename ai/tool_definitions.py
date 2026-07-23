# ai/tool_definitions.py — Gemini Function Calling Tool Declarations
"""
Deklarasi tools untuk Gemini function calling.
Hanya tools yang module-nya aktif yang dikirim ke Gemini.

Tools yang didaftarkan (semantic — butuh LLM routing):
  - get_weather: BMKG weather data
  - search_web: Tavily / DuckDuckGo web search

Tools yang TIDAK didaftarkan (deterministic — regex detection):
  - scrape_webpage: URL terdeteksi → Browserless scrape
  - get_youtube_transcript: yt-dlp transcript extraction (function calling)
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
    "get_journal_reference": {
        "name": "get_journal_reference",
        "description": (
            "Search academic journals and scientific literature for authoritative "
            "references on health, medical, science, or any scholarly topic. "
            "Use this when the user asks a health question ('apa penyebab...', "
            "'gejala...', 'efek samping...'), a science question ('penelitian "
            "tentang...', 'studi mengenai...', 'jurnal tentang...'), or whenever "
            "citing a peer-reviewed source would add credibility to your answer. "
            "Returns title, authors, journal name, year, DOI, and abstract. "
            "Cite the source naturally when presenting the information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Academic search query in Indonesian or English. "
                        "Use keywords from the user's question. "
                        "Pastikan pakai bahasa Indonesia jika user pakai bahasa Indonesia. "
                        "Example: 'efek vitamin D pada imunitas' or "
                        "'terapi kognitif perilaku untuk insomnia'."
                    ),
                }
            },
            "required": ["query"],
        },
    },
    "get_youtube_transcript": {
        "name": "get_youtube_transcript",
        "description": (
            "Fetch the transcript/subtitle text of a YouTube video. "
            "Use this when the user shares a YouTube link and asks about "
            "the video's content, wants a summary, needs the transcript, "
            "or asks what the video is about (e.g., 'apa isi video ini', "
            "'ringkas video ini', 'transkrip video ini'). "
            "Pass the full YouTube URL (youtube.com/watch?v=... or youtu.be/...). "
            "Do NOT use this for general web search queries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_url": {
                    "type": "string",
                    "description": (
                        "Full YouTube video URL, e.g. "
                        "'https://www.youtube.com/watch?v=dQw4w9WgXcQ' "
                        "or 'https://youtu.be/dQw4w9WgXcQ'. "
                        "Extract the exact URL from the user's message."
                    ),
                }
            },
            "required": ["video_url"],
        },
    },
}

MODULE_TO_TOOL = {
    "weather": "get_weather",
    "search": "search_web",
    "youtube_transcript": "get_youtube_transcript",
    "journal": "get_journal_reference",
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
