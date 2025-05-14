# agent_node.py
"""
Utility for wrapping a Docker MCP Army agent/tool HTTP API as a LangGraph node.
"""
import httpx

from .langfuse_tracing import trace

def agent_node(agent_url, endpoint="/invoke"):
    """
    Returns a LangGraph-compatible node function that calls the agent's HTTP endpoint.
    """
    @trace(name="agent_node_call", metadata={"agent_url": agent_url})
    def node_fn(input_data):
        resp = httpx.post(f"{agent_url}{endpoint}", json=input_data)
        resp.raise_for_status()
        return resp.json()
    return node_fn
