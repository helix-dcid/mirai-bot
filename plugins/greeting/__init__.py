import discord
from plugins.base import Plugin


class GreetingPlugin(Plugin):
    id = "greeting"
    name = "Greeting"
    version = "1.0.0"
    author = "Helix"
    description = "Auto-welcome untuk member baru"
    module_name = "greeting"

    async def on_member_join(self, member: discord.Member):
        import tools.auto_greeting as _ag
        if _ag.auto_greeting:
            await _ag.auto_greeting.on_member_join(member)
