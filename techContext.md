# Tech Context

## Tech stack/setup

- Supabase (Postgres + REST API) powers the Agent Notice Board for dynamic, real-time context sharing. Supabase runs locally (http://10.147.20.5:8088), agents use REST API and service key (no RLS), and config is managed via .env/env vars. All config patterns are documented in the memory bank and referenced in activeContext.md.
- Python client utility enables all agents and orchestrator components to interact with the notice board.
- Onboarding and production graphs are separated for modularity and maintainability, both integrated with the notice board.

- **Docker**: Containerization of agents and orchestrator
- **Docker Compose**: Multi-container orchestration and shared network
- **Python**: Main programming language
- **FastAPI**: Web framework for agents and orchestrator
- **Pydantic**: Data validation- Each agent/tool can have its own `.env` file for environment-specific configurations and secrets.
- Agents/tools expose a standardized FastAPI `/invoke` endpoint, implemented via a generic wrapper that dynamically loads the agent graph or node logic based on environment/config.
- The system supports plug-in modularity: new agents are discovered via docker-compose and onboarded automatically, with no code changes required.
- Agent logic can be updated or swapped dynamically by changing environment variables (e.g., `AGENT_GRAPH_PATH`).
- **Agent Test & Benchmarking**: Orchestrator sends a test prompt and benchmarks each agent (latency, correctness, resource usage) as part of onboarding; results are surfaced to the user before agent is available.
- **Agent-Repo-Config Architecture**: Each agent is linked to a repo in `docker_repos/`, and all agents are registered as services in a single `docker-compose.yml` (the authoritative config). Orchestrator discovers and manages agents via compose and agent card endpoints.

- The memory bank is used to document all technical, onboarding, and benchmarking changes, supporting reproducibility and knowledge sharing.

## References
- [Pydantic AI Examples](https://ai.pydantic.dev/examples/)
- [A2A Protocol Documentation](https://www.a2aprotocol.org/)
- [Docker Documentation](https://docs.docker.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
