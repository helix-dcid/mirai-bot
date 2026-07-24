import importlib
import time
import traceback
import discord
from pathlib import Path
from typing import Dict, List, Optional, Type
from discord import app_commands
from plugins.base import Plugin
from core.module_manager import module_manager
from utils.logger import setup_logging

logger = setup_logging()

PLUGIN_PACKAGE = "plugins"

# Circuit breaker thresholds
_ERROR_THRESHOLD = 3
_ERROR_WINDOW = 300  # 5 menit


class PluginManager:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.plugins: Dict[str, Plugin] = {}
        self._plugin_classes: Dict[str, Type[Plugin]] = {}
        self._load_order: List[str] = []
        self._error_tracker: Dict[str, List[float]] = {}

    # ── Discovery & Loading ─────────────────────────────────────

    def discover_plugins(self, force: bool = False):
        if self._plugin_classes and not force:
            return
        if force:
            self._plugin_classes.clear()
        import plugins as pkg
        plugin_path = Path(pkg.__file__).parent
        for item in plugin_path.iterdir():
            if not item.is_dir() or item.name.startswith("_"):
                continue
            init_file = item / "__init__.py"
            if not init_file.exists():
                continue
            try:
                mod_name = f"{PLUGIN_PACKAGE}.{item.name}"
                mod = importlib.import_module(mod_name)
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and issubclass(attr, Plugin) and attr is not Plugin:
                        pid = getattr(attr, 'id', None) or item.name
                        self._plugin_classes[pid] = attr
                        name = getattr(attr, 'name', None) or item.name
                        ver = getattr(attr, 'version', '?')
                        logger.info("[Plugin] Discovered: %s v%s", name, ver)
                        break
            except Exception as e:
                logger.error("[Plugin] Gagal discover %s: %s", item.name, e)

    def _resolve_dependencies(self) -> List[str]:
        ordered = []
        visited = set()

        def visit(pid: str, path: set):
            if pid in ordered:
                return
            if pid in path:
                raise RuntimeError(f"[Plugin] Dependency cycle detected: {' → '.join(path)} → {pid}")
            cls = self._plugin_classes.get(pid)
            if not cls:
                logger.warning("[Plugin] Dependency '%s' not found, skip", pid)
                return
            path.add(pid)
            for dep in cls.dependencies:
                visit(dep, path)
            path.remove(pid)
            if pid not in ordered:
                ordered.append(pid)

        for pid in self._plugin_classes:
            if pid not in visited:
                visit(pid, set())
        return ordered

    async def load_plugin(self, name: str) -> Optional[Plugin]:
        if name in self.plugins:
            return self.plugins[name]
        cls = self._plugin_classes.get(name)
        if not cls:
            logger.error("[Plugin] %s not found", name)
            return None
        try:
            instance = cls(self.bot)
            self.plugins[name] = instance

            if instance.module_name:
                module_manager.register_module(instance.module_name)

            await instance.on_load()
            logger.info("[Plugin] Loaded: %s v%s", instance.display_name, instance.version)
            return instance
        except Exception as e:
            logger.error("[Plugin] Gagal load %s: %s", name, e)
            traceback.print_exc()
            return None

    async def load_all(self):
        self.discover_plugins()
        self._load_order = self._resolve_dependencies()
        for pid in self._load_order:
            await self.load_plugin(pid)

    async def unload_plugin(self, name: str):
        plugin = self.plugins.pop(name, None)
        if plugin:
            if plugin.module_name:
                module_manager.unregister_module(plugin.module_name)
            await plugin.on_unload()
            logger.info("[Plugin] Unloaded: %s", plugin.display_name)

    async def reload_plugin(self, name: str) -> Optional[Plugin]:
        old = self.plugins.get(name)
        mod_path = ""
        if old:
            mod_path = old.__class__.__module__
        await self.unload_plugin(name)
        if mod_path:
            try:
                mod = importlib.import_module(mod_path)
                importlib.reload(mod)
            except Exception as e:
                logger.error("[Plugin] Gagal reload module %s: %s", mod_path, e)
        self.discover_plugins(force=True)
        return await self.load_plugin(name)

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return self.plugins.get(name)

    def get_plugin_api(self, name: str) -> Optional[Dict]:
        plugin = self.plugins.get(name)
        if plugin:
            return plugin.api
        return None

    def get_dependents(self, plugin_id: str) -> List[str]:
        dependents = []
        for pid, cls in self._plugin_classes.items():
            if plugin_id in cls.dependencies:
                dependents.append(pid)
        return dependents

    def get_all_plugins(self) -> List[Plugin]:
        return list(self.plugins.values())

    # ── Circuit Breaker ─────────────────────────────────────────

    def _track_error(self, plugin_id: str):
        now = time.time()
        if plugin_id not in self._error_tracker:
            self._error_tracker[plugin_id] = []
        self._error_tracker[plugin_id].append(now)
        # Purge errors older than window
        cutoff = now - _ERROR_WINDOW
        self._error_tracker[plugin_id] = [t for t in self._error_tracker[plugin_id] if t > cutoff]
        error_count = len(self._error_tracker[plugin_id])

        if error_count >= _ERROR_THRESHOLD:
            module_name = ""
            p = self.plugins.get(plugin_id)
            if p:
                module_name = p.module_name
            if module_name:
                module_manager.set_status(module_name, False)
                logger.warning(
                    "[Plugin] Circuit breaker: %s (%d errors in 5m) — auto-disabled module '%s'",
                    plugin_id, error_count, module_name,
                )

    def _is_broken(self, plugin_id: str) -> bool:
        p = self.plugins.get(plugin_id)
        if not p or not p.module_name:
            return False
        return not module_manager.is_enabled(p.module_name)

    # ── Command Registration ────────────────────────────────────

    def register_commands(self, tree: app_commands.CommandTree):
        for plugin in self.plugins.values():
            try:
                plugin.register_commands(tree)
            except Exception as e:
                logger.error("[Plugin] register_commands error in %s: %s", plugin.display_name, e)
                self._track_error(plugin.plugin_id)

    # ── Event Dispatchers ───────────────────────────────────────

    async def dispatch_ready(self):
        for plugin in self.plugins.values():
            if self._is_broken(plugin.plugin_id):
                continue
            try:
                await plugin.on_ready()
            except Exception as e:
                logger.error("[Plugin] on_ready error in %s: %s", plugin.display_name, e)
                self._track_error(plugin.plugin_id)

    async def dispatch_message(self, message: discord.Message) -> bool:
        for plugin in self.plugins.values():
            if self._is_broken(plugin.plugin_id) or not plugin.is_enabled():
                continue
            try:
                handled = await plugin.on_message(message)
                if handled:
                    return True
            except Exception as e:
                logger.error("[Plugin] on_message error in %s: %s", plugin.display_name, e)
                self._track_error(plugin.plugin_id)
        return False

    async def dispatch_message_edit(self, before: discord.Message, after: discord.Message) -> bool:
        for plugin in self.plugins.values():
            if self._is_broken(plugin.plugin_id) or not plugin.is_enabled():
                continue
            try:
                handled = await plugin.on_message_edit(before, after)
                if handled:
                    return True
            except Exception as e:
                logger.error("[Plugin] on_message_edit error in %s: %s", plugin.display_name, e)
                self._track_error(plugin.plugin_id)
        return False

    async def dispatch_reaction_add(self, reaction, user) -> bool:
        for plugin in self.plugins.values():
            if self._is_broken(plugin.plugin_id) or not plugin.is_enabled():
                continue
            try:
                handled = await plugin.on_reaction_add(reaction, user)
                if handled:
                    return True
            except Exception as e:
                logger.error("[Plugin] on_reaction_add error in %s: %s", plugin.display_name, e)
                self._track_error(plugin.plugin_id)
        return False

    async def dispatch_member_join(self, member: discord.Member):
        for plugin in self.plugins.values():
            if self._is_broken(plugin.plugin_id) or not plugin.is_enabled():
                continue
            try:
                await plugin.on_member_join(member)
            except Exception as e:
                logger.error("[Plugin] on_member_join error in %s: %s", plugin.display_name, e)
                self._track_error(plugin.plugin_id)

    async def dispatch_member_remove(self, member: discord.Member):
        for plugin in self.plugins.values():
            if self._is_broken(plugin.plugin_id) or not plugin.is_enabled():
                continue
            try:
                await plugin.on_member_remove(member)
            except Exception as e:
                logger.error("[Plugin] on_member_remove error in %s: %s", plugin.display_name, e)
                self._track_error(plugin.plugin_id)
