import asyncio
import logging
from typing import Optional, List, Tuple

from app.api.marzneshin import MarzneshinAPI
from app.core.api_manager import api_manager
from app.core.bot import bot, dp
from app.core.config import settings
from app.core.logger import setup_logging
from app.handlers import main_router
from app.handlers.middleware import AdminAuthMiddleware
from app.monitoring.task import run_monitoring_loop
from app.webhook.server import start_webhook_server
from app.webhook.worker import run_webhook_worker

async def find_sudo_client() -> Tuple[Optional[MarzneshinAPI], List[int]]:
    logging.info("Attempting to find a 'sudo' admin and all sudo chat IDs...")
    sudo_client_found: Optional[MarzneshinAPI] = None
    sudo_chat_ids: List[int] = []

    for admin in settings.admins:
        if not admin.chat_ids:
            continue
        
        first_chat_id = admin.chat_ids[0]
        
        try:
            client, _ = await api_manager.get_client(first_chat_id)
            admin_info = await client.get_current_admin()
            
            if admin_info and admin_info.is_sudo:
                logging.info(f"Admin '{admin.panel_username}' is SUDO. Adding {len(admin.chat_ids)} chat(s) to alert list.")
                sudo_chat_ids.extend(admin.chat_ids)
                
                if sudo_client_found is None:
                    logging.info(f"Monitoring task will use '{admin.panel_username}' client.")
                    sudo_client_found = client
        except Exception as e:
            logging.warning(f"Could not check sudo status for admin '{admin.panel_username}': {e}")
            
    return sudo_client_found, list(set(sudo_chat_ids))

async def main():
    setup_logging()
    
    dp.update.middleware(AdminAuthMiddleware())

    sudo_client, sudo_admin_chat_ids = await find_sudo_client()
        
    webhook_queue = asyncio.Queue()
    
    bot_polling_task = dp.start_polling(bot)
    
    all_tasks = [bot_polling_task]
    
    if sudo_client:
        all_tasks.append(run_monitoring_loop(bot, sudo_client, sudo_admin_chat_ids))
    else:
        logging.warning("No 'sudo' admin found. Node monitoring task will not start.")

    if settings.ENABLE_WEBHOOK:
        all_tasks.append(start_webhook_server(bot, webhook_queue, settings))
        all_tasks.append(run_webhook_worker(webhook_queue, bot, settings))
        logging.info("Webhook server and worker are enabled and will start.")
    else:
        logging.info("Webhook feature is disabled in .env file.")

    dp.include_router(main_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot is starting polling...")
    await asyncio.gather(*all_tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped manually.")