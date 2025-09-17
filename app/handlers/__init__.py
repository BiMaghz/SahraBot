from aiogram import Router

from .menus import router as menus_router
from .user import router as user_management_router
from .search import router as inline_router

main_router = Router()

main_router.include_routers(
    menus_router,
    user_management_router,
    inline_router,
)