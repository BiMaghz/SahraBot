import logging
from html import escape
from typing import List, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from .states import GeneralPanelFSM, UserEditFSM
from app.api.marzneshin import User, MarzneshinAPI
from app.utils.helpers import (
    format_expiry, format_time_ago,
    format_traffic, generate_qr_code
)

logger = logging.getLogger(__name__)

async def _get_dashboard_content(
    api_client: MarzneshinAPI,
) -> Tuple[str, InlineKeyboardMarkup]:

    traffic_stats = await api_client.get_system_traffic_stats()
    user_stats = await api_client.get_system_users_stats()

    traffic_text = "📊 Traffic Usage: _Not Available_"
    if traffic_stats:
        total_traffic = format_traffic(traffic_stats.total)
        traffic_text = f"📦 *Traffic Usage*\n↕️ Total: {total_traffic}"

    users_text = "👤 Users: _Not Available_"
    if user_stats:
        users_text = (
            f"👤 *Users*\n"
            f"👥 Total: {user_stats.total}\n"
            f"✅ Active: {user_stats.active}\n"
            f"🟢 Online: {user_stats.online}\n"
            f"⏸️ On Hold: {user_stats.on_hold}\n"
            f"⌛️ Expired: {user_stats.expired}\n"
            f"🪫 Limited: {user_stats.limited}"
        )

    text = (
        f"📊 *SahraBot Dashboard*\n"
        f"━━━━━━━━━━━━━━\n{users_text}\n"
        f"━━━━━━━━━━━━━━\n{traffic_text}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Create User", callback_data="panel:create_user")
    builder.button(text="👥 All Users", callback_data="panel:browse_users:all:0")
    builder.button(text="🔍 Search User", callback_data="panel:search_user")
    builder.button(text="✖️ Close", callback_data="panel:close")
    builder.adjust(1, 2, 1)

    return text, builder.as_markup()

def _get_user_details_content(user: User, back_callback: str) -> Tuple[str, InlineKeyboardMarkup]:
    status_emoji, status_text = _determine_user_status(user)
    data_limit_str = "Unlimited" if user.data_limit == 0 else format_traffic(user.data_limit)
    data_used_str = f"{format_traffic(user.used_traffic)} used"

    text = (
        f"{status_emoji} *User:* `{escape(user.username)}`\n"
        f"*Status:* {status_text}\n\n"
        f"🔋 *Data limit:* {data_limit_str}\n"
        f"📶 *Data Used:* {data_used_str}\n"
        f"📅 *Expiry Date:* {format_expiry(user.expire_date)}\n\n"
        f"🔄 *Subscription updated at:* {format_time_ago(user.sub_updated_at)}\n"
        f"🔌 *Last seen online:* {format_time_ago(user.online_at)}\n"
        f"📱 *Last agent:* `{escape(user.sub_last_user_agent or '-')}`\n\n"
        f"📝 *Note:* {escape(user.note or '-')}\n"
        f"👨‍💻 *Admin:* {escape(user.owner_username or 'None')}\n\n"
        f"🔗 *Subscription:*\n`{escape(user.subscription_url)}`"
    )

    builder = InlineKeyboardBuilder()
    if user.enabled:
        builder.button(text="🚫 Disable", callback_data=f"user:toggle_enable:{user.username}")
    else:
        builder.button(text="✅ Enable", callback_data=f"user:toggle_enable:{user.username}")

    builder.button(text="✏️ Edit", callback_data=f"user:edit_menu:{user.username}")
    builder.button(text="🔄 Renew", callback_data=f"user:renew_menu:{user.username}")
    builder.button(text="🔗 QR/Link", callback_data=f"user:links:{user.username}")
    builder.button(text="♻️ Revoke SUB", callback_data=f"user:revoke:{user.username}")
    builder.button(text="🗑️ Delete", callback_data=f"user:delete_confirm:{user.username}")

    back_text = "⬅️ Back to List" if "browse_users" in back_callback else "⬅️ Back to Menu"
    builder.button(text=back_text, callback_data=back_callback)
    builder.adjust(2, 2, 2, 1)

    return text, builder.as_markup()

def _create_users_paginator(
    user_list: List[User], current_page: int, total_pages: int, status_filter: str
) -> Tuple[str, InlineKeyboardMarkup]:
    
    status_titles = {
        "all": "👥 All Users", "active": "✅ Active Users", "disabled": "❌ Disabled Users",
        "expired": "⏳ Expired Users", "limited": "🪫 Limited Users",
    }
    title = status_titles.get(status_filter, "👥 Users")
    text = f"*{title} - Page {current_page} / {total_pages}*"
    
    builder = InlineKeyboardBuilder()
    for user in user_list:
        emoji, _ = _determine_user_status(user)
        callback_page_index = current_page - 1
        builder.button(
            text=f"{emoji} {escape(user.username)}",
            callback_data=f"user:view:{user.username}:browse_users:{status_filter}:{callback_page_index}"
        )
    
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"panel:browse_users:{status_filter}:{current_page - 2}"))
        
    if current_page == 1:
        if status_filter == "expired":
            nav_row.append(InlineKeyboardButton(text="🗑️ Del Expired", callback_data="delete_flow:start_expired"))

        nav_row.append(InlineKeyboardButton(text="Filter 🔎", callback_data=f"panel:filter_menu:{status_filter}:0"))
        
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"panel:browse_users:{status_filter}:{current_page}"))

    if nav_row:
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="panel:main_menu"))
    builder.adjust(1)

    return text, builder.as_markup()

