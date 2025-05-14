# Onboarding Interfaces: Streamlit Chat & CLI Config

## Overview
To maximize accessibility and user experience, the onboarding flow for MCP RAG Army supports both a Streamlit chat interface and a CLI configuration tool. Both interfaces follow the same onboarding logic and update the same configuration files, ensuring consistency and reproducibility.

---

## 1. Streamlit Chat Interface
- **Purpose:** Friendly, interactive web-based onboarding for all users.
- **Features:**
  - Chat-style Q&A for each onboarding step (repo, agent, .env, etc.)
  - Dynamic prompts based on RAG/AI analysis of repos
  - Real-time validation and help messages
  - File upload for `.env.example` or repo URLs
  - Progress bar and summary at the end
- **How it works:**
  - User launches Streamlit app (e.g., `streamlit run onboarding_chat.py`)
  - Chatbot guides the user through all onboarding questions
  - On completion, all configs (`docker-compose.yml`, agent cards, `.env`, etc.) are generated/updated automatically

## 2. CLI Config Tool
- **Purpose:** Fast, scriptable onboarding for technical users and automation.
- **Features:**
  - Step-by-step prompts in the terminal (using Typer/Click or similar)
  - Supports non-interactive mode via command-line arguments or environment variables
  - Mirrors the Streamlit logic and updates the same files
  - Can be integrated into CI/CD pipelines
- **How it works:**
  - User runs `python onboarding_cli.py` (or similar)
  - CLI prompts for all required onboarding info
  - All configs are generated/updated as in the chat interface

---

## Shared Logic
- Both interfaces use a shared onboarding backend (Python module) for:
  - Repo discovery/cloning
  - RAG analysis
  - Config extraction and validation
  - File generation/updating
- Ensures consistent onboarding regardless of interface

---

## Next Steps
- Scaffold `onboarding_chat.py` (Streamlit) and `onboarding_cli.py` (CLI)
- Implement shared onboarding logic as a Python module (e.g., `onboarding_core.py`)
- Reference this interface design in `features/onboarding.md` and `activeContext.md`
