import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.api.marzneshin import MarzneshinAPI
from app.core.config import settings
from .helpers import (
    _create_users_paginator, _display_user_details,
    _get_dashboard_content
)
from .states import GeneralPanelFSM

router = Router()
router.message.filter(F.from_user.id.in_(settings.admin_chat_ids))
router.callback_query.filter(F.from_user.id.in_(settings.admin_chat_ids))

logger = logging.getLogger(__name__)

@router.message(Command("start", "panel"))
async def cmd_start_panel(message: Message, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    await message.delete()
    
    fsm_data = await state.get_data() or {}
    old_panel_id = fsm_data.get("main_panel_id")
    if old_panel_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=old_panel_id)
        except TelegramBadRequest as e:
            logger.warning(f"Failed to delete old panel message: {e}")

    text, keyboard = await _get_dashboard_content(api_client)
    
    new_panel = await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await state.set_state(GeneralPanelFSM.main_menu)
    await state.update_data(main_panel_id=new_panel.message_id)

@router.callback_query(F.data.startswith("panel:browse_users:"))
async def cb_browse_users(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    await callback.answer("Loading users...")
    
    try:
        _, _, status_filter, page_str = callback.data.split(":")
        page = int(page_str)
    except (ValueError, IndexError):
        logger.warning(f"Invalid callback data for user browsing: {callback.data}")
        return

    filter_map = {
        "active": {"is_active": True, "expired": False, "enabled": True, "data_limit_reached": False},
        "disabled": {"enabled": False},
        "expired": {"expired": True},
        "limited": {"data_limit_reached": True, "expired": False},
        "all": {}
    }
    
    api_params = {
        "page": page + 1,
        "size": 10,
        "order_by": "created_at",
        "descending": True
    }
    api_params.update(filter_map.get(status_filter, {}))
    
    pagination_data = await api_client.get_all_users(**api_params)
    
    if not pagination_data or not pagination_data["users"]:
        text = f"ℹ️ No users found with filter: *{status_filter}*"
        builder = InlineKeyboardBuilder()
        builder.button(text="Filter 🔎", callback_data=f"panel:filter_menu:{status_filter}:0")
        builder.button(text="⬅️ Back to Main Menu", callback_data="panel:main_menu")
        builder.adjust(1)
        return await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

    await state.set_state(GeneralPanelFSM.browse_users)
    
    text, keyboard = _create_users_paginator(
        user_list=pagination_data["users"],
        current_page=pagination_data["page"],
        total_pages=pagination_data["pages"],
        status_filter=status_filter
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("panel:filter_menu:"))
async def cb_open_filter_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GeneralPanelFSM.browse_users)
    
    builder = InlineKeyboardBuilder()
    filters = {
        "👥 All Users": "all", "✅ Active": "active", "❌ Disabled": "disabled",
        "⏳ Expired": "expired", "🪫 Limited": "limited"
    }
    for text, status_filter in filters.items():
        builder.button(text=text, callback_data=f"panel:browse_users:{status_filter}:0")
    
    builder.button(text="⬅️ Back to List", callback_data="panel:browse_users:all:0")
    builder.adjust(2)
    
    await callback.message.edit_text("🔎 Please select a status to filter by:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "panel:search_user", GeneralPanelFSM.main_menu)
async def cb_search_user_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GeneralPanelFSM.search_user)
    await state.update_data(panel_message_id=callback.message.message_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="Inline Search 🔎", switch_inline_query_current_chat="")
    builder.button(text="⬅️ Back", callback_data="panel:main_menu")
    builder.adjust(1)
    await callback.message.edit_text("🔍 Send a username or subscription link to search.", reply_markup=builder.as_markup())

@router.callback_query(F.data == "panel:close", GeneralPanelFSM.main_menu)
async def cb_close_panel(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()

@router.callback_query(F.data == "panel:main_menu")
async def cb_back_to_main_menu(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    await state.clear()
    
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        logger.warning(f"Failed to delete message on 'Back': {e}")
        await callback.answer()

    text, keyboard = await _get_dashboard_content(api_client)

    new_panel = await callback.message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await state.set_state(GeneralPanelFSM.main_menu)
    await state.update_data(main_panel_id=new_panel.message_id)

@router.callback_query(F.data.startswith("user:view:"))
async def cb_view_user(callback: CallbackQuery, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    await callback.answer()
    
    parts = callback.data.split(":")
    username = parts[2]
    
    if len(parts) > 3 and "browse_users" in parts[3]:
        back_callback = f"panel:{':'.join(parts[3:])}"
    else:
        back_callback = "panel:main_menu"

    await state.update_data(back_callback=back_callback)
    await state.set_state(GeneralPanelFSM.view_user)

    await _display_user_details(
    bot,
    callback.message.chat.id,
    callback.message.message_id,
    username,
    back_callback,
    api_client
    )

@router.callback_query(F.data.startswith("user:return_to_view:"))
async def cb_return_to_user_view(callback: CallbackQuery, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    await callback.answer()
    username = callback.data.split(":")[2]
    
    fsm_data = await state.get_data() or {}
    back_callback = fsm_data.get("back_callback", "panel:main_menu")
    
    await state.set_state(GeneralPanelFSM.view_user)
    
    await _display_user_details(bot, callback.message.chat.id, callback.message.message_id, username, back_callback, api_client)
