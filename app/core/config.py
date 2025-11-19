import logging
from typing import List
from pydantic import BaseModel, computed_field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, YamlConfigSettingsSource

# --- Pydantic Models for Structured Config ---

class Admin(BaseModel):
    chat_ids: List[int]
    panel_username: str
    panel_password: str

class Settings(BaseSettings):
    BOT_TOKEN: str
    PANEL_URL: str

    ENABLE_WEBHOOK: bool = False
    WEBHOOK_ADDRESS: str = "0.0.0.0"
    WEBHOOK_PORT: int = 9090
    WEBHOOK_SECRET: str = "default_secret_please_change"
    
    admin_config: List[Admin]

    @computed_field
    @property
    def admin_chat_ids(self) -> List[int]:
        all_ids = []
        for admin in self.admin_config:
            all_ids.extend(admin.chat_ids)
        return all_ids
    
    @computed_field
    @property
    def admins(self) -> List[Admin]:
        return self.admin_config

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            env_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file='config.yml'),
        )

try:
    settings = Settings()
    logging.info(f"Configuration loaded successfully for {len(settings.admins)} admin groups.")
except Exception as e:
    logging.critical(f"FATAL: Configuration Error - {e}")
    raise