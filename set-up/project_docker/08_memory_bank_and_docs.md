# 08_memory_bank_and_docs.md

## Memory Bank & Documentation: Your Single Source of Truth

### 1. What is the Memory Bank?
- A set of markdown files that document all architecture, workflows, decisions, and patterns.
- Ensures reproducibility, onboarding, and troubleshooting for yourself and future collaborators.

### 2. Core Files
- `projectbrief.md`: Project goals, high-level architecture
- `productContext.md`: Problem/solution, why this system exists
- `systemPatterns.md`: Architectural patterns, protocols, onboarding/production split
- `techContext.md`: Stack, setup, and integration references
- `activeContext.md`: Current focus, new files, recent decisions
- `progress.md`: Status, roadmap, what’s next
- `.clinerules`: Implementation paths, workflow preferences, project-specific rules

### 3. Custom/Feature Files
- `features/agent_notice_board.md`, `features/agent_notice_board_supabase_schema.sql`, etc.
- Add new files for integration guides, API docs, onboarding specs, etc.
- **PLANNED:** Write missing feature specifications, API documentation, and integration guides. Types of docs to be written:
  - Feature specs (e.g., agent-driven onboarding, KG integration)
  - API docs (REST endpoints, Supabase client, agent APIs)
  - Integration guides (Graphiti/Neo4j, testing agent, monitoring)
- Reference the memory bank protocol for documentation structure.

### 4. How to Use the Memory Bank
- **Always read all memory bank files before starting new work.**
- Update the relevant file(s) after every major change or discovery.
- Reference new custom/spec files in `activeContext.md`.
- Use the memory bank as your onboarding and troubleshooting manual.

### 5. Example Workflow
```bash
# View project goals
cat projectbrief.md

# Add a new architectural pattern
echo "- New pattern: ..." >> systemPatterns.md

# Update current focus
echo "- Working on agent onboarding..." >> activeContext.md

# Log progress
echo "- Finished onboarding flow." >> progress.md
```

---

**The memory bank is your guide and logbook. Keep it up to date for maximum project intelligence!**
