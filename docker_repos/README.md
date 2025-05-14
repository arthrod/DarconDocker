# Docker Repositories Source of Truth

This directory serves as the main source of truth for all Docker images, repositories, and related configuration used in the MCP RAG Army system.

## Agent-Repo-Config Pattern
- Each agent is linked to a specific repo in `docker_repos/`, which contains its Dockerfile, code, and config templates.
- During onboarding, the orchestrator prompts the user to select a repo for each agent; this repo is used as the build context and config source.
- All agents (and the orchestrator) are registered in a single authoritative `docker-compose.yml`, which specifies service names, build contexts, ports, env files, and network config.
- The orchestrator discovers and manages agents by reading `docker-compose.yml` (directly or via Docker API) and by querying agent card endpoints for metadata and status.
- This ensures a single source of truth for deployment, traceability, and reproducibility across all agents and services.
- Visual flow: `docker_repos/<agent>/` → [Agent Container] → [docker-compose.yml] → [Orchestrator]
- Each agent's config and port assignment are reflected in both its repo and the compose file, ensuring correct routing and communication.

## Usage
- Add a separate file for each agent, orchestrator, or shared component as needed (e.g., `agent1.md`, `orchestrator.md`).
- Include Docker image names, tags, build instructions, and repository URLs.
- Update this directory as you add, update, or deprecate components.

## Example File Structure
- agent1.md: Details for agent1's Docker image and repo
- orchestrator.md: Details for orchestrator's image/repo
- shared.md: Shared utilities or base images

This approach ensures traceability and reproducibility for all system components.
