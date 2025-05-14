import sys
import os
from pydantic_ai.mcp import MCPServerStdio

# Ensure the tools directory is in sys.path for import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from n8n_To_Pydantic_RAG import n8n_To_pydantic_RAG

# MCP entrypoint for n8n_to_pydantic_agent
if __name__ == "__main__":
    MCPServerStdio.serve_agent(n8n_To_pydantic_RAG)
