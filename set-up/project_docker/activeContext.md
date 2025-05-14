# Active Context

---

## Newly Added Custom/Spec Files
- `features/integration_guide.md`: Integration guide for adding new agents, tools, and orchestrator features.
- `features/testing_strategy.md`: Testing strategy for unit, integration, API, and multi-agent workflow testing.
- `features/agent_notice_board.md`: Design and integration guide for the Supabase-powered Agent Notice Board.
- `features/agent_notice_board_supabase_schema.sql`: Supabase SQL schema for the Agent Notice Board table.
- `darchon/agent_notice_board_client.py`: Python client utility for posting/reading notices from Supabase.
- `.clinerules`: Project intelligence, implementation paths, workflow preferences, and decisions.

---

## Context/Architecture Updates
- Supabase is running locally at http://10.147.20.5:8088, accessed by agents via REST API and service key (no RLS). Config is managed via .env or environment variables. All config and integration patterns are referenced here per memory bank protocol.

---

### PLANNING/STATUS UPDATE

- No code exists yet for agent-driven KG summary update logic in onboarding or runtime flows, and it is not mentioned elsewhere in the project files.
- The following items are still to be implemented:
  - [ ] Automate agent registration in docker-compose.yml from onboarding.
  - [ ] Expand Supabase Python client for agent data CRUD.
  - [ ] Build out Graphiti/Neo4j integration for agent KG summaries.
  - [ ] Write missing feature/API docs and integration guides.
  - [ ] Add real test cases and monitoring containers (plan: create a sandbox container and build a testing agent that will become the benchmarking logic).
- The memory bank and activeContext.md must be kept updated with all changes.
- This is a planning/status update only, no code changes yet.
- Onboarding and production (MCP server) graphs are now separated for modular onboarding and runtime workflows.
- Both graphs are wired to the Agent Notice Board (Supabase) for context sharing, onboarding progress, and system-wide collaboration.
- The notice board enables richer, dynamic context than static agent cards, and is accessible to all agents and orchestrator components.
- All new custom/spec files are referenced here for onboarding, integration, and coordination workflows.

---

**Current Focus:**

- All agents and custom tools are onboarded via a unified, modular workflow.
- Each agent/tool is a self-contained directory, gets its own Docker container, and is registered as a service in docker-compose.yml.
- Benchmarking, test prompts, and ready status are orchestrated and surfaced to the user.
- The memory bank is updated to reflect all architectural and workflow changes, ensuring traceability and reproducibility.
- The system now uses a generic FastAPI agent wrapper for all plug-in agents/tools, exposing `/invoke` endpoints and dynamically loading agent logic (graph/node) at runtime.
- Onboarding and agent discovery are fully automated and standardized via docker-compose and environment/config, supporting rapid modularity.
- Planning orchestrator/AI-driven onboarding for agent/container setup
- Designing repo discovery and auto-cloning logic
- Integrating RAG analysis for repo understanding and config extraction
- Streamlining .env onboarding and automated config/compose generation
- Ensuring minimal manual steps for end users
- Integrating technical onboarding checklist and flowchart from `features/onboarding.md` into the workflow
- Implementing agent test prompt and benchmarking as part of onboarding
- Ensuring each agent is linked to a repo in `docker_repos/` and registered as a service in a single `docker-compose.yml` (the source of truth). Orchestrator discovers agents via compose and agent card endpoints.

**Recent Decisions:**
- Onboarding flow will handle repo discovery, RAG analysis, .env onboarding, and config generation
- User only provides secrets or custom values; all other steps are automated
- All changes are versioned and reproducible
- Orchestrator manages the entire onboarding and setup process
- Each new agent is automatically registered with the orchestrator via agent card discovery (see `features/onboarding.md`)
