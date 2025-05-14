# MCP Army: Full Build Plan

## Foundation-First Manual Setup
- Start with [foundation.md](foundation.md) to manually set up your environment, directories, Docker Compose, and network (network_xxx).
- All services (agents, orchestrator, Supabase, etc.) communicate internally via the shared Docker network—no external URLs required.
- Once the foundation is working, proceed to automate and agentize onboarding, registration, and workflow steps.
 (From Scratch)

This guide walks you step-by-step from a blank system (just Docker and Portainer) to a fully operational, modular MCP Army platform. It includes project structure, onboarding, Supabase, agent creation, knowledge graph integration, and all key terminal commands. Use this as your master checklist!

---

## 1. Prerequisites

- **Docker** and **Docker Compose** installed
- **Python 3.9+** installed
- (Optional) **Portainer** for Docker UI
- **Supabase** account (https://supabase.com/)
- (Optional, for KG): **Neo4j** and **Graphiti** (see https://github.com/graphiti-api/graphiti)

---

## 2. Project Directory Structure

```bash
mkdir -p Docker_MCP_Server/{docker_repos,darchon,features,deployment,api,custom_tools,set-up}
```

- `docker_repos/` — Each agent's code, Dockerfile, config
- `darchon/` — Orchestrator, onboarding graph, server graph, notice board client
- `features/` — Feature specs, Supabase schemas, integration docs
- `deployment/` — Deployment, security, monitoring, troubleshooting docs
- `set-up/` — Setup scripts and guides
- Memory bank files: `projectbrief.md`, `productContext.md`, `systemPatterns.md`, `techContext.md`, `activeContext.md`, `progress.md`, `.clinerules`

---

## 3. Initialize Git

```bash
git init
git add .
git commit -m "Initial MCP Army structure"
git remote add origin <your-git-remote-url>
git branch -M main
git push -u origin main
```

---

## 4. Supabase Setup

1. **Create a new project** at https://app.supabase.com/
2. **Create tables:**
   - `agent_notice_board` (see `features/agent_notice_board_supabase_schema.sql`)
   - `agent_data` (see `features/agent_data_supabase_schema.sql`)
3. **Enable Row-Level Security (RLS)** and set policies as needed.
4. **Get your `SUPABASE_URL` and `SUPABASE_API_KEY`** for use in the Python client.

---

## 5. Orchestrator & Onboarding Graph

- Scaffold `darchon/orchestrator.py` (FastAPI app for onboarding, registry, coordination)
- Scaffold `darchon/onboarding_graph.py` (chain of onboarding agents: NeedsAgent → RepoAgent → CodingAgent → ConfigAgent → RankingAgent)
- Implement onboarding flow:
  - Prompt user for initial intent (“What would you like?”)
  - Discover/clone repo, extract config, generate .env
  - Auto-generate docker-compose.yml entry
  - Benchmark agent (test prompt, latency, correctness)
  - Post onboarding progress to Supabase notice board and agent_data table

---

## 6. Agent Template

- Each agent: FastAPI app, `/invoke` endpoint, agent card (JSON), Dockerfile, config template
- Onboarded agents are auto-registered in `docker-compose.yml`
- Example agent repo structure:

```
docker_repos/agent_name/
  |- Dockerfile
  |- main.py (FastAPI)
  |- agent_card.json
  |- config_template.env
```

---

## 7. Agent Notice Board (Supabase)

- Deploy `agent_notice_board` table (see SQL in `features/agent_notice_board_supabase_schema.sql`)
- Use `darchon/agent_notice_board_client.py` to post/read notices
- Notices include onboarding progress, collaboration, benchmarking, etc.

---

## 8. Persistent Agent Data (Supabase)

- Deploy `agent_data` table (see SQL in `features/agent_data_supabase_schema.sql`)
- Store:
  - Agent ID, name, description, repo, docker image, endpoints, capabilities, config
  - Onboarding context, user intent, onboarding conversation
  - KG summary (from Graphiti/Neo4j), KG URI
- (Optional) Integrate with Graphiti/Neo4j for KG summaries/relationships

---

## 9. Workflow Automation

- Onboarding flow:
  - User submits initial request
  - Orchestrator/graph manages repo, config, agent creation
  - All steps/context posted to notice board and agent_data table
- Production (server) graph:
  - Monitors notice board for new agents, state changes
  - Registers new agents and updates registry dynamically

---

## 10. Testing, Monitoring, Security

- Follow `features/testing_strategy.md` for unit/integration tests
- Set up monitoring (Prometheus, Grafana) as per `deployment/monitoring.md`
- Apply security best practices from `deployment/security.md` (manage secrets, enable RLS, etc.)

---

## 11. Memory Bank & Documentation

- Update memory bank files after every major change:
  - `projectbrief.md`, `productContext.md`, `systemPatterns.md`, `techContext.md`, `activeContext.md`, `progress.md`, `.clinerules`
- Use these as your single source of truth for onboarding, workflows, and troubleshooting.

---

## 12. Example Terminal Commands (Cheat Sheet)

```bash
# Start all agents and orchestrator
docker compose up --build

# Add a new agent repo
git clone <agent-template-repo> docker_repos/my_new_agent

# Add new files to git
git add .
git commit -m "Add new agent: my_new_agent"
git push

# Run onboarding script (example)
python darchon/onboarding_graph.py

# Post a notice to Supabase (example)
python darchon/agent_notice_board_client.py --post --agent_id=my_new_agent --notice_type=onboarding_start --payload='{"step":"init"}'

# Check logs
docker compose logs orchestrator

# View running containers
docker ps
```

---

## 13. Next Steps

- [ ] Complete each checklist item above in order
- [ ] Use `set-up/` directory for setup scripts, notes, and automation helpers
- [ ] Ask for more detailed guides on any step as needed!

---

**You are ready to build the MCP Army from scratch. Update your memory bank as you go!**
