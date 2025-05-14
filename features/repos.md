# Repositories Configuration

## Purpose
This file lists and describes external repositories (Docker images, code repos, etc.) that are used or referenced by the system.

## Recommended Usage
- List all Docker images for agents, orchestrator, and shared components
- Include source code repository URLs (e.g., GitHub, GitLab)
- Document versioning/tagging strategies for reproducibility
- Reference any external tools or dependencies

## Example Structure
```
- agents/agent1: docker.io/yourorg/agent1:latest
- agents/agent2: docker.io/yourorg/agent2:v1.0.0
- orchestrator: docker.io/yourorg/orchestrator:main
- shared-utils: https://github.com/yourorg/shared-utils.git@v2.3.1
```

## Notes
- Keep this file up to date as you add, remove, or update components.
- This approach helps with reproducibility, CI/CD, and onboarding.
