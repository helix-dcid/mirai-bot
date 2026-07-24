# core/module_manager.py - Manajemen Modul Mirai
"""
Modul untuk mengelola status aktif/nonaktif dari berbagai fitur Mirai.

Fitur:
- Enable/disable modul seperti calculator, weather, greeting, deepseek, wellness
- Dynamic registration: plugin bisa daftarkan module_name-nya sendiri
- Konfigurasi disimpan di data/module_config.json
- Dapat diakses dari command /module
"""
import json
from pathlib import Path
from utils.logger import setup_logging

logger = setup_logging()
MODULE_CONFIG_PATH = Path("data/module_config.json")

# Built-in modules yang selalu tersedia
_BUILTIN_MODULES = [
    "calculator", "weather", "greeting", "deepseek",
    "wellness", "web_scraper", "youtube_transcript",
    "search", "journal",
]


class ModuleManager:
    def __init__(self):
        self._modules: set = set()
        self._config_cache: dict = {}
        self._cache_mtime: float = 0.0
        self._seed_builtins()
        self._ensure_config_exists()
        self._refresh_cache()

    def _seed_builtins(self):
        for name in _BUILTIN_MODULES:
            self._modules.add(name)

    def _ensure_config_exists(self):
        if not MODULE_CONFIG_PATH.parent.exists():
            MODULE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if not MODULE_CONFIG_PATH.exists():
            default_config = {m: True for m in self._modules}
            self._save_config(default_config)
            logger.info("[MODULE] Config file dibuat dengan default: semua modul aktif")

    def _load_config(self):
        try:
            with open(MODULE_CONFIG_PATH, 'r') as f:
                config = json.load(f)

            if "web_search" in config and "web_scraper" not in config:
                config["web_scraper"] = config.pop("web_search")
                self._save_config(config)
                logger.info("[MODULE] Migrasi: renamed 'web_search' → 'web_scraper'")

            for module in self._modules:
                if module not in config:
                    config[module] = True
                    logger.info("[MODULE] Modul '%s' ditambahkan ke config dengan default True", module)
            return config
        except Exception as e:
            logger.error(f"[MODULE] Error loading config: {e}")
            return {m: True for m in self._modules}

    def _refresh_cache(self):
        try:
            mtime = MODULE_CONFIG_PATH.stat().st_mtime
            if mtime != self._cache_mtime:
                self._config_cache = self._load_config()
                self._cache_mtime = mtime
        except Exception:
            pass

    def _save_config(self, config):
        try:
            with open(MODULE_CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"[MODULE] Error saving config: {e}")

    # ── Dynamic Registration ───────────────────────────────────

    def register_module(self, module_name: str, default_enabled: bool = True):
        if module_name in self._modules:
            return True
        self._modules.add(module_name)
        config = self._load_config()
        if module_name not in config:
            config[module_name] = default_enabled
            self._save_config(config)
            self._config_cache = config
            logger.info("[MODULE] Modul '%s' registered (default: %s)", module_name, default_enabled)
        return True

    def unregister_module(self, module_name: str):
        self._modules.discard(module_name)
        config = self._load_config()
        if module_name in config:
            del config[module_name]
            self._save_config(config)
            self._config_cache = config
            logger.info("[MODULE] Modul '%s' unregistered", module_name)

    # ── Public API ─────────────────────────────────────────────

    def is_enabled(self, module_name: str) -> bool:
        self._refresh_cache()
        if module_name not in self._modules:
            return False
        return self._config_cache.get(module_name, True)

    def set_status(self, module_name: str, status: bool):
        config = self._load_config()
        config[module_name] = status
        self._save_config(config)
        self._config_cache = config
        try:
            self._cache_mtime = MODULE_CONFIG_PATH.stat().st_mtime
        except Exception:
            pass

    def get_all_status(self):
        return self._load_config()

    @property
    def registered_modules(self) -> list:
        return sorted(self._modules)

    def reset(self):
        self._modules.clear()
        self._seed_builtins()
        default_config = {m: True for m in self._modules}
        self._save_config(default_config)
        self._config_cache = dict(default_config)
        self._cache_mtime = 0.0


module_manager = ModuleManager()
