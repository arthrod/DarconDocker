# MCP Army Deployment Strategies

This document provides a comprehensive overview of deployment strategies for the MCP Army modular AI agent system. It covers local, development, staging, and production deployments, as well as best practices for security, scaling, and maintenance.

---

## 1. Local Development Deployment

### Prerequisites
- Docker Desktop (or compatible Docker engine)
- Docker Compose (v2+ recommended)
- Python 3.9+
- .env files for orchestrator/agents (secrets, ports, AGENT_GRAPH_PATH, etc.)

### Steps
1. Clone the repository and navigate to the project root.
2. Ensure all agent/tool Docker contexts are present in `docker_repos/`.
3. Review and update `docker-compose.yml` as needed.
4. Build and start all services:
   ```sh
   docker-compose up --build
   ```
5. Access orchestrator API/UI (default: http://localhost:8000)
6. Test agent endpoints using `/invoke` and `/health`.

---

## 2. Staging/Testing Deployment

- Use a separate `.env.staging` for secrets/keys.
- Deploy to a cloud VM or managed Docker service (e.g., AWS ECS, Azure Container Apps).
- Use a staging branch for CI/CD pipelines.
- Enable logging and monitoring (see `deployment/monitoring.md`).

---

## 3. Production Deployment

### Best Practices
- Use strong secrets in `.env.production` (never commit secrets to git).
- Restrict network access (firewall, Docker network isolation).
- Use HTTPS (reverse proxy: Traefik, Nginx, or Caddy).
- Enable persistent storage for memory bank and agent state.
- Auto-scale agents using Docker Swarm/Kubernetes if needed.
- Enable health checks and auto-restart policies in Docker Compose.
- Monitor with Prometheus/Grafana or similar (see `deployment/monitoring.md`).

### Steps
1. Prepare production `.env` files for all services.
2. Set up secure Docker host (Linux VM, cloud instance, etc.).
3. Deploy with:
   ```sh
   docker-compose -f docker-compose.yml --env-file .env.production up -d --build
   ```
4. Set up reverse proxy for HTTPS and routing.
5. Monitor logs, metrics, and health endpoints.

---

## 4. CI/CD Integration
- Use GitHub Actions, GitLab CI, or similar to automate build, test, and deploy.
- Use separate jobs for build, test, and deploy stages.
- Store secrets in CI/CD vaults, not in code.

---

## 5. Security & Secrets Management
- Never commit secrets to version control.
- Use Docker secrets, Vault, or cloud KMS for production.
- Rotate secrets regularly.
- Restrict API access with authentication (see `deployment/security.md`).

---

## 6. Troubleshooting & Recovery
- Use `docker-compose logs` and `/health` endpoints for diagnostics.
- Document common issues and fixes in `deployment/troubleshooting.md`.
- Always back up persistent volumes.

---

## 7. Reference
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Best Practices for Docker](https://docs.docker.com/develop/dev-best-practices/)
- [Traefik](https://doc.traefik.io/traefik/), [Nginx](https://nginx.org/en/docs/)
