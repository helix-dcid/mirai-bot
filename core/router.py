import asyncio
from core.events.message_handler import MessageHandler
from services.ai_service import AIService
from services.scheduler_service import SchedulerService
from managers.cooldown_manager import CooldownManager
from tools.micro_rag import MicroRAG
from core.command import CommandGroup
from core.plugin_manager import PluginManager
from utils.web_rate_limiter import WebRateLimiter
from utils.logger import setup_logging

logger = setup_logging()

# Cache global untuk akses dari commands (terutama /plugin)
_router_cache = None


class Router:
    def __init__(self, bot):
        global _router_cache
        _router_cache = self
        self.bot = bot

        # Initialize Services & Managers
        self.ai_service = AIService()
        self.cooldown_manager = CooldownManager()
        self.micro_rag = MicroRAG()
        self.web_rate_limiter = WebRateLimiter()

        # Initialize Handlers
        self.message_handler = MessageHandler(
            bot, self.ai_service, self.cooldown_manager, self.micro_rag,
            web_rate_limiter=self.web_rate_limiter,
        )

        # Initialize Commands
        self.command_group = CommandGroup(bot)

        # Initialize PluginManager (sync: discover plugin classes)
        self.plugin_manager = PluginManager(bot)
        self.plugin_manager.discover_plugins()

        # Initialize Scheduler
        self.scheduler = SchedulerService(
            bot,
            self.micro_rag
        )

        # Inisialisasi AutoGreeting SEKALI — jangan di on_ready (hindari duplikat handler saat reconnect)
        from tools.auto_greeting import AutoGreeting
        from ai.gemini import GeminiClient
        self.auto_greeting = AutoGreeting(self.bot, GeminiClient())
        # Set module-level variable supaya greeting_command.py bisa import instance
        import tools.auto_greeting as _ag
        _ag.auto_greeting = self.auto_greeting

        self.setup_events()

    def setup_events(self):
        @self.bot.event
        async def on_ready():
            logger.info("✅ Bot connected as %s", self.bot.user)

            # Load all plugins (async: on_load lifecycle)
            await self.plugin_manager.load_all()

            # Register plugin commands to the shared command tree
            self.plugin_manager.register_commands(self.command_group.tree)

            # Sync global commands — includes built-in + plugin commands
            await self.command_group.sync_commands()

            # Dispatch on_ready to plugins
            await self.plugin_manager.dispatch_ready()

            if not getattr(self.bot, "_mirai_background_started", False):
                self.bot._mirai_background_started = True
                asyncio.create_task(self.scheduler.start_all())

        @self.bot.event
        async def on_message(message):
            # Plugin first: if a plugin handles this message, skip main handler
            handled = await self.plugin_manager.dispatch_message(message)
            if handled:
                return
            await self.message_handler.handle(message)

        @self.bot.event
        async def on_message_edit(before, after):
            handled = await self.plugin_manager.dispatch_message_edit(before, after)
            if handled:
                return

        @self.bot.event
        async def on_member_join(member):
            # AutoGreeting built-in
            if hasattr(self, 'auto_greeting') and self.auto_greeting:
                await self.auto_greeting.on_member_join(member)
            # Plugin hooks
            await self.plugin_manager.dispatch_member_join(member)

        @self.bot.event
        async def on_member_remove(member):
            await self.plugin_manager.dispatch_member_remove(member)
