import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class AdminInfo(BaseModel):
    id: int
    username: str
    is_sudo: bool

class Node(BaseModel):
    id: int
    name: str
    address: str
    port: int
    status: str
    message: str
    xray_version: Optional[str] = None

class NodeList(BaseModel):
    items: List[Node]
    total: int
    page: int
    size: int
    pages: int

class UserService(BaseModel):
    id: int
    name: str
    user_ids: List[int] = Field(default_factory=list)

class UserStats(BaseModel):
    total: int
    active: int
    on_hold: int
    expired: int
    limited: int
    online: int

class TrafficStats(BaseModel):
    step: int
    total: int
    usages: List[List[Optional[int]]]

class User(BaseModel):
    id: int
    username: str
    key: str
    data_limit: int
    expire_strategy: str
    expire_date: Optional[datetime] = None
    service_ids: List[int] = Field(default_factory=list)
    activated: bool
    is_active: bool
    expired: bool
    data_limit_reached: bool
    enabled: bool
    used_traffic: int
    lifetime_used_traffic: int
    note: Optional[str] = None
    owner_username: Optional[str] = None
    online_at: Optional[datetime] = None
    created_at: datetime
    sub_updated_at: Optional[datetime] = None
    sub_last_user_agent: Optional[str] = None
    subscription_url: Optional[str] = None

    @field_validator("data_limit", mode="before")
    @classmethod
    def convert_null_data_limit_to_zero(cls, v):
        return v if v is not None else 0

# --- API Client ---

