# 03_orchestrator_onboarding.md

## Orchestrator & Onboarding Graph Setup

### 1. Scaffold the Orchestrator Service
- Create `darchon/orchestrator.py` as a FastAPI app.
- This will:
  - Expose endpoints for onboarding, agent registry, and coordination
  - Read/write to `docker-compose.yml` for agent discovery
  - Call onboarding graph for new agent setup

### 2. Scaffold the Onboarding Graph
- Create `darchon/onboarding_graph.py`
- Implement a chain of onboarding agents:
  - `NeedsAgent`: Prompts user for initial intent ("What would you like?")
  - `RepoAgent`: Handles repo discovery/auto-cloning
  - `CodingAgent`: (Optional) Generates starter code or scaffolding
  - `ConfigAgent`: Extracts config, generates .env, docker-compose entry
  - `RankingAgent`: Benchmarks agent (latency, correctness, resource usage)
- Each agent step posts progress to the Supabase notice board and agent_data table

### 3. Example FastAPI App (orchestrator.py)
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/onboard")
def onboard_agent():
    # Call onboarding graph logic here
    return {"status": "onboarding started"}
```

### 4. Example Onboarding Graph Usage
```python
from darchon.onboarding_graph import OnboardingGraph
onboarder = OnboardingGraph()
onboarder.onboard({"user_intent": "Build a summarizer agent"})
```

### 5. Register Orchestrator in Docker Compose
- Add orchestrator service in `docker-compose.yml`:
```yaml
orchestrator:
  build: ./darchon
  ports:
    - "8000:8000"
  environment:
    - SUPABASE_URL=your_supabase_url
    - SUPABASE_API_KEY=your_service_key
```

---

**Orchestrator and onboarding logic are now scaffolded. Continue to the next setup step.**
