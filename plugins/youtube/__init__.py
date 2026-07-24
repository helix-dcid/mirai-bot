from plugins.base import Plugin


class YouTubePlugin(Plugin):
    id = "youtube"
    name = "YouTube Transcript"
    version = "1.0.0"
    author = "Helix"
    description = "Ekstraksi transkrip/subtitle video YouTube via yt-dlp"
    module_name = "youtube_transcript"