class MarzneshinAPI:
    def __init__(self, panel_url: str, username: str, password: str):
        self.base_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self._token: Optional[str] = None
        self._expires_at: int = 0
        self.client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def _get_token(self, force_refresh: bool = False) -> Optional[str]:
        if not force_refresh and self._token and time.time() < self._expires_at - 60:
            return self._token

        try:
            response = await self.client.post(
                f"{self.base_url}/api/admins/token",
                data={"grant_type": "password", "username": self.username, "password": self.password},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            token_data = response.json()
            self._token = token_data["access_token"]
            self._expires_at = time.time() + token_data.get("expires_in", 86400)
            logging.info("Marzneshin token obtained/refreshed successfully.")
            return self._token
        except httpx.HTTPStatusError as e:
            logging.error(f"Marzneshin Token HTTP Error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logging.error(f"Marzneshin Token Request Error: {e}")
        return None

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[httpx.Response]:
        token = await self._get_token()
        if not token:
            return None

        headers = kwargs.pop('headers', {})
        headers["Authorization"] = f"Bearer {token}"
        headers["accept"] = "application/json"

        try:
            response = await self.client.request(method, f"{self.base_url}{endpoint}", headers=headers, **kwargs)

            if response.status_code == 401:
                logging.warning("Token expired or invalid. Refreshing and retrying...")
                token = await self._get_token(force_refresh=True)
                if not token:
                    return None
                headers["Authorization"] = f"Bearer {token}"
                response = await self.client.request(method, f"{self.base_url}{endpoint}", headers=headers, **kwargs)

            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logging.error(f"Marzneshin API HTTP Error on {method} {endpoint}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logging.error(f"Marzneshin API Request Error on {method} {endpoint}: {e}")
        return None
    
    async def get_current_admin(self) -> Optional[AdminInfo]:
        response = await self._request("GET", "/api/admins/current")
        return AdminInfo(**response.json()) if response else None
    
    async def get_nodes(
        self,
        status: Optional[str] = None,
        name: Optional[str] = None,
        page: int = 1,
        size: int = 50
    ) -> Optional[NodeList]:
        params = {"page": page, "size": size}
        if status:
            params["status"] = status
        if name:
            params["name"] = name
            
        response = await self._request("GET", "/api/nodes", params=params)
        return NodeList(**response.json()) if response else None

    async def resync_node(self, node_id: int) -> bool:
        response = await self._request("POST", f"/api/nodes/{node_id}/resync")
        return response is not None and response.status_code == 200

    async def get_user(self, username: str) -> Optional[User]:
        response = await self._request("GET", f"/api/users/{username}")
        return User(**response.json()) if response else None

    async def get_all_users(
        self,
        username: Optional[str] = None,
        order_by: Optional[str] = None,
        descending: Optional[bool] = None,
        is_active: Optional[bool] = None,
        activated: Optional[bool] = None,
        expired: Optional[bool] = None,
        data_limit_reached: Optional[bool] = None,
        enabled: Optional[bool] = None,
        owner_username: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> Optional[Dict]:
        endpoint = "/api/users"
        params = {"page": page, "size": size}

        if username is not None:
            params["username"] = username
        if order_by:
            params["order_by"] = order_by
        if descending is not None:
            params["descending"] = descending
        if is_active is not None:
            params["is_active"] = is_active
        if activated is not None:
            params["activated"] = activated
        if expired is not None:
            params["expired"] = expired
        if data_limit_reached is not None:
            params["data_limit_reached"] = data_limit_reached
        if enabled is not None:
            params["enabled"] = enabled
        if owner_username is not None:
            params["owner_username"] = owner_username

        response = await self._request("GET", endpoint, params=params)
        if not response:
            return None
    
        data = response.json()
        users = [User(**user_data) for user_data in data.get("items", [])]
    
        return {
            "users": users,
            "total": data.get("total", 0),
            "page": data.get("page", 1),
            "size": data.get("size", 10),
            "pages": data.get("pages", 1),
        }
    
    async def create_user(self, payload: Dict[str, Any]) -> Optional[User]:
        response = await self._request("POST", "/api/users", json=payload)
        return User(**response.json()) if response else None

    async def update_user(self, username: str, payload: Dict[str, Any]) -> Optional[User]:
        response = await self._request("PUT", f"/api/users/{username}", json=payload)
        return User(**response.json()) if response else None

    async def delete_user(self, username: str) -> bool:
        response = await self._request("DELETE", f"/api/users/{username}")
        return response is not None and response.status_code == 200
    
    async def enable_user(self, username: str) -> bool:
        response = await self._request("POST", f"/api/users/{username}/enable")
        return response is not None and response.status_code == 200

    async def disable_user(self, username: str) -> bool:
        response = await self._request("POST", f"/api/users/{username}/disable")
        return response is not None and response.status_code == 200
    
    async def delete_expired_users(self, passed_time: int) -> Optional[Dict]:
        url = f"{self.base_url}/api/users/expired"
        headers = {"Authorization": f"Bearer {await self._get_token()}"}
        params = {"passed_time": passed_time}
        
        try:
            response = await self.client.delete(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logging.info("Attempted to delete expired users, but none were found.")
                return e.response.json()
            logging.error(f"Marzneshin API HTTP Error on DELETE /api/users/expired: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logging.error(f"Marzneshin API Request Error on DELETE /api/users/expired: {e}")
            return None
        
    async def reset_usage(self, username: str) -> bool:
        response = await self._request("POST", f"/api/users/{username}/reset")
        return response is not None and response.status_code == 200

    async def revoke_sub(self, username: str) -> bool:
        response = await self._request("POST", f"/api/users/{username}/revoke_sub")
        return response is not None and response.status_code == 200

    async def get_services(self) -> Optional[List[UserService]]:
        response = await self._request("GET", "/api/services")
        if not response:
            return None
        data = response.json()
        return [UserService(**service_data) for service_data in data.get("items", [])]
    
    async def get_sub_info(self, username: str, key: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/sub/{username}/{key}/info"
        response = await self.client.get(url)
        return response.json()

    async def get_system_traffic_stats(self) -> Optional[TrafficStats]:
        response = await self._request("GET", "/api/system/stats/traffic")
        return TrafficStats(**response.json()) if response else None

    async def get_system_users_stats(self) -> Optional[UserStats]:
        response = await self._request("GET", "/api/system/stats/users")
        return UserStats(**response.json()) if response else None