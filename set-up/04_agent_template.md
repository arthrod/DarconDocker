# 04_agent_template.md

## Agent Template Setup

### 1. Create a New Agent Directory
```bash
mkdir -p docker_repos/my_new_agent
cd docker_repos/my_new_agent
```

### 2. Create a FastAPI App
- `main.py`:
```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/invoke")
def invoke(payload: dict):
    # Implement agent logic here
    return {"result": "Agent response"}
```

### 3. Create a Dockerfile
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4. Create an Agent Card
- `agent_card.json` (metadata for discovery):
```json
{
  "name": "my_new_agent",
  "capabilities": ["summarization", "translation"],
  "endpoints": ["/invoke"],
  "description": "A demo agent."
}
```

### 5. Create a Config Template
- `config_template.env`:
```
EXAMPLE_ENV_VAR=your_value_here
```

### 6. Register Agent in Docker Compose
- **PLANNED:** Automate this step from onboarding logic.
- Planning method signature:
  ```python
  def register_agent_in_docker_compose(agent_name: str, agent_config: dict) -> None:
      """Add agent service to docker-compose.yml during onboarding."""
      pass
  ```
- Example snippet:
  ```yaml
  my_new_agent:
    build: ./docker_repos/my_new_agent
    ports:
      - "8081:8080"
  ```# Use unique port
  env_file:
    - ./docker_repos/my_new_agent/config_template.env
```

### 7. Build & Run
```bash
docker compose up --build my_new_agent
```

---

**Repeat for each new agent. Continue to the next setup step.**
