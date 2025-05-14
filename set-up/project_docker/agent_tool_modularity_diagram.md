# Agent & Tool Modularity: Defaults vs. Dynamics

```mermaid
graph TD
    subgraph Shared/Default
        NET[Docker Network (mcpnet)]
        COMPOSE[docker-compose.yml (structure)]
        ONBOARD[Onboarding Logic]
        FASTAPI[Base FastAPI Pattern]
    end

    subgraph Agent/Tool 1
        DIR1[Unique Dir (repo/tool)]
        CODE1[Unique Code/Entrypoint]
        PORT1[Unique Port]
        NAME1[Unique Service Name]
        ENV1[Unique .env/Config]
        META1[Unique Metadata]
        CONTAINER1[Docker Container]
    end

    subgraph Agent/Tool 2
        DIR2[Unique Dir (repo/tool)]
        CODE2[Unique Code/Entrypoint]
        PORT2[Unique Port]
        NAME2[Unique Service Name]
        ENV2[Unique .env/Config]
        META2[Unique Metadata]
        CONTAINER2[Docker Container]
    end

    NET --> CONTAINER1
    NET --> CONTAINER2
    COMPOSE --> CONTAINER1
    COMPOSE --> CONTAINER2
    ONBOARD --> DIR1
    ONBOARD --> DIR2
    FASTAPI --> CODE1
    FASTAPI --> CODE2

    DIR1 --> CONTAINER1
    CODE1 --> CONTAINER1
    PORT1 --> CONTAINER1
    NAME1 --> CONTAINER1
    ENV1 --> CONTAINER1
    META1 --> CONTAINER1

    DIR2 --> CONTAINER2
    CODE2 --> CONTAINER2
    PORT2 --> CONTAINER2
    NAME2 --> CONTAINER2
    ENV2 --> CONTAINER2
    META2 --> CONTAINER2
```

---

## Legend
- **Shared/Default:** Docker network, compose structure, onboarding logic, and FastAPI pattern are common to all agents/tools.
- **Dynamic/Per-Agent-Tool:** Directory, code, port, service name, config, metadata, and container are unique for each agent/tool.

---

**This diagram shows how every agent/tool gets its own container and unique config, while sharing the same network and onboarding/orchestration logic.**
