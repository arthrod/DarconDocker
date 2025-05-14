# System Patterns

- **Orchestrator/AI-driven onboarding:** Handles repo discovery (auto-cloning if needed), RAG-based repo analysis, .env onboarding, agent test prompt, benchmarking (latency, correctness, resource usage), and automated config/compose generation. Results are surfaced to the user before agent is available.
- **Agent-Repo-Config Pattern:** Each agent is linked to a repo in `docker_repos/`, and all agents are registered as services in a single `docker-compose.yml` (the source of truth). Orchestrator discovers agents via compose and agent card endpoints.
- **Memory Bank Pattern:** The system pattern now includes a generic FastAPI wrapper for all agents/tools, exposing a standardized `/invoke` endpoint for agent-to-agent and orchestrator communication. Agent logic (graph/node) is loaded dynamically at runtime based on environment variables or config, enabling true plug-in modularity. Onboarding logic auto-registers new agents in docker-compose and ensures they are automatically available to the system. The memory bank is updated to reflect all system patterns, onboarding logic, modularity, and benchmarking protocols, ensuring architectural traceability.
- **Onboarding/Production Graph Split:** The onboarding graph/chain handles agent onboarding, repo setup, and config, while the MCP server graph manages runtime workflows. This decouples onboarding complexity from production logic.
- **Agent Notice Board (Supabase):** A centralized, dynamic context-sharing layer for onboarding progress, agent state, and collaboration, accessible to all agents and orchestrator components. Supabase runs locally (http://10.147.20.5:8088), agents use REST API/service key (no RLS), and config is managed via .env/env vars. All config patterns are referenced in activeContext.md.
- **Client Utility:** Utility for agents to post/read notices, enabling real-time coordination and richer collaboration.
- **Docker Compose**: Multi-container deployment, managed/updated by the onboarding flow.
- **FastAPI**: Agents/orchestrator implemented as FastAPI services.
- **Pydantic**: For schema and agent logic.
- **Model Context Protocol (MCP)**: Standardizes agent-tool and inter-agent communication.
- **Agent-to-Agent (A2A) Protocol**: Structured messaging for agent coordination.
- **Agent Card**: JSON metadata for agent discovery/endpoints.
- **.env**: Populated via onboarding, based on extracted variables from repos.
- **Minimal manual config:** User only provides secrets or custom values; everything else is automated.
