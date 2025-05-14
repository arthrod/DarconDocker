# MCP Army Testing Strategy

This document outlines the testing strategy for the MCP Army system.

## 1. Unit Testing
- Write unit tests for all core orchestrator modules in `darchon/`.
- Test agent logic modules individually before containerization.
- Use pytest or unittest for Python modules.

## 2. Integration Testing
- Test agent containers in isolation using their `/invoke` and `/health` endpoints.
- Use Docker Compose to spin up orchestrator and agent containers for end-to-end tests.
- Validate onboarding, registration, and agent discovery flows.

## 3. API Testing
- Use tools like Postman or HTTPie to test orchestrator and agent APIs.
- Validate all `/invoke` and `/health` endpoints for correct responses and error handling.

## 4. Multi-Agent Workflow Testing
- Test Agent Conference Graph (LangGraph) flows for all-way communication and aggregation.
- Simulate user requests and verify aggregator node outputs.

## 5. Continuous Integration
- Integrate tests into CI/CD pipelines (GitHub Actions, GitLab CI, etc.).
- Run all tests on pull requests and merges.

## 6. Documentation
- Document test cases and results in `progress.md` or separate test reports.
- Reference this strategy in `activeContext.md`.

---
