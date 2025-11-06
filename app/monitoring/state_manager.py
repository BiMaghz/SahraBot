import os
import json
import logging
import asyncio

import aiofiles
import aiofiles.os

from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MonitoringState:
    def __init__(self, db_path: str = "./data/monitoring.json"):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._default_state = {
            "monitoring_enabled": False,
            "nodes": {}
        }

    async def _read_state(self) -> Dict[str, Any]:
        async with self._lock:
            if not await aiofiles.os.path.exists(self.db_path):
                return self._default_state.copy()
            try:
                async with aiofiles.open(self.db_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    return json.loads(content)
            except Exception as e:
                logger.error(f"Failed to read state file {self.db_path}: {e}")
                return self._default_state.copy()

    async def _write_state(self, state: Dict[str, Any]) -> bool:
        async with self._lock:
            try:
                await aiofiles.os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                async with aiofiles.open(self.db_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(state, indent=2))
                return True
            except Exception as e:
                logger.error(f"Failed to write state file {self.db_path}: {e}")
                return False

    async def is_monitoring_enabled(self) -> bool:
        state = await self._read_state()
        return state.get("monitoring_enabled", False)

    async def set_monitoring_enabled(self, is_enabled: bool):
        state = await self._read_state()
        state["monitoring_enabled"] = is_enabled
        await self._write_state(state)
        logger.info(f"Monitoring state set to: {is_enabled}")

    async def get_node_status(self, node_name: str) -> Optional[Dict]:
        state = await self._read_state()
        return state.get("nodes", {}).get(node_name)

    async def update_node_status(self, node_name: str, status_data: Dict[str, Any]):
        state = await self._read_state()
        if "nodes" not in state:
            state["nodes"] = {}
        
        existing_data = state["nodes"].get(node_name, {})
        
        existing_data.update(status_data)
        
        existing_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        state["nodes"][node_name] = existing_data
        await self._write_state(state)

    async def remove_node(self, node_name: str):
        state = await self._read_state()
        if node_name in state.get("nodes", {}):
            del state["nodes"][node_name]
            await self._write_state(state)

state_manager = MonitoringState()