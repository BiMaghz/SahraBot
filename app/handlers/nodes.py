import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.api.marzneshin import MarzneshinAPI
from app.core.config import settings
from app.handlers.states import NodeFSM
from app.monitoring.state_manager import state_manager

logger = logging.getLogger(__name__)
router = Router()

router.callback_query.filter(F.from_user.id.in_(settings.admin_chat_ids))

STATUS_EMOJI = {
    "healthy": "💚",
    "unhealthy": "💔",
    "disabled": "❌"
}

@router.callback_query(F.data == "nodes:menu")
async def cb_nodes_menu(callback: CallbackQuery, state: FSMContext, api_client: MarzneshinAPI):
    
    await state.set_state(NodeFSM.menu)
    await callback.answer("Fetching node list...")
    
    nodes_list = await api_client.get_nodes(size=100)
    
    text_lines = ["🛰️ *Nodes List*\n━━━━━━━━━━━━━━"]
    builder = InlineKeyboardBuilder()
    
    if nodes_list and nodes_list.items:
        for node in nodes_list.items:
            emoji = STATUS_EMOJI.get(node.status, "❓")
            text_lines.append(f"{emoji} *{node.name}* (`{node.status}`)")
    else:
        text_lines.append("_No nodes found or access denied._")
    
    builder.row(InlineKeyboardButton(text="📊 Node Monitoring", callback_data="nodes:monitoring_menu"))
    builder.row(InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="panel:main_menu"))
    
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
@router.callback_query(F.data == "nodes:monitoring_menu")
async def cb_monitoring_menu(callback: CallbackQuery, state: FSMContext):
        
    await state.set_state(NodeFSM.monitoring_menu)
    
    is_enabled = await state_manager.is_monitoring_enabled()
    
    text = (
        f"📊 *Node Monitoring*\n"
        f"━━━━━━━━━━━━━━\n"
        f"Node monitoring is currently *{'ENABLED' if is_enabled else 'DISABLED'}*.\n\n"
        "When enabled, the bot will run a background task to check all nodes every 60 seconds."
    )
    
    builder = InlineKeyboardBuilder()
    if is_enabled:
        builder.button(text="❌ Disable Monitoring", callback_data="nodes:toggle_monitoring")
    else:
        builder.button(text="✅ Enable Monitoring", callback_data="nodes:toggle_monitoring")
    
    builder.row(InlineKeyboardButton(text="⬅️ Back to Nodes", callback_data="nodes:menu"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(NodeFSM.monitoring_menu, F.data == "nodes:toggle_monitoring")
async def cb_toggle_monitoring(callback: CallbackQuery, state: FSMContext):
    
    is_currently_enabled = await state_manager.is_monitoring_enabled()
    new_status = not is_currently_enabled
    
    await state_manager.set_monitoring_enabled(new_status)
    await callback.answer(f"✅ Monitoring is now {'ENABLED' if new_status else 'DISABLED'}.", show_alert=True)
    
    await cb_monitoring_menu(callback, state)