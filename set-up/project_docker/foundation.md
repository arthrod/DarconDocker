# FOUNDATION.md

## MCP Army: Foundation Setup Logbook

This file is your living logbook for manually bootstrapping the MCP Army platform. Fill in each section as you work. Use this as the basis for future automation, onboarding, and agent-driven workflows.

---

## 1. Prerequisites & Environment
- [ ] List your OS, Docker, Docker Compose, Python, and any other core tools/versions.
- [ ] Note any initial system setup or config (networking, ports, users, etc).

**Prompt:**
> What is your current OS and environment? List all core tools and versions you have installed.

---

## 2. Directory & Repo Structure
- [ ] Document the root directory structure you create.
- [ ] List each agent repo you clone or create in `docker_repos/`.
- [ ] Note any custom directories or files you add.

**Prompt:**
> What does your project directory look like after initial setup? Which agent repos did you clone or create?

---

## 2b. Docker Compose & Network Setup
- [ ] Document your Docker Compose setup for darchon and related services.
- [ ] Specify the shared Docker network name (e.g., network_xxx) used for internal service communication.
- [ ] Reference your manual build/run script and Dockerfile for darchon.
- [ ] Note that Supabase and all services communicate via the shared Docker network, not via external URLs.

**Example darchon service in docker-compose.yml:**
```yaml
darchon:
  build: ./darchon
  container_name: ddarchon-docker-mcp
  ports:
    - "8501:8501"   # Streamlit UI
    - "8100:8100"   # Archon Service
  env_file:
    - ./darchon/.env
  networks:
    - network_xxx
```

**Example network section:**
```yaml
networks:
  network_xxx:
    driver: bridge
```

**Prompt:**
> What does your actual docker-compose.yml look like? What is the name of your shared Docker network? How do you build and run darchon (reference your script and Dockerfile)?

---

## 3. Manual Docker & Compose Setup
- [ ] Record how you manually create and edit Dockerfiles for each agent.
- [ ] Document how you add services to `docker-compose.yml` (service names, build context, ports, env files, etc).
- [ ] Note any custom network or volume setup.

**Prompt:**
> How did you set up Dockerfiles and docker-compose.yml for each agent? What services, ports, and configs did you use?

---

## 4. Supabase & Database (Manual)
- [ ] Describe how you set up Supabase locally (or other DB).
- [ ] List any tables you create by hand (e.g., agent_notice_board, agent_data).
- [ ] Note connection details, env vars, and how agents will access the DB (via Docker network).

**Prompt:**
> How did you start Supabase? What tables did you create? How do agents connect to the DB?

---

## 5. Manual Agent Onboarding & Testing
- [ ] Document the step-by-step process of onboarding an agent manually.
- [ ] List the config, metadata, and endpoints you set up for each agent.
- [ ] Record any manual tests you run to verify agent communication and workflow.

**Prompt:**
> How did you onboard and test each agent? What manual steps did you take to verify everything worked?

---

## 6. Troubleshooting & Gotchas
- [ ] Log any issues, errors, or surprises you encounter.
- [ ] Note how you fixed them, or what you still need to resolve.
- [ ] Capture any environment-specific quirks.

**Prompt:**
> What problems did you hit? How did you solve them (or what’s still unresolved)?

---

## 7. Foundation Complete: What’s Next?
- [ ] Summarize the current state of your manual foundation.
- [ ] List which steps you want to automate or agentize first.
- [ ] Reference this file in your memory bank and activeContext.md.

**Prompt:**
> What’s working? What’s missing? What do you want to automate or build an agent for next?

---

**Tip:**
Update this file as you go. It will become the blueprint for your first automation and onboarding agents.
