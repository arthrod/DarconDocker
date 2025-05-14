# Product Context

## Problem context/solutions

- Onboarding and runtime workflows are now decoupled: onboarding is handled by a dedicated graph/chain, while production logic is managed by the main MCP server graph.
- The Agent Notice Board (Supabase) enables agents and orchestrator components to share onboarding progress, capabilities, and collaboration requests in real time. Supabase is running locally (http://10.147.20.5:8088), accessed via REST API and service key (no RLS). Config is managed via .env or environment variables and all patterns are documented in the memory bank.
- The Python client utility allows seamless posting and retrieval of notices, supporting dynamic, context-rich workflows.

## Problem
Modern AI workflows require orchestrating multiple specialized agents, each with unique dependencies and configuration. Manual setup—cloning repos, configuring .env files, and writing Docker Compose services—is error-prone, slow, and unfriendly to non-experts.

## Solution

- The system maintains an up-to-date memory bank documenting all onboarding, benchmarking, architectural, and workflow changes.
- All agents/tools now use a generic FastAPI wrapper, exposing `/invoke` endpoints and loading agent logic (graph/node) dynamically for true plug-in modularity.
- Onboarding and agent discovery are automated via docker-compose, supporting rapid extensibility and modularity.
- This ensures all project knowledge, workflow decisions, and modularity patterns are accessible and consistently applied.
This project leverages an AI/orchestrator-driven onboarding flow:
- Discovers or auto-clones required repos
- Uses RAG to analyze repo structure and config needs
- Guides the user through .env onboarding (with auto-extraction of variables)
- Automatically generates all Docker Compose and agent config files
- Orchestrator sends a test prompt and benchmarks each new agent (latency, correctness, resource usage); results are surfaced to the user before the agent is available
- Each agent is linked to a dedicated repo in `docker_repos/`, and all agents are registered as services in a single `docker-compose.yml` (the source of truth). Orchestrator discovers agents via compose and agent card endpoints.
- Minimizes manual steps—user only provides secrets or custom values
- Enables rapid, reproducible, and error-resistant agent/container setup
