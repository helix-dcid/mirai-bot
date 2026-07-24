from plugins.base import Plugin


class SearchPlugin(Plugin):
    id = "search"
    name = "Web Search"
    version = "1.0.0"
    author = "Helix"
    description = "Pencarian web via Tavily, DuckDuckGo, dan Browserless"
    module_name = "search"
