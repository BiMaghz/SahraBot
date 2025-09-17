import logging
import re
import uuid
from typing import Optional, List
from html import escape

from aiogram import F, Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from app.api.marzneshin import MarzneshinAPI, User
from app.core.config import settings
from app.utils.helpers import format_expiry, format_traffic, extract_subscription_data, extract_inline_username
from .helpers import _determine_user_status, _display_user_details
from .states import GeneralPanelFSM

router = Router()
logger = logging.getLogger(__name__)

@router.message(GeneralPanelFSM.search_user)
async def msg_handle_search_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    api_client: MarzneshinAPI
):
    search_text = (message.text or "").strip()
    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    if not panel_message_id:
        await message.answer("❌ Session error. Please /start again.")
        return

    await bot.edit_message_text(
        f"🔍 Searching...",
        chat_id=message.chat.id,
        message_id=panel_message_id,
    )

    user: Optional[User] = None
    username_to_search: str = ""
    
    username_from_inline = extract_inline_username(search_text)
    if username_from_inline:
        user = await api_client.get_user(username_from_inline)
        username_to_search = username_from_inline
    else:
        sub_data = extract_subscription_data(search_text)
        if sub_data:
            sub_username, sub_key = sub_data
            user_info_dict = await api_client.get_sub_info(sub_username, sub_key)
            if user_info_dict:
                user = User(**user_info_dict)
            username_to_search = sub_username
        else:
            username_to_search = search_text.splitlines()[0]
            if username_to_search:
                user = await api_client.get_user(username_to_search)

    if user:
        await state.set_state(GeneralPanelFSM.view_user)
        back_callback = "panel:main_menu"
        await _display_user_details(
            bot, message.chat.id, panel_message_id, user.username, back_callback, api_client
        )
    else:
        builder = InlineKeyboardBuilder().button(
            text="⬅️ Back", callback_data="panel:main_menu"
        )
        await bot.edit_message_text(
            f"❌ *User not found:* `{escape(username_to_search)}`",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

@router.inline_query(F.from_user.id.in_(settings.admin_chat_ids))
async def inline_search_handler(inline_query: InlineQuery, api_client: MarzneshinAPI):
    query_text = inline_query.query.strip()

    if not query_text:
        await inline_query.answer([], cache_time=1, switch_pm_text="🔎 Type a username...", switch_pm_parameter="start")
        return

    api_params = {"size": 50}
    
    admin_search_pattern = re.match(r"admin=(\w+)\s+(.+)", query_text, re.IGNORECASE)
    admin_only_pattern = re.match(r"admin=(\w+)", query_text, re.IGNORECASE)

    if admin_search_pattern:
        owner, search_term = admin_search_pattern.groups()
        api_params["owner_username"] = owner
        api_params["username"] = search_term
    elif admin_only_pattern:
        owner = admin_only_pattern.groups()[0]
        api_params["owner_username"] = owner
    else:
        api_params["username"] = query_text
    
    pagination_data = await api_client.get_all_users(**api_params)
    
    if not pagination_data or not pagination_data["users"]:
        not_found_article = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="❌ No users found",
                description="No results match your search",
                input_message_content=InputTextMessageContent(
                    message_text="❌ No users found."
                )
            )
        ]
        return await inline_query.answer(not_found_article, cache_time=1)
    
    results = pagination_data["users"]

    articles: List[InlineQueryResultArticle] = []
    for user in results:
        if not isinstance(user, User):
            continue

        emoji, status_text = _determine_user_status(user)
        
        limit_str = "Unlimited" if user.data_limit == 0 else format_traffic(user.data_limit)
        used_str = format_traffic(user.used_traffic)
        expire_str = format_expiry(user.expire_date)

        caption = (
            f"🔤 *Username*: `{escape(user.username)}`\n\n"
            f"🔗 *Sub Link*: `{escape(user.subscription_url)}`"
        )
        
        input_content = InputTextMessageContent(
            message_text=caption,
            parse_mode="Markdown"
        )
        
        articles.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=f"{emoji} {user.username}",
                description=f"📊 {used_str} / {limit_str} | ⏳ {expire_str}",
                input_message_content=input_content,
                thumbnail_url="https://img.icons8.com/fluency/48/user-male-circle--v1.png"
            )
        )

    await inline_query.answer(articles, cache_time=5, is_personal=True)
