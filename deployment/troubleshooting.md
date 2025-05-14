# MCP Army Troubleshooting Guide

## 1. Diagnostics
- Use `docker-compose logs <service>` to view logs for orchestrator or agents.
- Check `/health` endpoints for each service.
- Use `docker ps` and `docker stats` to monitor containers.

## 2. Common Issues
- **Container won't start:** Check logs for errors, verify `.env` files, rebuild images.
- **Agent not responding:** Confirm agent is registered in `docker-compose.yml` and accessible on Docker network.
- **Network issues:** Ensure all services are on the same Docker network (`mcpnet`).
- **API errors:** Validate request payloads and endpoint URLs.

## 3. Recovery
- Restart failed containers: `docker-compose restart <service>`
- Restore from backup if persistent data is lost.
- Document fixes in this guide for future reference.
