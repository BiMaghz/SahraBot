import asyncio
import logging

from app.core.bot import bot, dp
from app.core.logger import setup_logging
from app.handlers import main_router
from app.handlers.middleware import AdminAuthMiddleware

async def main():
    
    setup_logging()

    dp.update.middleware(AdminAuthMiddleware())
    
    dp.include_router(main_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Starting bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped manually.")