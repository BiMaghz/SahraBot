import logging
from html import escape
from datetime import datetime, timezone, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from app.api.marzneshin import MarzneshinAPI
from app.core.config import settings
from app.utils.helpers import (
    generate_random_username, parse_duration_to_datetime,
    validate_username
)
from .helpers import (
    _display_user_details, _send_user_subscription_info,
    _display_service_selection, _apply_user_update
)
from .states import UserCreationFSM, GeneralPanelFSM, UserRenewalFSM, DeleteFlowFSM, UserEditFSM

router = Router()
router.message.filter(F.from_user.id.in_(settings.admin_chat_ids))
router.callback_query.filter(F.from_user.id.in_(settings.admin_chat_ids))

logger = logging.getLogger(__name__)

# --- User Creation ---

@router.callback_query(F.data == "panel:create_user", GeneralPanelFSM.main_menu)
async def cb_create_user_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserCreationFSM.waiting_for_username)
    await state.update_data(panel_message_id=callback.message.message_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎲 Random Username", callback_data="user_create:random_username")
    builder.button(text="⬅️ Cancel", callback_data="panel:main_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "👤 *Create New User | Step 1 of 3*\n\n"
        "Please send the desired *username*.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(UserCreationFSM.waiting_for_username, F.data == "user_create:random_username")
async def cb_random_username(callback: CallbackQuery, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    await callback.answer("🎲 Generating...")
    
    while True:
        username = generate_random_username()
        existing_user = await api_client.get_user(username)
        if not existing_user:
            break
            
    await state.update_data(username=username)
    await state.set_state(UserCreationFSM.waiting_for_data_and_expiry)

    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Cancel", callback_data="panel:main_menu")

    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=panel_message_id,
        text=(
            f"👤 *Create New User | Step 2 of 3*\n\n"
            f"Username: `{escape(username)}`\n\n"
            f"Now, please send the *data limit* and *expiry duration*.\n"
            f"*Examples:*\n"
            f"- `30g 30d` (30 GB for 30 days)\n"
            f"- `0 1m` (Unlimited data for 1 month)"
        ),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.message(UserCreationFSM.waiting_for_username)
async def msg_username_input(message: Message, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    await message.delete()
    username = message.text.strip()
    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")

    back_button_keyboard = InlineKeyboardBuilder().button(text="⬅️ Cancel", callback_data="panel:main_menu").as_markup()

    if not validate_username(username):
        await bot.edit_message_text(
            "❌ Invalid username format. Please try again.",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            reply_markup=back_button_keyboard
        )
        return

    existing_user = await api_client.get_user(username)
    if existing_user:
        await bot.edit_message_text(
            f"❌ Username `{escape(username)}` already exists. Please choose another.",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            reply_markup=back_button_keyboard,
            parse_mode="Markdown"
        )
        return

    await state.update_data(username=username)
    await state.set_state(UserCreationFSM.waiting_for_data_and_expiry)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Cancel", callback_data="panel:main_menu")

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=panel_message_id,
        text=(
            f"👤 *Create New User | Step 2 of 3*\n\n"
            f"*Username:* `{escape(username)}`\n\n"
            f"Now, please send the *data limit* and *expiry duration*.\n"
            f"*Examples:*\n"
            f"- `30g 30d` (30 GB for 30 days)\n"
            f"- `0 1m` (Unlimited data for 1 month)"
        ),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.message(UserCreationFSM.waiting_for_data_and_expiry)
async def msg_handle_data_expiry(message: Message, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    await message.delete()
    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")

    parts = message.text.lower().strip().split()
    if len(parts) != 2:
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Cancel", callback_data="panel:main_menu")
        await bot.edit_message_text(
            "❌ Invalid format. Please provide both data limit and expiry. Example: `30g 60d`",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        return

    data_limit_str, expire_str = parts
    try:
        if data_limit_str == "0":
            data_limit_bytes = 0
        else:
            unit = data_limit_str[-1]
            value = int(data_limit_str[:-1])
            if unit == "g":
                data_limit_bytes = value * (1024 ** 3)
            elif unit == "t":
                data_limit_bytes = value * (1024 ** 4)
            else:
                raise ValueError
    except (ValueError, IndexError):
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Cancel", callback_data="panel:main_menu")
        await bot.edit_message_text(
            "❌ Invalid data limit format. Use *g* for GB, *t* for TB, or *0* for unlimited.",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        return

    await state.update_data(data_limit_bytes=data_limit_bytes, expire_str=expire_str)

    if expire_str in ("0", "0d"):
        await state.update_data(expire_strategy="never")
        await _display_service_selection_for_create(message, state, bot, api_client)
    else:
        await state.set_state(UserCreationFSM.waiting_for_expire_type)
        builder = InlineKeyboardBuilder()
        builder.button(text="🪧 Fixed Date", callback_data="user_expire_type:fixed_date")
        builder.button(text="▶️ On First Use", callback_data="user_expire_type:start_on_first_use")
        builder.button(text="⬅️ Cancel", callback_data="panel:main_menu")
        builder.adjust(1)
        await bot.edit_message_text(
            "👤 *Create New User | Step 2.5 of 3*\n\nPlease select the expiration type:",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

@router.callback_query(UserCreationFSM.waiting_for_expire_type, F.data.startswith("user_expire_type:"))
async def cb_handle_expire_type(callback: CallbackQuery, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    expire_strategy = callback.data.split(":")[1]
    await state.update_data(expire_strategy=expire_strategy)
    await _display_service_selection_for_create(callback.message, state, bot, api_client)

async def _display_service_selection_for_create(
    message: Message,
    state: FSMContext,
    bot: Bot, 
    api_client: MarzneshinAPI
):
    await state.set_state(UserCreationFSM.waiting_for_services)
    
    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")
    
    api_params = {}

    all_services = await api_client.get_services(**api_params)
    if not all_services:
        await message.answer("⚠️ No services found on the panel. Creating user without services.")
        await finalize_user_creation(message, state, bot, api_client)
        return
        
    fsm_data = await state.get_data() or {}
    selected_service_ids = fsm_data.get("service_ids", set())

    builder = InlineKeyboardBuilder()
    for service in all_services:
        is_selected = service.id in selected_service_ids
        text = f"{'✅' if is_selected else '☑️'} {service.name}"
        builder.button(text=text, callback_data=f"user_create_service:toggle:{service.id}")
    
    builder.button(text="✅ Create User", callback_data="user_create_service:save")
    builder.button(text="⬅️ Cancel", callback_data="panel:main_menu")
    builder.adjust(1)

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=panel_message_id,
        text=(
            f"👤 *Create New User | Step 3 of 3*\n\n"
            f"Finally, select the *services* for this user."
        ),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(UserCreationFSM.waiting_for_services, F.data.startswith("user_create_service:"))
async def cb_handle_service_toggle(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    action = callback.data.split(":")[1]
    fsm_data = await state.get_data() or {}
    
    selected_service_ids = set(fsm_data.get("service_ids", []))

    if action == "toggle":
        service_id = int(callback.data.split(":")[2])
        if service_id in selected_service_ids:
            selected_service_ids.remove(service_id)
        else:
            selected_service_ids.add(service_id)
        
        await state.update_data(service_ids=list(selected_service_ids))
        await _display_service_selection_for_create(callback.message, state, callback.bot, api_client)

    elif action == "save":
        if not selected_service_ids:
            await callback.answer("❌ At least one service is required.", show_alert=True)
            return

        await callback.message.edit_text("⏳ Creating user, please wait...")
        await finalize_user_creation(callback.message, state, api_client)

async def finalize_user_creation(message: Message, state: FSMContext, api_client: MarzneshinAPI):
    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")
    expire_strategy = fsm_data.get("expire_strategy")
    
    payload = {
        "username": fsm_data.get('username'),
        "data_limit": fsm_data.get('data_limit_bytes', 0),
        "service_ids": list(fsm_data.get('service_ids', set())),
        "expire_strategy": expire_strategy,
    }

    if expire_strategy == "fixed_date" or expire_strategy == "start_on_first_use":
        expire_str = fsm_data.get("expire_str")
        expire_dt = parse_duration_to_datetime(expire_str)
        
        if expire_strategy == "fixed_date":
            payload["expire_date"] = expire_dt.isoformat()
        else:
            now = datetime.now(timezone.utc)
            payload["usage_duration"] = int((expire_dt - now).total_seconds())
    
    new_user = await api_client.create_user(payload)

    if new_user:
        await state.set_state(GeneralPanelFSM.view_user)
        back_callback = "panel:main_menu"
        await _display_user_details(message.bot, message.chat.id, panel_message_id, new_user.username, back_callback, api_client)
    else:
        await message.bot.edit_message_text("❌ Failed to create user. The username might already exist or the payload was invalid.", chat_id=message.chat.id, message_id=panel_message_id)
    
    await state.clear()

# --- User Management ---

@router.callback_query(F.data.startswith("user:toggle_enable:"))
async def cb_toggle_user_enable(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    api_client: MarzneshinAPI
):
    username = callback.data.split(":")[2]
    await callback.answer("⏳ Toggling status...")

    api_params = {"username": username}

    user = await api_client.get_user(**api_params)
    if not user:
        return await callback.answer("❌ User not found.", show_alert=True)

    if user.enabled:
        success = await api_client.disable_user(**api_params)
        new_status_text = "Disabled"
    else:
        success = await api_client.enable_user(**api_params)
        new_status_text = "Enabled"

    if success:
        await callback.answer(f"✅ Status set to {new_status_text}")
    else:
        await callback.answer("❌ Failed to update status.", show_alert=True)

    fsm_data = await state.get_data() or {}
    back_callback = fsm_data.get("back_callback", "panel:main_menu")

    await _display_user_details(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        username,
        back_callback,
        api_client
    )

@router.callback_query(F.data.startswith("user:links:"))
async def cb_user_links(callback: CallbackQuery, bot: Bot, api_client: MarzneshinAPI):
    username = callback.data.split(":")[2]
    await callback.answer("✅ Sending subscription info...")
    await _send_user_subscription_info(callback.message, bot, username, api_client)

@router.callback_query(F.data.startswith("user:delete_confirm:"))
async def cb_delete_user_confirm(callback: CallbackQuery):
    username = callback.data.split(":")[2]

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yes, Delete", callback_data=f"user:delete_execute:{username}")
    builder.button(text="❌ No, Cancel", callback_data=f"user:return_to_view:{username}")

    await callback.message.edit_text(
        f"⚠️ *Are you sure you want to permanently delete user* `{escape(username)}`?\n\n_This action cannot be undone._",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

@router.callback_query(F.data.startswith("user:delete_execute:"))
async def cb_delete_user_execute(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    username = callback.data.split(":")[2]
    fsm_data = await state.get_data() or {}
    back_callback = fsm_data.get("back_callback", "panel:main_menu")
    await callback.answer(f"⏳ Deleting user {username}...")

    success = await api_client.delete_user(username)
    
    if success:
        text = f"✅ User `{escape(username)}` has been deleted."
        builder = InlineKeyboardBuilder()

        if "browse_users" in back_callback:
            builder.button(text="⬅️ Back to User List", callback_data=back_callback)
        else:
            builder.button(text="⬅️ Back to Main Menu", callback_data="panel:main_menu")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await callback.answer("❌ Failed to delete the user.", show_alert=True)
        await _display_user_details(callback.bot, callback.message.chat.id, callback.message.message_id, username, back_callback)

@router.callback_query(F.data.startswith("user:revoke:"))
async def cb_revoke_user_confirm(callback: CallbackQuery):
    username = callback.data.split(":")[2]
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yes, Revoke", callback_data=f"user:revoke_execute:{username}")
    builder.button(text="❌ No, Cancel", callback_data=f"user:return_to_view:{username}")

    await callback.message.edit_text(
        f"⚠️ *Are you sure you want to revoke and regenerate the subscription link for* `{escape(username)}`?\n\n_The old link will stop working._",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

@router.callback_query(F.data.startswith("user:revoke_execute:"))
async def cb_revoke_user_execute(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    api_client: MarzneshinAPI
):
    username = callback.data.split(":")[2]
    await callback.answer(f"⏳ Revoking link for {username}...")

    api_params = {"username": username}

    success = await api_client.revoke_sub(**api_params)
    if success:
        await callback.answer("✅ Subscription link has been revoked.", show_alert=True)
    else:
        await callback.answer("❌ Failed to revoke the link.", show_alert=True)

    fsm_data = await state.get_data() or {}
    back_callback = fsm_data.get("back_callback", "panel:main_menu")

    await _display_user_details(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        username,
        back_callback,
        api_client
    )

@router.callback_query(F.data.startswith("user:renew_menu:"))
async def cb_renew_user_start(callback: CallbackQuery, state: FSMContext):
    username = callback.data.split(":")[2]

    await state.set_state(UserRenewalFSM.waiting_for_data_and_expiry)
    await state.update_data(username=username, panel_message_id=callback.message.message_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Cancel", callback_data=f"user:return_to_view:{username}")

    await callback.message.edit_text(
        f"🔄 *Renewing for:* `{escape(username)}`\n\n"
        "Please send the new *data limit* and *expiry duration*.\n\n"
        "*Examples:*\n"
        "`30g 60d` (30 GB for 60 days)\n"
        "`100g 0` (100 GB, no change in expiry)\n"
        "`0 30d` (Unlimited data for 30 days)",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.message(UserRenewalFSM.waiting_for_data_and_expiry)
async def msg_renew_user_data(
    message: Message,
    state: FSMContext,
    bot: Bot,
    api_client: MarzneshinAPI
):
    fsm_data = await state.get_data() or {}
    username = fsm_data.get("username")
    panel_message_id = fsm_data.get("panel_message_id")
    back_callback = fsm_data.get("back_callback", "panel:main_menu")
    
    await message.delete()

    if not all([username, panel_message_id]):
        await bot.edit_message_text(
            "❌ Session error. Please try again.",
            chat_id=message.chat.id,
            message_id=panel_message_id
        )
        return await state.clear()
    
    parts = message.text.lower().strip().split()
    if len(parts) != 2:
        error_text = "❌ Invalid format. Please provide both data limit and expiry. Example: 30g 60d"
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Cancel", callback_data=f"user:view:{username}:panel:main_menu:all:0")
        await bot.edit_message_text(
        error_text,
        chat_id=message.chat.id,
        message_id=panel_message_id,
        reply_markup=builder.as_markup()
        )
        return

    data_limit_str, expire_str = parts
    data_limit_bytes = -1
    expire_datetime = None
    is_valid = True

    try:
        if data_limit_str == "0":
            data_limit_bytes = 0
        else:
            unit = data_limit_str[-1]
            value = int(data_limit_str[:-1])
            if unit == "g": data_limit_bytes = value * (1024 ** 3)
            elif unit == "t": data_limit_bytes = value * (1024 ** 4)
            else: is_valid = False
    except (ValueError, IndexError):
        is_valid = False

    if not is_valid:
        await bot.edit_message_text(
            "❌ Invalid data limit format. Example: `30g` or `0`.",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            parse_mode="Markdown"
        )
        return
    
    if expire_str != "0":
        expire_datetime = parse_duration_to_datetime(expire_str)
        if expire_datetime is None:
            await bot.edit_message_text(
                "❌ Invalid expiry format. Example: `60d` or `2025-12-31` or `0`.",
                chat_id=message.chat.id,
                message_id=panel_message_id,
                parse_mode="Markdown"
            )
            return

    await bot.edit_message_text(
        f"⏳ Renewing `{username}`...",
        chat_id=message.chat.id,
        message_id=panel_message_id,
        parse_mode="Markdown"
    )

    api_params = {"username": username}

    current_user = await api_client.get_user(**api_params)
    if not current_user:
        await bot.edit_message_text(
            "❌ User not found.",
            chat_id=message.chat.id,
            message_id=panel_message_id
        )
        return await state.clear()
        
    payload = {"username": username}

    if expire_str == "0":
        payload["expire_strategy"] = "never"
        payload["expire_date"] = None
    else:
        payload["expire_strategy"] = "fixed_date"
        payload["expire_date"] = expire_datetime.isoformat()

    if data_limit_bytes != current_user.data_limit:
        payload["data_limit"] = data_limit_bytes

    update_success = await api_client.update_user(username, payload)
    reset_success = await api_client.reset_usage(username)

    if update_success and reset_success:
        await bot.edit_message_text(
            f"✅ User `{username}` successfully renewed.",
            chat_id=message.chat.id,
            message_id=panel_message_id,
            parse_mode="Markdown"
        )
    else:
        await bot.edit_message_text(
            "❌ Failed to renew User.",
            chat_id=message.chat.id,
            message_id=panel_message_id
        )

    await _display_user_details(bot, message.chat.id, panel_message_id, username, back_callback, api_client)

# --- Edit Data, Date, Note, Services ---

@router.callback_query(F.data.startswith("user:edit_menu:"))
async def cb_start_user_edit(callback: CallbackQuery, state: FSMContext):
    username = callback.data.split(":")[2]
    await state.update_data(username=username, selected_service_ids=None)
    await state.set_state(UserEditFSM.menu)

    builder = InlineKeyboardBuilder()
    builder.button(text="📶 Data Limit", callback_data=f"user_edit:data_limit")
    builder.button(text="📅 Expiry", callback_data=f"user_edit:expiry")
    builder.button(text="📝 Note", callback_data=f"user_edit:note")
    builder.button(text="🔧 Services", callback_data=f"user_edit:services")
    builder.button(text="⬅️ Back", callback_data=f"user:return_to_view:{username}")
    builder.adjust(2, 2, 1)

    try:
        await callback.message.edit_text(
            f"🛠️ *Editing user:* `{escape(username)}`\nSelect a field to modify:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_start_user_edit: {e}")
    await callback.answer()

@router.callback_query(UserEditFSM.menu, F.data.startswith("user_edit:"))
async def cb_handle_edit_menu_selection(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    action = callback.data.split(":")[1]
    fsm_data = await state.get_data() or {}
    username = fsm_data.get("username")

    prompts = {
        "data_limit": "📶 Enter new *Data Limit*. Examples: `50g` (50 GB), `0` (unlimited).",
        "expiry": "📅 Enter new *Expiry*. Examples: `30d`, `2025-12-31`, `0` (never).",
        "note": "📝 Send the new *Note* for this user.",
    }

    if action in prompts:
        target_state = getattr(UserEditFSM, f"waiting_for_{action}")
        await state.set_state(target_state)
        await state.update_data(panel_message_id=callback.message.message_id)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Cancel", callback_data=f"user:edit_menu:{username}")
        
        await callback.message.edit_text(prompts[action], reply_markup=builder.as_markup(), parse_mode='Markdown')
    
    elif action == "services":
        await _display_service_selection(callback.message, state, api_client)
    else:
        await callback.answer("Unknown action.", show_alert=True)

@router.message(UserEditFSM.waiting_for_data_limit)
async def msg_edit_data_limit(message: Message, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    fsm_data = await state.get_data() or {}
    username = fsm_data.get("username")
    panel_message_id = fsm_data.get("panel_message_id")
    await message.delete()
    
    try:
        data_limit_str = message.text.lower().strip()
        if data_limit_str == '0':
            data_limit_bytes = 0
        else:
            unit = data_limit_str[-1]
            value = int(data_limit_str[:-1])
            if unit == 'g': data_limit_bytes = value * (1024 ** 3)
            elif unit == 't': data_limit_bytes = value * (1024 ** 4)
            else: raise ValueError("Invalid unit")
        
        payload = {"data_limit": data_limit_bytes}
        await _apply_user_update(message, state, bot, username, payload, api_client)

    except (ValueError, IndexError):
        error_text = "❌ Invalid format. Use 'g' for GB, 't' for TB, or '0' for unlimited."
        builder = InlineKeyboardBuilder().button(text="⬅️ Cancel", callback_data=f"user:edit_menu:{username}")
        await bot.edit_message_text(error_text, chat_id=message.chat.id, message_id=panel_message_id, reply_markup=builder.as_markup())


@router.message(UserEditFSM.waiting_for_expiry)
async def msg_edit_expiry(message: Message, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    fsm_data = await state.get_data() or {}
    username = fsm_data.get("username")
    panel_message_id = fsm_data.get("panel_message_id")
    await message.delete()

    expire_datetime = parse_duration_to_datetime(message.text)
    
    if expire_datetime is not None or message.text.strip() == '0':
        payload = {"expire_date": expire_datetime.isoformat() if expire_datetime else None}
        if message.text.strip() == '0':
            payload["expire_strategy"] = "never"
        else:
            payload["expire_strategy"] = "fixed_date"
            
        await _apply_user_update(message, state, bot, username, payload, api_client)
    else:
        error_text = "❌ Invalid format. Use `30d`, `3m`, `2025-12-31`, or `0`."
        builder = InlineKeyboardBuilder().button(text="⬅️ Cancel", callback_data=f"user:edit_menu:{username}")
        await bot.edit_message_text(error_text, chat_id=message.chat.id, message_id=panel_message_id, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.message(UserEditFSM.waiting_for_note)
async def msg_edit_note(message: Message, state: FSMContext, bot: Bot, api_client: MarzneshinAPI):
    fsm_data = await state.get_data() or {}
    username = fsm_data.get("username")
    await message.delete()

    payload = {"note": message.text.strip()}
    await _apply_user_update(message, state, bot, username, payload, api_client)

@router.callback_query(UserEditFSM.waiting_for_services, F.data.startswith("user_edit_service:"))
async def cb_handle_service_selection(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    action = callback.data.split(":")[1]
    fsm_data = await state.get_data() or {}
    username = fsm_data.get("username")
    selected_service_ids = set(fsm_data.get("selected_service_ids", []))

    if action == "toggle":
        service_id = int(callback.data.split(":")[2])
        if service_id in selected_service_ids:
            selected_service_ids.remove(service_id)
        else:
            selected_service_ids.add(service_id)
        
        await state.update_data(selected_service_ids=list(selected_service_ids))
        await _display_service_selection(callback.message, state, api_client)

    elif action == "save":
        if not selected_service_ids:
            await callback.answer("❌ At least one service is required.", show_alert=True)
            return
        payload = {"service_ids": list(selected_service_ids)}
        await _apply_user_update(callback.message, state, callback.bot, username, payload, api_client, is_callback=True)

# --- Delete Expired Users ---

@router.callback_query(F.data == "delete_flow:start_expired")
async def cb_start_delete_expired(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DeleteFlowFSM.waiting_for_duration)
    
    await state.update_data(panel_message_id=callback.message.message_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Cancel", callback_data="panel:browse_users:expired:0")
    
    await callback.message.edit_text(
        "🗑️ *Delete Expired Users*\n\n"
        "Please specify the timeframe. Users expired for more than this duration will be deleted.\n\n"
        "Example: `30d` (for 30 days), `0d` (for all)",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.message(DeleteFlowFSM.waiting_for_duration)
async def msg_delete_expired_duration(message: Message, state: FSMContext, bot: Bot):
    await message.delete()
    duration_str = message.text.strip()
    
    fsm_data = await state.get_data() or {}
    panel_message_id = fsm_data.get("panel_message_id")

    if not (duration_str.endswith('d') and duration_str[:-1].isdigit()):
        await bot.edit_message_text("❌ Invalid format. Please send a duration like `30d`.", chat_id=message.chat.id, message_id=panel_message_id)
        return

    days = int(duration_str[:-1])
    delta = timedelta(days=days)
    passed_time_dt = datetime.now(timezone.utc) - delta
    passed_time_ts = int(passed_time_dt.timestamp())
    
    await state.update_data(passed_time=passed_time_ts)
    await state.set_state(DeleteFlowFSM.confirm_delete_expired)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Yes, Delete", callback_data="delete_flow:confirm_expired")
    builder.button(text="❌ No, Cancel", callback_data="panel:browse_users:expired:0")
    builder.adjust(1)
    
    await bot.edit_message_text(
        text=f"⚠️ *FINAL WARNING!*\n\nThis will permanently delete all users who expired more than *{days} days ago*.\n\n_This action cannot be undone._ Are you sure?",
        chat_id=message.chat.id,
        message_id=panel_message_id,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(DeleteFlowFSM.confirm_delete_expired, F.data == "delete_flow:confirm_expired")
async def cb_confirm_delete_expired(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    await callback.message.edit_text("⏳ Deleting expired users, please wait...")
    
    fsm_data = await state.get_data() or {}
    passed_time = fsm_data.get("passed_time")
    
    if passed_time is None:
        await callback.answer("❌ Session error. Please try again.", show_alert=True)
        return

    result = await api_client.delete_expired_users(passed_time=passed_time)
    await state.clear()

    if result:
        if result.get("detail") == "No expired user found.":
            text = "ℹ️ No expired users matching the criteria were found to delete."
        elif "count" in result:
            text = f"✅ Successfully deleted {result['count']} expired users."
        else:
            text = "✅ Operation completed."
    else:
        text = "❌ An error occurred while trying to delete expired users."

    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back to List", callback_data="panel:browse_users:expired:0")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())