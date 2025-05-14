# Project Brief

This project implements a plug-and-play system where each Retrieval-Augmented Generation (RAG) agent operates in its own Docker container, forming a cohesive "MCP RAG army." The onboarding process is orchestrator/AI-driven, handling repo discovery (including auto-cloning if needed), RAG-based repo analysis, interactive .env onboarding, agent test prompt and benchmarking, and fully automated Docker Compose/config generation. Users are guided through agent/container setup with minimal manual steps—just provide secrets or keys and the system does the rest. Benchmarking results and a 'ready' message are surfaced to the user before agents are available.

**Architecture Note:**
- Each agent is linked to a dedicated repo in `docker_repos/` (Dockerfile, code, config).
- Agents are registered as services in a single `docker-compose.yml` (the system's source of truth).
- Orchestrator discovers and manages agents via compose and agent card endpoints.
- The project now uses a generic FastAPI wrapper, exposing `/invoke` endpoints and dynamically loading agent logic (graph/node) at runtime.
- Onboarding and agent discovery are fully automated: new agents are registered in docker-compose and become available without code changes, supporting a true plug-in architecture.
- Modular onboarding and runtime workflows: onboarding and production agent graphs are separated for clarity, extensibility, and maintainability.
- The Agent Notice Board (Supabase) is used for real-time, dynamic context sharing, onboarding progress, and agent/system coordination. Supabase is running locally at http://10.147.20.5:8088, accessed via REST API and service key (no RLS). Config is managed via .env or environment variables.
- Agents and orchestrator components communicate via both static agent cards (for handshake/capabilities) and the dynamic notice board (for richer, collaborative context).
- A Python client utility is provided for agents to post/read notices from Supabase.

Key goals:

- The memory bank documents onboarding flows, modularity patterns, benchmarking protocols, and workflow evolution for full traceability.
- Modular, containerized RAG agents (FastAPI + Pydantic)
- Shared Docker network for agent-to-agent (A2A) communication
- Model Context Protocol (MCP) standardization
- Central orchestrator for unified endpoint and coordination
- Secure, scalable, and testable architecture
- **AI-driven onboarding:** Repo discovery, RAG analysis, .env onboarding, agent test prompt, benchmarking, and automated agent/container setup
- Minimal manual configuration for end users
