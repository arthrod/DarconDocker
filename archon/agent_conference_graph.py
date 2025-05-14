"""
Agent Conference Graph (Plug-in, Modular, All-Way Communication)
- Each agent/tool exposes a standardized FastAPI `/invoke` endpoint using a generic wrapper that dynamically loads the agent graph/node logic at runtime (see features/fastapi_agent_wrapper.py).
- Agents are discovered dynamically from docker-compose.yml and integrated into a fully connected (all-way) communication graph.
- The system supports true plug-in modularity: new agents/tools are onboarded and registered automatically, with no code changes required.
- Agent logic is loaded at runtime via environment variables/config (e.g., AGENT_GRAPH_PATH), supporting rapid extension and customization.
- A response aggregator node summarizes all agent outputs for the orchestrator/user.
- Onboarding logic auto-registers new agents/tools in docker-compose and ensures they are available to the system.
- All agent-to-agent and orchestrator communication is via HTTP/JSON to the standardized `/invoke` endpoint.
- Designed for easy plug-in extension and future workflows.
"""
import yaml
import httpx
from pathlib import Path
from langgraph.graph import Graph
from typing import Dict, Any

# --- Dynamic Discovery of Agents/Tools ---
def discover_agents(compose_path="../../docker-compose.yml") -> Dict[str, str]:
    compose_file = Path(__file__).parent / compose_path
    with open(compose_file, 'r') as f:
        compose = yaml.safe_load(f)
    agents = {}
    for svc, cfg in compose.get('services', {}).items():
        if 'build' in cfg and 'ports' in cfg:
            port = str(cfg['ports'][0]).split(":")[0]
            url = f"http://{svc}:{port}"
            agents[svc] = url
    return agents

# --- Agent Node Wrapper ---
from .agent_node import agent_node

# --- Response Aggregator Node ---
def response_aggregator(all_responses: Dict[str, Any]) -> Dict[str, Any]:
    summary = "\n\n".join([
        f"Agent: {agent}\nResponse: {resp.get('result', resp)}"
        for agent, resp in all_responses.items()
    ])
    return {"summary": summary, "all_responses": all_responses}

# --- Build the All-Way Communication Graph ---
def build_agent_conference_graph():
    agents = discover_agents()
    graph = Graph()
    agent_nodes = {name: agent_node(url) for name, url in agents.items()}

    # Add agent nodes
    for name, node_fn in agent_nodes.items():
        graph.add_node(name, node_fn)

    # All-way communication: every agent can send to every other agent
    for src in agent_nodes:
        for dst in agent_nodes:
            if src != dst:
                graph.connect(src, dst)

    # Aggregator node
    def aggregator_node(input_data):
        return response_aggregator(input_data)
    graph.add_node("response_aggregator", aggregator_node)
    for agent in agent_nodes:
        graph.connect(agent, "response_aggregator")

    return graph

# --- Onboarding Logic: Auto-Register New Agents/Tools ---
def onboarding_register_new_agent(agent_dir: str, service_name: str, port: int):
    compose_path = Path(__file__).parent.parent / "docker-compose.yml"
    with open(compose_path, 'r') as f:
        compose = yaml.safe_load(f)
    if service_name in compose.get('services', {}):
        print(f"Service {service_name} already exists in compose.")
        return
    compose['services'][service_name] = {
        'build': {'context': agent_dir},
        'ports': [f"{port}:{port}"],
        'networks': ['mcpnet']
    }
    with open(compose_path, 'w') as f:
        yaml.safe_dump(compose, f)
    print(f"Registered new agent {service_name} at {agent_dir} with port {port}.")

# --- Example Usage ---
if __name__ == "__main__":
    # Example onboarding: register a new agent (call from onboarding UI/CLI)
    # onboarding_register_new_agent("../docker_repos/agentX", "agentX", 8005)

    # Build and run the agent conference graph
    graph = build_agent_conference_graph()
    input_data = {"input": "Agent conference: collaborate and respond."}
    # Broadcast input to all agents, collect responses
    all_responses = {}
    for agent in graph.nodes:
        if agent != "response_aggregator":
            all_responses[agent] = graph.nodes[agent](input_data)
    # Aggregate and print summary
    summary = graph.nodes["response_aggregator"](all_responses)
    print("\n===== Agent Conference Summary =====\n")
    print(summary["summary"])

