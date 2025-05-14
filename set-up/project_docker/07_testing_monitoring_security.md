# 07_testing_monitoring_security.md

## Testing, Monitoring, and Security for MCP Army

### 1. Testing Strategies
- Write unit tests for each agent (FastAPI endpoints, core logic)
- Write integration tests for orchestrator-agent and agent-to-agent flows
- Use `features/testing_strategy.md` for detailed scenarios
- **PLANNED:** Add real test cases and monitoring containers. Plan to create a sandbox container and build a testing agent to handle benchmarking logic.
- Planning method signature:
  ```python
  def run_agent_benchmark(agent_id: str, test_suite: dict) -> dict:
      """Run tests and benchmarks for agent in sandbox container."""
      pass
  ```
- Example test command:
```bash
pytest docker_repos/my_new_agent/tests/
```

### 2. Monitoring Setup
- Use Prometheus and Grafana for metrics and dashboards
- Follow `deployment/monitoring.md` for setup steps
- Example: Add Prometheus as a service in `docker-compose.yml`

### 3. Security Best Practices
- Store secrets in `.env` files (never commit to git)
- Enable Row-Level Security (RLS) in Supabase for all tables
- Use service keys only on backend/server-side
- Follow `deployment/security.md` for full checklist

### 4. Troubleshooting
- See `deployment/troubleshooting.md` for common issues and fixes
- Example log command:
```bash
docker compose logs orchestrator
```

---

**Testing, monitoring, and security complete the robust MCP Army foundation. Document all changes in your memory bank as you go!**
