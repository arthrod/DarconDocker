"""
Agent Notice Board Client for MCP Army (Supabase)
- Allows agents to post and read notices from the central Supabase-powered notice board.
- Requires SUPABASE_URL and SUPABASE_API_KEY (or anon key) in environment or config.
"""
import os
import requests
from typing import Optional, Dict, Any, List

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY") or os.getenv("SUPABASE_ANON_KEY")
NOTICE_TABLE = "agent_notice_board"

class AgentNoticeBoardClient:
    def __init__(self, supabase_url: Optional[str] = None, SUPABASE_API_KEY: Optional[str] = None):
        self.supabase_url = supabase_url or SUPABASE_URL
        self.SUPABASE_API_KEY = SUPABASE_API_KEY or SUPABASE_API_KEY
        if not self.supabase_url or not self.SUPABASE_API_KEY:
            raise ValueError("Supabase URL and key must be set in env or passed to client.")
        self.rest_url = f"{self.supabase_url}/rest/v1/{NOTICE_TABLE}"
        self.headers = {
            "apikey": self.SUPABASE_API_KEY,
            "Authorization": f"Bearer {self.SUPABASE_API_KEY}",
            "Content-Type": "application/json",
        }

    def post_notice(self, agent_id: str, notice_type: str, payload: Dict[str, Any], visibility: str = "public", expires_at: Optional[str] = None) -> Dict[str, Any]:
        data = {
            "agent_id": agent_id,
            "notice_type": notice_type,
            "payload": payload,
            "visibility": visibility,
        }
        if expires_at:
            data["expires_at"] = expires_at
        resp = requests.post(self.rest_url, json=data, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_notices(self, filter_dict: Optional[Dict[str, Any]] = None, limit: int = 10) -> List[Dict[str, Any]]:
        params = {"select": "*", "order": "timestamp.desc", "limit": limit}
        if filter_dict:
            for k, v in filter_dict.items():
                params[k] = f"eq.{v}"
        resp = requests.get(self.rest_url, headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()
