# 00_prerequisites.md

## Prerequisites for MCP Army Build

### 1. Docker & Docker Compose
- Download and install Docker Desktop for Windows: https://www.docker.com/products/docker-desktop/
- Verify installation:
  ```bash
  docker --version
  docker compose version
  ```

### 2. Python 3.9+
- Download Python: https://www.python.org/downloads/
- Add Python to PATH during installation.
- Verify installation:
  ```bash
  python --version
  pip --version
  ```

### 3. Portainer (Optional, for Docker UI)
- Install via Docker:
  ```bash
  docker volume create portainer_data
  docker run -d -p 9000:9000 --name=portainer --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce
  ```
- Access Portainer at http://localhost:9000

### 4. Supabase Account
- Sign up at https://supabase.com/
- Create a new project (choose a strong password, select a region).
- Save your `SUPABASE_URL` and `SUPABASE_API_KEY` for later.

### 5. (Optional) Neo4j & Graphiti for Knowledge Graph
- Download Neo4j Desktop: https://neo4j.com/download/
- Install and create a new local database.
- (For Graphiti) See https://github.com/graphiti-api/graphiti for installation and usage.

---

**Once all prerequisites are complete, continue to the next setup step.**
