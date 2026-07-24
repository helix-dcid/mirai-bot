import json
import discord
from discord import app_commands
from pathlib import Path
from typing import Optional, Dict, Any, List
from core.module_manager import module_manager
from utils.logger import setup_logging

logger = setup_logging()

PLUGIN_DATA_ROOT = Path("data/plugins")


class Plugin:
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    author: str = "unknown"
    description: str = ""
    module_name: str = ""
    dependencies: List[str] = []
    config_defaults: Dict[str, Any] = {}

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._config: Dict[str, Any] = {}
        self._load_config()

    # ── Lifecycle Hooks ────────────────────────────────────────

    async def on_load(self):
        pass

    async def on_unload(self):
        pass

    async def on_ready(self):
        pass

    async def on_message(self, message: discord.Message) -> bool:
        return False

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> bool:
        return False

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> bool:
        return False

    async def on_member_join(self, member: discord.Member):
        pass

    async def on_member_remove(self, member: discord.Member):
        pass

    def register_commands(self, tree: app_commands.CommandTree):
        pass

    # ── Config System ──────────────────────────────────────────

    def _config_path(self) -> Path:
        pid = self.id or self.__class__.__name__.lower()
        PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)
        return PLUGIN_DATA_ROOT / f"{pid}.json"

    def _load_config(self):
        path = self._config_path()
        self._config = dict(self.config_defaults)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._config.update(data)
            except Exception as e:
                logger.warning("[Plugin:%s] Gagal load config: %s", self.display_name, e)

    def save_config(self):
        path = self._config_path()
        try:
            path.write_text(
                json.dumps(self._config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("[Plugin:%s] Gagal save config: %s", self.display_name, e)

    def get_config(self, key: str, default=None):
        return self._config.get(key, default)

    def set_config(self, key: str, value):
        self._config[key] = value
        self.save_config()

    # ── Data Path ───────────────────────────────────────────────

    def get_data_path(self) -> Path:
        pid = self.id or self.__class__.__name__.lower()
        path = PLUGIN_DATA_ROOT / pid
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ── Helpers ─────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        if not self.module_name:
            return True
        return module_manager.is_enabled(self.module_name)

    @property
    def display_name(self) -> str:
        return self.name or self.__class__.__name__

    @property
    def plugin_id(self) -> str:
        return self.id or self.__class__.__name__.lower()

    # ── Plugin-to-Plugin API ─────────────────────────────────────

    @property
    def api(self) -> Dict[str, Any]:
        return {}
