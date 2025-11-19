import asyncio
import logging
from html import escape
from typing import List

from aiogram import Bot

from app.core.config import Settings
from app.api.marzneshin import User

logger = logging.getLogger(__name__)

async def find_admin_chat_ids(owner_username: str, settings: Settings) -> List[int]:
    chat_ids = []
    for admin in settings.admins:
        if admin.panel_username == owner_username:
            chat_ids.extend(admin.chat_ids)
    return chat_ids

async def run_webhook_worker(queue: asyncio.Queue, bot: Bot, settings: Settings):
    logger.info("Webhook event worker started.")
    while True:
        try:
            event = await queue.get()
            
            if not (event and isinstance(event, dict) and event.get("action") == "user_deactivated"):
                queue.task_done()
                continue

            user_data = event.get("user")
            if not user_data:
                queue.task_done()
                continue

            user = User(**user_data)
            owner = user.owner_username
            
            if not owner:
                logger.warning(f"User {user.username} deactivated but has no owner. Cannot send alert.")
                queue.task_done()
                continue

            chat_ids = await find_admin_chat_ids(owner, settings)
            if not chat_ids:
                logger.warning(f"Owner '{owner}' found for user '{user.username}', but no matching chat_id in config.")
                queue.task_done()
                continue

            message = ""
            
            if user.expired:
                message = (
                    "🕔 #Expired\n"
                    "━━━━━━━━━━━━━━\n"
                    f"👤 User: <code>{escape(user.username)}</code>"
                )
            elif user.data_limit_reached:
                message = (
                    "🪫 #Limited\n"
                    "━━━━━━━━━━━━━━\n"
                    f"👤 User: <code>{escape(user.username)}</code>"
                )

            if message:
                for chat_id in chat_ids:
                    try:
                        await bot.send_message(chat_id, message, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Failed to send webhook alert to admin {chat_id}: {e}")
            
            queue.task_done()

        except Exception as e:
            logger.error(f"Error in webhook worker: {e}", exc_info=True)
            if 'queue' in locals():
                queue.task_done()