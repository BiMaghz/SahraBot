import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

from typing import List
from app.api.marzneshin import MarzneshinAPI
from .state_manager import state_manager

logger = logging.getLogger(__name__)

async def alert_sudo_admins(bot: Bot, message: str, sudo_chat_ids: List[int]):
    for admin_id in sudo_chat_ids:
        try:
            await bot.send_message(admin_id, message, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to send alert to admin {admin_id}: {e}")

async def run_monitoring_loop(bot: Bot, api_client: MarzneshinAPI, sudo_chat_ids: List[int]):
    logger.info("Node monitoring background task started.")
    while True:
        try:
            if not await state_manager.is_monitoring_enabled():
                await asyncio.sleep(60)
                continue

            nodes_list = await api_client.get_nodes(size=100)
            if not nodes_list:
                logger.warning("Monitoring loop: Could not fetch nodes from API.")
                await asyncio.sleep(60)
                continue

            current_node_statuses = {node.name: node for node in nodes_list.items}

            for node_name, current_node in current_node_statuses.items():
                saved_status_data = await state_manager.get_node_status(node_name)
                
                if current_node.status == 'unhealthy':
                    if saved_status_data is None:
                        logger.warning(f"Node '{node_name}' detected as unhealthy. Attempting resync.")
                        await api_client.resync_node(current_node.id)
                        
                        new_status_data = {
                            "status": 'unhealthy',
                            "message": current_node.message,
                            "down_since": datetime.now(timezone.utc).isoformat(),
                            "alert_sent": False,
                            "last_alert_time": None
                        }
                        await state_manager.update_node_status(node_name, new_status_data)
                    else:
                        if not saved_status_data.get('alert_sent'):
                            logger.error(f"Node '{node_name}' is CONFIRMED down. Sending alert.")
                            await alert_sudo_admins(
                                bot,
                                f"💔 *Node Down Alert*\n"
                                f"Node: `{node_name}`\n"
                                f"Error: `{current_node.message}`",
                                sudo_chat_ids
                            )
                            saved_status_data['alert_sent'] = True
                            saved_status_data['last_alert_time'] = datetime.now(timezone.utc).isoformat()
                            await state_manager.update_node_status(node_name, saved_status_data)
                        
                        else:
                            last_alert_time_str = saved_status_data.get('last_alert_time')
                            if last_alert_time_str:
                                last_alert_time = datetime.fromisoformat(last_alert_time_str)
                                if (datetime.now(timezone.utc) - last_alert_time).total_seconds() > 3600: # 1 hour
                                    logger.warning(f"Node '{node_name}' is still down. Sending reminder.")
                                    await alert_sudo_admins(
                                        bot,
                                        f"⏰ *Node Reminder*\n"
                                        f"Node: `{node_name}` is still unhealthy.",
                                        sudo_chat_ids
                                    )
                                    saved_status_data['last_alert_time'] = datetime.now(timezone.utc).isoformat()
                                    await state_manager.update_node_status(node_name, saved_status_data)

                elif current_node.status == 'healthy' and saved_status_data is not None:
                    logger.info(f"Node '{node_name}' has recovered. Sending recovery alert.")
                    down_since_time = datetime.fromisoformat(saved_status_data['down_since'])
                    downtime = datetime.now(timezone.utc) - down_since_time
                    downtime_str = str(downtime).split('.')[0]
                    
                    await alert_sudo_admins(
                        bot,
                        f"💚 *Node Recovered*\n"
                        f"Node: `{node_name}` is now healthy.\n"
                        f"Downtime: `{downtime_str}`",
                        sudo_chat_ids
                    )
                    await state_manager.remove_node(node_name)

            saved_nodes = (await state_manager._read_state()).get("nodes", {})
            for saved_node_name in list(saved_nodes.keys()):
                if saved_node_name not in current_node_statuses:
                    await state_manager.remove_node(saved_node_name)

        except Exception as e:
            logger.error(f"Unhandled error in monitoring loop: {e}", exc_info=True)
        
        await asyncio.sleep(60)