import asyncio
import logging
from typing import Optional

from app.api.marzneshin import MarzneshinAPI
from app.core.api_manager import api_manager
from app.core.bot import bot, dp
from app.core.config import settings
from app.core.logger import setup_logging
from app.handlers import main_router
from app.handlers.middleware import AdminAuthMiddleware
from app.handlers.nodes import router as nodes_router
from app.monitoring.task import run_monitoring_loop

async def find_sudo_client() -> Optional[MarzneshinAPI]:
    logging.info("Attempting to find a 'sudo' admin for the monitoring task...")
    for admin in settings.admins:
        if not admin.chat_ids:
            continue
        
        first_chat_id = admin.chat_ids[0]
        
        try:
            client, _ = await api_manager.get_client(first_chat_id)
            admin_info = await client.get_current_admin()
            
            if admin_info and admin_info.is_sudo:
                logging.info(f"Sudo admin client found: '{admin.panel_username}'. Monitoring task will use this client.")
                return client
        except Exception as e:
            logging.warning(f"Could not check sudo status for admin '{admin.panel_username}': {e}")
            
    return None

async def main():
    setup_logging()

    dp.update.middleware(AdminAuthMiddleware())
    
    sudo_client = None
    sudo_admin_chat_ids = []
    
    logging.info("Checking all admins for 'sudo' privileges...")
    for admin in settings.admins:
        if not admin.chat_ids:
            continue
        
        first_chat_id = admin.chat_ids[0]
        
        try:
            client, _ = await api_manager.get_client(first_chat_id)
            admin_info = await client.get_current_admin()
            
            if admin_info and admin_info.is_sudo:
                logging.info(f"Admin '{admin.panel_username}' is SUDO. Adding {len(admin.chat_ids)} chat(s) to alert list.")
                sudo_admin_chat_ids.extend(admin.chat_ids)
                
                if sudo_client is None:
                    logging.info(f"Monitoring task will use '{admin.panel_username}' client.")
                    sudo_client = client
        except Exception as e:
            logging.warning(f"Could not check sudo status for admin '{admin.panel_username}': {e}")
            
    if sudo_client:
        asyncio.create_task(run_monitoring_loop(bot, sudo_client, sudo_admin_chat_ids))
    else:
        logging.warning(
            "No 'sudo' admin was found in the config.yml.\n"
            "Node monitoring task will not start, and the /nodes menu will be disabled."
        )

    dp.include_router(main_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot is starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped manually.")