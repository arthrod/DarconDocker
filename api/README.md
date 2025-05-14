# API Communication Protocols

This document describes the API communication protocols and standards for the Docker MCP RAG Army system, including orchestrator, agents, and agent-to-agent (A2A) interactions.

---

## Communication Architecture Overview

All API and agent-to-agent communication in the MCP Army system is conducted over HTTP/JSON using standardized FastAPI `/invoke` endpoints. Every agent, tool, orchestrator, and infrastructure service (including Supabase) runs as a container on the shared Docker network (`network_xxx` or your actual network name), enabling seamless REST API calls and service discovery between containers. All communication is internal to Docker—no external URLs are needed.

- **User → Orchestrator:**
  - Users interact with the orchestrator via REST API and MCP server (UI, CLI, or direct HTTP calls).
- **Orchestrator → Agent(s):**
  - The orchestrator calls agent `/invoke` endpoints for onboarding, benchmarking, and workflow execution.
- **Agent ↔ Agent (A2A):**
  - Agents can communicate with each other using the same `/invoke` endpoints. This is orchestrated by the Agent Conference Graph (LangGraph), which enables all-way messaging, aggregation, and advanced workflows.
- **Aggregator Node:**
  - Aggregates and summarizes agent responses before returning results to the orchestrator/user.

All communication routes through the Docker network, ensuring secure, efficient, and language-agnostic service discovery and messaging.

For a full visual reference, see [../communication_ascii.txt](../communication_ascii.txt).

---

## Protocols & Standards
- **HTTP/JSON:** All communication between orchestrator and agents uses RESTful HTTP with JSON payloads.
- **FastAPI:** Both orchestrator and agents expose FastAPI endpoints.
- **Model Context Protocol (MCP):** Standardizes request/response formats for agent-tool and orchestrator-agent messaging.
- **A2A Protocol:** Defines agent-to-agent messaging, routed via orchestrator or direct HTTP calls.

---

## Repo-to-Agent and Agent-to-Config Architecture

- **Repo-to-Agent Linkage:**
  - Each agent is built from a dedicated repo in `docker_repos/` (e.g., `docker_repos/agent1/`).
  - During onboarding, the orchestrator prompts the user to select a repo for each agent; this repo provides the Dockerfile, source code, and config templates.
  - The selected repo is used as the build context for the agent's Docker image and as the source for its config files (e.g., `.env`, agent card).

- **Agent Registration in docker-compose.yml:**
  - All agents and the orchestrator are defined as services in a single `docker-compose.yml` file (the system's source of truth).
  - For each agent, `docker-compose.yml` specifies:
    - Service name (e.g., `agent1`)
    - Build context (repo path)
    - Internal and external ports
    - Environment/config files
    - Network assignment
  - This file is auto-generated/updated during onboarding to ensure it matches the current set of agents and their configs.

- **Orchestrator Discovery:**
  - The orchestrator reads `docker-compose.yml` (directly or via Docker API) to discover all agent services.
  - It queries agent card endpoints for metadata and status, and registers/benchmarks agents accordingly.

---

## Docker Networking & Agent Port Assignment

- **Each agent and the orchestrator run in their own Docker container** and expose FastAPI endpoints on a dedicated port (e.g., 8001, 8002, 9000).
- **Docker Compose** defines the shared network and maps each agent's internal port to a host port if needed.
- **Internal Communication:**
  - Inside Docker, agents and orchestrator communicate using service names and internal ports (e.g., `http://agent1:8001/invoke`).
- **External Communication:**
  - Host-to-container access is via mapped host ports (e.g., `localhost:8001`).
- **Port Assignment:**
  - Each agent repo should specify its default port (in `.env.example` or config).
  - During onboarding, users are prompted for the agent's port (internal) and, optionally, the host port.
- **Example Docker Compose (excerpt):**
  ```yaml
  services:
    orchestrator:
      build: ./orchestrator
      ports:
        - "9000:9000"
      networks:
        - mcpnet
    agent1:
      build: ./docker_repos/agent1
      ports:
        - "8001:8001"
      networks:
        - mcpnet
    agent2:
      build: ./docker_repos/agent2
      ports:
        - "8002:8002"
      networks:
        - mcpnet
  networks:
    mcpnet:
      driver: bridge
  ```
- **Summary Table:**

| Component      | Docker Service | Internal Port | Host Port | API Endpoints Exposed             |
|---------------|---------------|--------------|-----------|-----------------------------------|
| Orchestrator  | orchestrator  | 9000         | 9000      | /invoke, /status, /agent_card, ...|
| Agent 1       | agent1        | 8001         | 8001      | /invoke, /status, /agent_card, ...|
| Agent 2       | agent2        | 8002         | 8002      | /invoke, /status, /agent_card, ...|

- **Onboarding & Config Guidance:**
  - Port assignment is a required onboarding step.
  - Each agent's config and `docker-compose.yml` must reflect the chosen port.
  - Agents must document their default port and endpoints in their repo docs.

---

## Key Endpoints
- `/invoke` (POST): Main endpoint for invoking agent tools/tasks
- `/status` (GET): Health and readiness check
- `/agent_card` (GET): Returns agent metadata (capabilities, endpoints, description)
- `/benchmark` (POST): Orchestrator sends benchmarking/test prompts, receives results

---

## Example Message Structure (MCP)
```json
{
  "sender": "orchestrator",
  "recipient": "agent1",
  "task": "summarize",
  "payload": { "text": "..." },
  "protocol": "MCPv1"
}
```

---

## Agent Registration & Benchmarking
- Onboarding includes orchestrator sending test and benchmark prompts to new agents.
- Agents must respond to `/status` and `/benchmark` before being marked as ready.
- Results are surfaced to the user in the onboarding interface.

---

## References
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [A2A Protocol](https://www.a2aprotocol.org/)
- [MCP Protocol Spec] (internal)
