from typing import Dict, Tuple

from app.api.marzneshin import MarzneshinAPI
from app.core.config import Admin, settings

class APIClientManager:
    def __init__(self):
        self._clients: Dict[str, MarzneshinAPI] = {}
        self._admin_map: Dict[int, Admin] = {}
        for admin in settings.admins:
            for chat_id in admin.chat_ids:
                self._admin_map[chat_id] = admin

    async def get_client(self, chat_id: int) -> Tuple[MarzneshinAPI, Admin]:
        admin_config = self._admin_map.get(chat_id)
        if not admin_config:
            raise ValueError(f"No admin configuration found for chat_id {chat_id}")

        if admin_config.panel_username in self._clients:
            return self._clients[admin_config.panel_username], admin_config

        client = MarzneshinAPI(
            panel_url=settings.PANEL_URL,
            username=admin_config.panel_username,
            password=admin_config.panel_password
        )
        self._clients[admin_config.panel_username] = client
        return client, admin_config

api_manager = APIClientManager()