async def _display_user_details(
    bot: Bot,
    chat_id: int,
    message_id: int,
    username: str,
    back_callback: str,
    api_client: MarzneshinAPI,
):
    api_params = {"username": username}

    user = await api_client.get_user(**api_params)
    if not user:
        await bot.edit_message_text(
            "❌ Could not fetch user details.",
            chat_id=chat_id,
            message_id=message_id
        )
        return

    text, keyboard = _get_user_details_content(user, back_callback)
    try:
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.warning(f"Error editing message in _display_user_details: {e}")

async def _send_user_subscription_info(
    message: Message,
    bot: Bot,
    username: str,
    api_client: MarzneshinAPI,
):
    api_params = {"username": username}

    user = await api_client.get_user(**api_params)
    if not user:
        await message.answer("❌ Could not fetch user details to generate links.")
        return

    status_emoji, status_text = _determine_user_status(user)
    data_limit_str = "Unlimited" if user.data_limit == 0 else format_traffic(user.data_limit)

    caption = (
        f"{status_emoji} Status: *{status_text}*\n\n"
        f"🔤 *Username:* `{escape(user.username)}`\n"
        f"🔋 *Data limit:* {data_limit_str}\n"
        f"📅 *Expiry Date:* {format_expiry(user.expire_date)}\n\n"
        f"🚀 *Subscription:* `{escape(user.subscription_url)}`"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Open Subscription Link", url=user.subscription_url)

    qr_img = generate_qr_code(user.subscription_url)
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=BufferedInputFile(qr_img.getvalue(), "subscription.png"),
        caption=caption,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

def _determine_user_status(user: User) -> Tuple[str, str]:
    if not user.enabled: return "❌", "Disabled"
    if user.expired: return "⌛️", "Expired"
    if user.data_limit_reached: return "🪫", "Limited"
    if user.is_active: return "✅", "Active"
    return "⏸️", "Inactive"

async def _display_service_selection(
    message: Message,
    state: FSMContext,
    api_client: MarzneshinAPI,
):
    await state.set_state(UserEditFSM.waiting_for_services)
    fsm_data = await state.get_data() or {}
    username = fsm_data.get("username")

    api_params = {}

    all_services = await api_client.get_services(**api_params)
    if not all_services:
        return await message.edit_text("❌ No services are configured on the panel.")

    selected_service_ids = fsm_data.get("selected_service_ids")
    if selected_service_ids is None:
        user = await api_client.get_user(username, **api_params)
        selected_service_ids = set(user.service_ids)
        await state.update_data(selected_service_ids=list(selected_service_ids))

    builder = InlineKeyboardBuilder()
    for service in all_services:
        is_selected = service.id in selected_service_ids
        text = f"{'✅' if is_selected else '☑️'} {service.name}"
        builder.button(text=text, callback_data=f"user_edit_service:toggle:{service.id}")
    
    builder.button(text="💾 Save Changes", callback_data="user_edit_service:save")
    builder.button(text="⬅️ Cancel", callback_data=f"user:edit_menu:{username}")
    builder.adjust(1)
    
    try:
        await message.edit_text(
            f"🔧 *Select Services for:* `{escape(username)}`",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error while displaying service selection: {e}")

async def _apply_user_update(
    message: Message,
    state: FSMContext,
    bot: Bot,
    username: str,
    payload: dict,
    api_client: MarzneshinAPI,
    is_callback: bool = False
):
    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")
    
    if is_callback:
        panel_message = message
    elif panel_message_id:
        panel_message = await bot.edit_message_text(
            f"⏳ Updating `{escape(username)}`...",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            parse_mode="Markdown"
        )
    else:
        panel_message = await bot.send_message(
            message.chat.id,
            f"⏳ Updating `{escape(username)}`...",
            parse_mode="Markdown"
        )

    payload["username"] = username

    update_success = await api_client.update_user(username, payload)

    if not update_success:
        await panel_message.edit_text("❌ An error occurred while updating the user.")
    
    await state.set_state(GeneralPanelFSM.view_user)
    back_callback = fsm_data.get("back_callback", "panel:main_menu")

    await _display_user_details(
        bot,
        panel_message.chat.id,
        panel_message.message_id,
        username,
        back_callback,
        api_client
    )