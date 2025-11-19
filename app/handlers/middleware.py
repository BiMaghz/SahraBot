from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.api_manager import api_manager
from app.core.config import settings

class AdminAuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        user = data.get("event_from_user")
        if not user or user.id not in settings.admin_chat_ids:
            return await handler(event, data)

        try:
            api_client, admin_config = await api_manager.get_client(user.id)
            
            data["api_client"] = api_client
            data["admin_config"] = admin_config
            
        except ValueError as e:
            print(f"Middleware Error: {e}")
            return None

        return await handler(event, data)