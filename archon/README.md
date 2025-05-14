# LangGraph Integration for Docker MCP Army

This directory contains code and documentation for integrating your modular Docker MCP Army agents and tools with [LangGraph](https://github.com/langchain-ai/langgraph), enabling robust, composable, and observable multi-agent workflows.

---

## Overview
- **Each agent/tool (repo or custom) is exposed as a FastAPI HTTP service in Docker.**
- **LangGraph orchestrates these agents as nodes in a graph, calling their HTTP endpoints.**
- **Workflows can be dynamically composed, monitored, and extended.**

---

## Directory Structure
- `workflow.py` — Example LangGraph workflow that dynamically discovers and orchestrates all running agents/tools.
- `agent_node.py` — Utility for wrapping agent HTTP endpoints as LangGraph nodes.
- `discovery.py` — Utility for reading `docker-compose.yml` and auto-registering agents/tools as LangGraph nodes.
- `README.md` — This file.

---

## Quickstart
1. Ensure all agents/tools are running in Docker with unique service names and ports.
2. Install LangGraph and dependencies:
   ```bash
   pip install langgraph httpx pyyaml
   ```
3. Use or extend the provided `workflow.py` to define and run your workflow.

---

## Example Workflow
See `workflow.py` for a sample that:
- Discovers agents from `docker-compose.yml`
- Wraps each as a LangGraph node
- Connects nodes into a simple pipeline
- Runs the workflow with sample input

---

## Extending
- Add custom logic, error handling, or branching in your graph as needed.
- Integrate with orchestrator for dynamic agent discovery and health checks.
- Use LangGraph's hooks for tracing, monitoring, and observability.

---

## Docker Compose & Network Integration
- darchon is deployed as a service via Docker Compose on the shared Docker network (network_xxx).
- All service communication (including with Supabase and other agents) is internal to Docker and uses service names, not external URLs.
- Reference your manual build/run script and see [../foundation.md](../foundation.md) for initial setup and troubleshooting.
- Config is managed via .env files.

---

## References
- [LangGraph Documentation](https://github.com/langchain-ai/langgraph)
- [Your MCP Army API Docs](../darchon/README.md)
- [docker-compose.yml] (project root)
