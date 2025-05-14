# 06_workflow_automation.md

## Workflow Automation: Onboarding, Registry, and Runtime

### 1. Onboarding Flow (Step-by-Step)
- User submits initial request (via orchestrator UI or CLI)
- Orchestrator calls onboarding graph:
  - **NeedsAgent**: Prompt for "What would you like?" (user intent)
  - **RepoAgent**: Discover or clone agent repo
  - **CodingAgent**: (Optional) Generate starter code if needed
  - **ConfigAgent**: Extract config, generate .env, create docker-compose entry
  - **RankingAgent**: Benchmark agent (test prompt, latency, correctness)
- At each step:
  - Post progress to Supabase notice board (`agent_notice_board`)
  - Update persistent agent record in `agent_data` (user intent, onboarding context, KG summary, etc.)

### 2. Agent Registration & Discovery
- New agents are auto-registered in `docker-compose.yml`
- Orchestrator discovers agents by reading `docker-compose.yml` and agent cards
- Registry is updated dynamically as agents are onboarded

### 3. Runtime Coordination
- Orchestrator and agents poll or subscribe to the notice board for:
  - Onboarding completions
  - Collaboration requests
  - System-wide alerts
- Agents can query their own onboarding context, user intent, and KG summary from `agent_data`

### 4. Example Terminal Commands
```bash
# Start orchestrator and all agents
docker compose up --build

# Onboard a new agent (example)
curl http://localhost:8000/onboard -d '{"user_intent":"Summarize documents"}'

# Post onboarding progress manually (example)
python darchon/agent_notice_board_client.py --post --agent_id=my_agent --notice_type=onboarding_progress --payload='{"step":"config_generated"}'

# Query agent data (example, using psql)
psql -h <host> -U <user> -d <db> -c 'SELECT * FROM agent_data WHERE agent_id = "my_agent";'
```

---

**Workflow automation ensures onboarding, agent creation, and runtime coordination are seamless and reproducible. Continue to the next setup step.**
