# Agent Template: Core Features & Templating Questionnaire

**Architecture Note:**
- Each agent is linked to a dedicated repo in `docker_repos/` (Dockerfile, code, config).
- Agents are registered as services in a single `docker-compose.yml` (the system's source of truth).
- Onboarding ensures repo selection, config, and compose file are always in sync.

## Overview
The agent template defines the structure, configuration, and initialization logic for each RAG agent in the MCP RAG Army system. It is designed to be reusable and user-driven, enabling rapid and consistent creation of new agents through an interactive questionnaire.

## Core Features & Capabilities
- **Reusable Agent Blueprint:** Standardizes how agents are defined and deployed.
- **Interactive Questionnaire:** Guides the user through required configuration (network, name, port, system prompt, A2A card, repo selection).
- **Dynamic Config Generation:** User responses are used to generate/update the agent's config files and Docker Compose service definitions.
- **A2A Card Integration:** Captures agent metadata for discovery and communication.
- **Repo Assignment:** Allows selection of a codebase or Docker image from the `docker_repos` directory.
- **Persistence:** All user input is saved for reproducibility and future updates.

## Templating Questionnaire Flow
1. **Prompt User for:**
    - Network name (shared Docker network)
    - Agent name (unique identifier)
    - Port (host/container mapping)
    - System prompt (custom instructions)
    - A2A agent card details (capabilities, endpoints, description)
    - Repo selection (from `docker_repos`)
2. **Validate Inputs:** Ensure uniqueness and valid values.
3. **Generate/Update Files:**
    - Update `docker-compose.yml` with new agent service
    - Create/update agent config (e.g., `agent_card.json`, `.env`)
    - Update agent directory structure if needed
    - Persist metadata in `features/` or `docker_repos/` as required
4. **Agent Test Prompt:**
    - Orchestrator sends a test prompt to the new agent; the response is displayed to the user.
5. **Agent Benchmarking:**
    - Orchestrator benchmarks the new agent (latency, correctness, resource usage).
    - Results and a final 'Agent is ready' message are shown to the user before the agent is considered available.
6. **Repeat for Multiple Agents:** Support batch initialization.

## How User Input Updates the System
- **docker-compose.yml:** Adds/updates agent service blocks based on user choices.
- **Agent Config Files:** Populates system prompt, port, and A2A card info.
- **docker_repos:** Links agent to its code/image source.
- **Documentation:** Optionally updates `features/` or `api/` docs for traceability.

## Integration in Project Workflow
- The agent template and questionnaire are invoked during the initial setup (or when adding new agents).
- User-driven config ensures every agent is uniquely tailored yet standardized.
- All changes are reflected in both runtime configs and project documentation for transparency and reproducibility.

---

# How It All Fits Together

- **Single Source of Truth:** All agent configs, metadata, and repo assignments are tracked in version-controlled files.
- **Interactive Setup:** The questionnaire ensures every agent is initialized with complete, validated, and user-approved settings.
- **Automated File Updates:** No manual editing of core configs—user input drives all downstream changes.
- **Extensibility:** New agent types, features, or config options can be added to the template/questionnaire as the system evolves.
- **Reproducibility:** The entire setup, from agent creation to orchestration, can be recreated or updated by rerunning the initialization process with the template.

This approach ensures rapid, error-resistant agent deployment and a transparent, maintainable multi-agent system.
