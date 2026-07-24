# core/auto_greeting.py - Fitur Welcome & Goodbye Otomatis untuk Mirai
import asyncio
import discord
import json
from pathlib import Path
from utils.logger import setup_logging
from core.module_manager import module_manager

logger = setup_logging()

CONFIG_PATH = Path("data/greeting_config.json")

# Instance global — diset oleh Router() setelah inisialisasi
auto_greeting = None

class AutoGreeting:
    def __init__(self, bot: discord.Client, gemini_client):
        self.bot = bot
        self.gemini = gemini_client
        self._ensure_config_exists()

    def _ensure_config_exists(self):
        if not CONFIG_PATH.parent.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'w') as f:
                json.dump({"enabled": True, "guilds": {}}, f, indent=4)

    def _load_config(self):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[GREETING] Error loading config: {e}")
            return {"enabled": True, "guilds": {}}

    def _save_config(self, config):
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"[GREETING] Error saving config: {e}")

    def is_enabled(self, guild_id: int) -> bool:
        if not module_manager.is_enabled("greeting"):
            return False
        config = self._load_config()
        if not config.get("enabled", True):
            return False
        guild_config = config.get("guilds", {}).get(str(guild_id), {})
        return guild_config.get("enabled", True)

    def set_enabled(self, guild_id: int, status: bool):
        config = self._load_config()
        if str(guild_id) not in config["guilds"]:
            config["guilds"][str(guild_id)] = {}
        config["guilds"][str(guild_id)]["enabled"] = status
        self._save_config(config)

    def set_channel(self, guild_id: int, channel_id: int):
        config = self._load_config()
        if str(guild_id) not in config["guilds"]:
            config["guilds"][str(guild_id)] = {}
        config["guilds"][str(guild_id)]["channel_id"] = channel_id
        self._save_config(config)

    def _get_welcome_message(self, member: discord.Member) -> str:
        name = member.display_name
        perkenalan = "<#1391643015969509476>"
        pedoman = "<#1389578192246935633>"
        return (
            f"Hey {member.mention} — {name} kan? Selamat datang!\n"
            f"Ayo kenalan dulu lewat {perkenalan}.\n"
            f"Oh ya, jangan sampai kelewatan {pedoman} ya, atau tanya pengurus aja kalau bingung.\n"
            f"Makasih banyak!"
        )

    async def on_member_join(self, member: discord.Member):
        if member.bot or not self.is_enabled(member.guild.id):
            return
        channel = self._get_greeting_channel(member.guild)
        if not channel:
            return
        await asyncio.sleep(2)
        try:
            welcome_msg = self._get_welcome_message(member)
            await channel.send(welcome_msg)
            logger.info("[WELCOME] Sent welcome message for %s in %s", member.display_name, channel.name)
        except Exception as e:
            logger.error("[WELCOME] Critical Error: %s", e)

    def _get_greeting_channel(self, guild: discord.Guild) -> discord.TextChannel:
        """Mencari channel terbaik untuk mengirim pesan sambutan."""
        config = self._load_config()
        guild_config = config.get("guilds", {}).get(str(guild.id), {})
        
        # 1. Coba channel ID yang dikonfigurasi manual
        custom_channel_id = guild_config.get("channel_id")
        if custom_channel_id:
            channel = guild.get_channel(int(custom_channel_id))
            if channel and isinstance(channel, discord.TextChannel) and channel.permissions_for(guild.me).send_messages:
                return channel

        # 2. Coba ID chat-umum yang sudah diketahui
        known_channel = guild.get_channel(1389066613398966392)
        if known_channel and isinstance(known_channel, discord.TextChannel) and known_channel.permissions_for(guild.me).send_messages:
            return known_channel

        # 3. Cari channel dengan nama umum
        common_names = ['chat-umum', 'general', 'umum', 'cat-umum', 'welcome', 'greetings', 'halo', 'selamat-datang']
        for name in common_names:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel and channel.permissions_for(guild.me).send_messages:
                return channel

        # 4. Coba system channel
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            return guild.system_channel
            
        # 5. Fallback
        return next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
