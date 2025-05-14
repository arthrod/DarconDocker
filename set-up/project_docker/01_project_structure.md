# 01_project_structure.md

## Project Directory Structure for MCP Army

### 1. Create the Root Project Directory
If not already done:
```bash
mkdir -p Docker_MCP_Server
cd Docker_MCP_Server
```

### 2. Create Main Subdirectories
```bash
mkdir -p docker_repos darchon features deployment api custom_tools set-up
```

- **docker_repos/**: Each agent's code, Dockerfile, and config templates go here. Example: `docker_repos/my_agent/`
- **darchon/**: Orchestrator, onboarding graph, server graph, and notice board client.
- **features/**: Feature specs, Supabase schemas, integration and testing docs.
- **deployment/**: Deployment, security, monitoring, troubleshooting docs.
- **api/**: (Optional) API documentation or OpenAPI specs.
- **custom_tools/**: Any custom scripts, utilities, or agent helpers.
- **set-up/**: All setup guides and scripts (including this one).

### 3. Create Memory Bank Files
```bash
touch projectbrief.md productContext.md systemPatterns.md techContext.md activeContext.md progress.md .clinerules
```

- These markdown files are your project memory bank. They document all decisions, workflows, and architecture.

### 4. Initialize Git
```bash
git init
git add .
git commit -m "Initial MCP Army structure"
```

### 5. (Optional) Create a Remote Git Repository
- On GitHub/GitLab/Bitbucket, create a new repository.
- Link it:
  ```bash
  git remote add origin <your-git-remote-url>
  git branch -M main
  git push -u origin main
  ```

---

**Your directory and memory bank are now ready. Continue to the next setup step.**
