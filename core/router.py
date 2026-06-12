import asyncio
from core.events.message_handler import MessageHandler
from services.ai_service import AIService
from services.scheduler_service import SchedulerService
from managers.cooldown_manager import CooldownManager
from core.micro_rag import MicroRAG
from core.command import CommandGroup
from utils.web_rate_limiter import WebRateLimiter
from utils.logger import setup_logging

logger = setup_logging()

class Router:
    def __init__(self, bot):
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
        
        # Initialize Scheduler
        self.scheduler = SchedulerService(
            bot, 
            self.micro_rag
        )
        
        # Inisialisasi AutoGreeting SEKALI — jangan di on_ready (hindari duplikat handler saat reconnect)
        from core.auto_greeting import AutoGreeting
        from ai.gemini import GeminiClient
        self.auto_greeting = AutoGreeting(self.bot, GeminiClient())
        
        self.setup_events()

    def setup_events(self):
        @self.bot.event
        async def on_ready():
            logger.info("✅ Bot connected as %s", self.bot.user)
            # Only sync globally — skip guild-specific sync to avoid double commands
            await self.command_group.sync_commands()
            
            if not getattr(self.bot, "_mirai_background_started", False):
                self.bot._mirai_background_started = True
                asyncio.create_task(self.scheduler.start_all())

        @self.bot.event
        async def on_message(message):
            await self.message_handler.handle(message)
