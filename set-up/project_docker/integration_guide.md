# MCP Army Integration Guide

This guide describes how to integrate new agents, tools, or orchestrator features into the MCP Army system.

## 1. Agent/Tool Integration
- Place agent/tool Docker context in `docker_repos/<agent_name>/`.
- Ensure agent exposes standardized FastAPI `/invoke` and `/health` endpoints.
- Register agent/tool in `docker-compose.yml` with correct build context, ports, and environment variables (especially `AGENT_GRAPH_PATH`).
- Onboarding logic in orchestrator (`darchon/`) will auto-discover and register new agents.
- Reference new agent/tool in `activeContext.md` when added.

## 2. Orchestrator Feature Integration
- Add orchestrator logic to `darchon/`.
- Update API documentation in `api/` as needed.
- Update architecture diagrams/specs in `features/`.
- Reference new features in `activeContext.md`.

## 3. Plug-in & Modular Patterns
- Use the FastAPI agent wrapper for all new agents/tools.
- Use the Agent Conference Graph (LangGraph) for multi-agent workflows.
- Ensure all communication is via HTTP/JSON on Docker network `mcpnet`.

## 4. Documentation
- Update `activeContext.md` to reference new integrations.
- Add new feature specs or onboarding guides to `features/` as needed.

---
