import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram_fsm_sqlitestorage import SQLiteStorage
from app.core.config import settings

os.makedirs("./data", exist_ok=True)

storage = SQLiteStorage("./data/fsm_storage.db")

bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=storage)
