# MCP Army Security Best Practices

## 1. Secrets Management
- Never commit secrets to version control.
- Use `.env` files for development; use Docker secrets or Vault for production.
- Store secrets in CI/CD vaults for automation.

## 2. Network Security
- Restrict agent/orchestrator ports to internal Docker network (`mcpnet`).
- Use firewalls and security groups for cloud deployments.
- Use HTTPS for all external API/UI endpoints (reverse proxy).

## 3. API Security
- Require authentication for orchestrator and agent APIs.
- Use API keys, OAuth, or JWT for access control.
- Rate limit sensitive endpoints.

## 4. Container Security
- Use minimal base images for containers.
- Run containers as non-root where possible.
- Keep images up to date (patch vulnerabilities regularly).

## 5. Auditing & Compliance
- Enable logging and retain logs for audits.
- Document all access and configuration changes.
