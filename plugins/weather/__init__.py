from plugins.base import Plugin


class WeatherPlugin(Plugin):
    id = "weather"
    name = "Weather"
    version = "1.0.0"
    author = "Helix"
    description = "Prakiraan cuaca BMKG dengan database 91k lokasi Indonesia"
    module_name = "weather"
