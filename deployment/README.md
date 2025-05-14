# Deployment Overview

This document describes the deployment process, configuration, and best practices for the MCP Army modular agent system.

---

## Docker Compose & Network
- Deploy the entire MCP stack using Docker Compose.
- All services (agents, orchestrator, Supabase, etc.) are connected via the shared Docker network (`network_xxx`).
- All inter-service communication is internal to Docker—no external URLs required.
- For manual setup steps and troubleshooting, see [../foundation.md](../foundation.md).

## Documentation Index
- [deployment_strategies.md](deployment_strategies.md): Full deployment strategies for local, staging, and production.
- [monitoring.md](monitoring.md): Monitoring and logging setup (Prometheus, Grafana, ELK, etc.).
- [security.md](security.md): Security best practices for secrets, networking, APIs, and containers.
- [troubleshooting.md](troubleshooting.md): Common issues, diagnostics, and recovery steps.

---

## High-Level Deployment Workflow
1. **Prepare environment:** Install Docker, Docker Compose, and required Python version.
2. **Configure `.env` files:** Set secrets, ports, and agent logic paths.
3. **Update `docker-compose.yml`:** Register all agents/tools and orchestrator.
4. **Build and start services:**
   ```sh
   docker-compose up --build
   ```
5. **Secure endpoints:** Set up reverse proxy, HTTPS, and authentication.
6. **Monitor system:** Use Prometheus, Grafana, and log aggregators.
7. **Troubleshoot as needed:** Refer to troubleshooting guide.

---

---

## Agent-Repo-Config Architecture

- **Repo-to-Agent Linkage:**
  - Each agent is built from a dedicated repo in `docker_repos/` (e.g., `docker_repos/agent1/`).
  - Onboarding prompts the user to select a repo for each agent. The selected repo is used as the build context and config source (Dockerfile, code, .env.example, agent card).

- **docker-compose.yml as Source of Truth:**
  - All agents and the orchestrator are defined as services in a single `docker-compose.yml` file.
  - For each agent, this file specifies the service name, build context, ports, env files, and network config.
  - Onboarding auto-generates/updates this file to reflect the current agent set and configuration.

- **Orchestrator Discovery:**
  - The orchestrator reads `docker-compose.yml` (or queries Docker API) to discover all agent services.
  - It uses agent card endpoints to gather metadata and manage registration, testing, and benchmarking.

---

## Deployment Structure
- **docker-compose.yml:** Main entry point for multi-agent deployment
- **.env files:** Store secrets and environment variables for each agent
- **docker_repos/:** Source of truth for agent and orchestrator Docker images/repos

---

## Deployment Process
1. **Onboarding:** Use CLI or Streamlit to onboard agents (auto-generates configs)
2. **Build & Launch:**
   - Run `docker-compose up --build` to build and start all services
3. **Orchestrator Discovery:**
   - Orchestrator scans Docker network, registers agents via agent card
4. **Agent Test & Benchmarking:**
   - Orchestrator sends test/benchmark prompts; results surfaced to user

---

## Best Practices
- Keep `docker_repos/` up to date with all images/repos
- Version control all onboarding and deployment configs
- Use `.env.example` templates to guide secure onboarding

---

## Advanced/Production
- Integrate with CI/CD for automated builds and deployments
- Monitor agent health/status via `/status` endpoints
- Use orchestration tools (Kubernetes, etc.) for scaling (future roadmap)

---

## References
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
