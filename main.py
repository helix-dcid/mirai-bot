import os
from dotenv import load_dotenv

# Load .env FIRST before importing project modules that read env vars
load_dotenv()

from core.bot import create_bot
from core.router import Router
from utils.logger import setup_logging

logger = setup_logging()

def main():
    """Entry point minimal."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("❌ DISCORD_TOKEN tidak ditemukan di .env!")

    # Create bot
    bot = create_bot()
    
    # Create router (handles everything)
    router = Router(bot)
    
    # Start bot
    logger.info("Starting Mirai Helix...")
    bot.run(token)

if __name__ == "__main__":
    main()
