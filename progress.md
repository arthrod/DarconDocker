# Progress

## Status/roadmap

- Onboarding and production (MCP server) graphs are now separated for modular onboarding and runtime workflows.
- The Agent Notice Board (Supabase) and Python client utility are integrated for real-time context sharing and collaboration.
- All onboarding and runtime workflows now coordinate via the notice board, supporting rapid agent onboarding and system transparency.

- The memory bank is updated in parallel with all major workflow and architectural changes, including onboarding, modularity, and benchmarking protocols.
- Implemented a generic FastAPI agent wrapper that exposes standardized `/invoke` endpoints and loads agent logic dynamically.
- Onboarding now auto-registers new agents in docker-compose and ensures plug-in modularity with no code changes required.
- Planning phase: architecture, protocols, and system requirements defined
- Agent test prompt and benchmarking protocol defined as part of onboarding

## Roadmap
1. Finalize project structure and configuration
2. Implement base agent template (FastAPI + Pydantic)
3. Implement orchestrator service
4. Define agent card and protocol endpoints
5. Create Docker Compose and .env setup
6. Integrate, test, and document
7. Implement agent test prompt and benchmarking; surface results to user during onboarding
