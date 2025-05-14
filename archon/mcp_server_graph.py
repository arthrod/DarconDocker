"""
MCP Server Graph: Main Production Agent Graph for MCP Army

- Handles all production agent-to-agent workflows, tool orchestration, and runtime traffic.
- Receives notifications from onboarding_graph about new agents and their capabilities.
- Can update its agent registry dynamically as new agents are onboarded.
"""

from typing import Dict, Any, List
from darchon.agent_notice_board_client import AgentNoticeBoardClient

class MCPServerGraph:
    """
    MCPServerGraph integrates with the Agent Notice Board (Supabase).
    Posts notices on agent registration and onboarding events.
    Can poll the notice board for onboarding completions or agent updates.
    """
    def __init__(self):
        self.agents = {}  # name -> agent instance
        self.notice_client = AgentNoticeBoardClient()

    def register_agent(self, agent_name: str, agent_info: Dict[str, Any]):
        self.agents[agent_name] = agent_info
        print(f"[MCPServerGraph] Registered new agent: {agent_name} | Info: {agent_info}")
        # Post registration notice
        self.notice_client.post_notice(
            agent_id=agent_name,
            notice_type="agent_registered",
            payload={"agent_info": agent_info}
        )

    def receive_onboarding_notification(self, onboarding_agent: str, context: Dict[str, Any]):
        print(f"[MCPServerGraph] Notified by {onboarding_agent} during onboarding: {context}")
        # Optionally, pre-register or prepare for new agent
        self.notice_client.post_notice(
            agent_id=onboarding_agent,
            notice_type="onboarding_notification",
            payload={"context": context}
        )

    def poll_onboarding_notices(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch recent onboarding completion notices from the notice board."""
        notices = self.notice_client.get_notices({"notice_type": "onboarding_complete"}, limit=limit)
        for notice in notices:
            print(f"[MCPServerGraph] Onboarding complete: {notice}")
        return notices

    def run(self):
        # Main workflow logic for production agent orchestration
        pass
