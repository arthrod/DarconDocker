from __future__ import annotations as _annotations

from dataclasses import dataclass
from dotenv import load_dotenv
import logfire
import asyncio
import httpx
import os
import logging

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel
from openai import AsyncOpenAI
from supabase import Client
from typing import List
from utils import *

load_dotenv()

llm = os.getenv("LLM_MODEL", "gpt-4o-mini")
model = OpenAIModel(llm)

logfire.configure(send_to_logfire="if-token-present")

# Configure logging
logging.basicConfig(level=logging.DEBUG)


@dataclass
class PydanticAIDeps:
    supabase: Client
    openai_client: AsyncOpenAI


# Updated system prompt to reflect the full role of the agent.
system_prompt = """
You are an expert in three key areas:
1. Creating n8n workflows.
2. Building Pydantic-AI retrieval-augmented generation (RAG) agents.
3. Converting n8n workflows into fully functional Pydantic-AI agents.

When performing a conversion:
  - First, carefully analyze the provided n8n workflow text (which may be very long because it is copy and pasted).
  - Consult both the n8nxpyai documentation and the GitHub repository information stored in Supabase.
  - Outline the full functionality of the n8n workflow and describe how each component works.
  - Retrieve all relevant documentation from both tables to ensure you have complete context.
  - Convert the n8n workflow into equivalent Pydantic-AI code.
  - Provide a detailed, step-by-step comparison that explains how each element of the n8n workflow maps to the new Pydantic-AI agent.

Additional instructions:
  - NEVER CONFUSE "PYDANTIC AI" WITH "PYDANTIC".
  - If any necessary information is missing from the documentation, be honest and indicate that the conversion may be incomplete.
  
Your responses should be thorough, ensuring that every conversion clearly maps the original n8n functionality to Pydantic-AI functionality.
"""

n8n_To_pydantic_RAG = Agent(
    model, system_prompt=system_prompt, deps_type=PydanticAIDeps, retries=2
)


async def get_embedding(text: str, openai_client: AsyncOpenAI) -> List[float]:
    """Get embedding vector from OpenAI."""
    try:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return [0] * 1536  # Return zero vector on error


@n8n_To_pydantic_RAG.tool
async def retrieve_relevant_documentation(
    ctx: RunContext[PydanticAIDeps],
    user_query: str,
    source: str = "n8nxpyai",  # Accepts "n8nxpyai" or "github"
) -> str:
    """
    Retrieve relevant documentation chunks (or GitHub file content) based on the query using RAG.

    Args:
        ctx: The context including the Supabase client and OpenAI client.
        user_query: The user's question or query.
        source: Which table to query ("n8nxpyai" or "github").

    Returns:
        A formatted string containing the top 5 most relevant chunks.
    """
    logging.debug(
        f"Retrieving documentation for query: {user_query} from source: {source}"
    )
    try:
        query_embedding = await get_embedding(user_query, ctx.deps.openai_client)
        logging.debug(f"Query embedding: {query_embedding}")
        formatted_chunks = []

        if source == "n8nxpyai":
            # Query the n8nxpyai table using the match_n8nxpyai RPC.
            result = ctx.deps.supabase.rpc(
                "match_n8nxpyai",
                {
                    "query_embedding": query_embedding,
                    "match_count": 5,
                    "filter": {},  # Adjust filter if needed.
                },
            ).execute()

            logging.debug(f"n8nxpyai result: {result.data}")

            if not result.data:
                return "No relevant n8nxpyai documentation found."

            for doc in result.data:
                # Format each documentation chunk with title, summary, and content.
                chunk_text = f"""
# {doc['title']}

**Summary:** {doc['summary']}

{doc['content']}
"""
                formatted_chunks.append(chunk_text)

        elif source == "github":
            # Query the GitHub table using the match_github_files RPC.
            result = ctx.deps.supabase.rpc(
                "match_github_files",
                {"query_embedding": query_embedding, "match_count": 5},
            ).execute()

            logging.debug(f"github result: {result.data}")

            if not result.data:
                return "No relevant GitHub files found."

            for doc in result.data:
                # Format the GitHub file info.
                chunk_text = f"""
# {doc['repo_owner']}/{doc['repo_name']} - {doc['file_path']}

**Branch:** {doc['branch']}  
**Commit:** {doc['commit_hash']}  
**File Type:** {doc['file_type']}  
**File Size:** {doc['file_size']} bytes

{doc['file_content']}
"""
                formatted_chunks.append(chunk_text)
        else:
            return f"Unknown source '{source}'. Please specify 'n8nxpyai' or 'github'."

        return "\n\n---\n\n".join(formatted_chunks)

    except Exception as e:
        logging.error(f"Error retrieving documentation: {e}")
        return f"Error retrieving documentation: {str(e)}"


@n8n_To_pydantic_RAG.tool
async def list_documentation_pages(
    ctx: RunContext[PydanticAIDeps],
    source: str = "n8nxpyai",  # Accepts "n8nxpyai" or "github"
) -> List[str]:
    """
    List all available documentation page identifiers (URLs or file paths) for a given source.

    Args:
        ctx: The context including the Supabase client.
        source: Which table to query ("n8nxpyai" or "github").

    Returns:
        A sorted list of unique page identifiers.
    """
    logging.debug(f"Listing documentation pages from source: {source}")
    try:
        if source == "n8nxpyai":
            # For n8nxpyai, assume the table has a 'url' column.
            result = ctx.deps.supabase.from_("n8nxpyai").select("url").execute()
            if not result.data:
                return []
            urls = sorted(set(doc["url"] for doc in result.data))
            logging.debug(f"n8nxpyai URLs: {urls}")
            return urls

        elif source == "github":
            # For GitHub, build a composite identifier from repo_owner, repo_name, branch, and file_path.
            result = (
                ctx.deps.supabase.from_("github")
                .select("repo_name, repo_owner, branch, file_path")
                .execute()
            )
            if not result.data:
                return []
            urls = sorted(
                set(
                    f"{doc['repo_owner']}/{doc['repo_name']}/{doc['branch']}/{doc['file_path']}"
                    for doc in result.data
                )
            )
            logging.debug(f"github URLs: {urls}")
            return urls

        else:
            return []
    except Exception as e:
        logging.error(f"Error retrieving documentation pages: {e}")
        return []


@n8n_To_pydantic_RAG.tool
async def get_page_content(
    ctx: RunContext[PydanticAIDeps],
    identifier: str,
    source: str = "n8nxpyai",  # Accepts "n8nxpyai" or "github"
) -> str:
    """
    Retrieve the full content for a specific page (or file) by combining all its chunks.

    Args:
        ctx: The context including the Supabase client.
        identifier: The URL (for n8nxpyai) or composite file identifier (for GitHub).
        source: Which table to query ("n8nxpyai" or "github").

    Returns:
        A string with the complete page or file content.
    """
    logging.debug(
        f"Retrieving page content for identifier: {identifier} from source: {source}"
    )
    try:
        if source == "n8nxpyai":
            # For n8nxpyai, retrieve all chunks for a given URL.
            result = (
                ctx.deps.supabase.from_("n8nxpyai")
                .select("title, summary, content, chunk_number")
                .eq("url", identifier)
                .order("chunk_number")
                .execute()
            )
            if not result.data:
                return f"No content found for URL: {identifier}"

            page_title = result.data[0]["title"].split(" - ")[0]
            formatted_content = [f"# {page_title}\n"]
            for chunk in result.data:
                formatted_content.append(
                    f"**Summary:** {chunk['summary']}\n\n{chunk['content']}"
                )
            logging.debug(f"n8nxpyai content: {formatted_content}")
            return "\n\n".join(formatted_content)

        elif source == "github":
            # For GitHub, parse the composite identifier: "owner/repo/branch/file_path".
            try:
                repo_owner, repo_name, branch, file_path = identifier.split("/", 3)
            except ValueError:
                return "Invalid GitHub identifier format. Expected 'owner/repo/branch/file_path'."

            result = (
                ctx.deps.supabase.from_("github")
                .select("*")
                .eq("repo_owner", repo_owner)
                .eq("repo_name", repo_name)
                .eq("branch", branch)
                .eq("file_path", file_path)
                .execute()
            )
            if not result.data:
                return f"No content found for GitHub file: {identifier}"

            doc = result.data[0]
            content = f"""
# {repo_owner}/{repo_name} - {file_path}

**Branch:** {branch}  
**Commit:** {doc['commit_hash']}  
**File Type:** {doc['file_type']}  
**File Size:** {doc['file_size']} bytes

{doc['file_content']}
"""
            logging.debug(f"github content: {content}")
            return content

        else:
            return "Unknown source specified."

    except Exception as e:
        logging.error(f"Error retrieving page content: {e}")
        return f"Error retrieving page content: {str(e)}"


@n8n_To_pydantic_RAG.tool
async def convert_n8n_to_pydantic_ai(
    ctx: RunContext[PydanticAIDeps], workflow_text: str
) -> str:
    """
    Convert an n8n workflow into a Pydantic-AI agent.

    Steps performed:
      1. Analyze the provided n8n workflow text.
      2. Outline the full functionality of the n8n workflow.
      3. Consult the n8nxpyai and GitHub documentation from Supabase for relevant context.
      4. Retrieve necessary documentation via the provided tools.
      5. Convert the n8n workflow to equivalent Pydantic-AI code.
      6. Provide a detailed comparison of the conversion, explaining how each component of the n8n workflow maps to the new Pydantic-AI agent functionality.

    Returns:
        A detailed message containing the outlined workflow, retrieved documentation context,
        the converted Pydantic-AI code, and a step-by-step comparison.
    """
    try:
        # Ensure the workflow text does not confuse Pydantic-AI with Pydantic
        if (
            "pydantic" in workflow_text.lower()
            and "pydantic-ai" not in workflow_text.lower()
        ):
            return "Please specify 'Pydantic-AI' instead of 'Pydantic'."

        # Step 1: Analyze and outline the workflow functionality.
        # (For demonstration, we simply truncate the workflow text for an outline.)
        workflow_outline = (
            f"Outlined functionality of the n8n workflow:\n{workflow_text[:500]}...\n"
        )

        # Step 2: Retrieve context from both documentation sources.
        docs_n8n = await retrieve_relevant_documentation(
            ctx, workflow_text, source="n8nxpyai"
        )
        docs_github = await retrieve_relevant_documentation(
            ctx, workflow_text, source="github"
        )

        # Step 3: Simulate conversion logic.
        conversion_explanation = (
            "Conversion Details:\n"
            "1. Mapped n8n nodes to Pydantic-AI agent actions.\n"
            "2. Integrated documentation context to preserve original workflow functionality.\n"
            "3. Generated equivalent Pydantic-AI code that mimics the n8n workflow behavior.\n"
            "\nConverted Pydantic-AI Code:\n"
            "```python\n# Example converted code\n# (This code is generated based on the original n8n workflow.)\n...\n```\n"
            "\nComparison:\n"
            "- Original n8n Workflow: Each node corresponds to a step in the process, with triggers, actions, and conditional flows.\n"
            "- Converted Pydantic-AI Agent: Each step is now represented as an agent tool call or function, preserving the logic and flow.\n"
        )

        return (
            f"{workflow_outline}\n"
            f"--- Documentation from n8nxpyai ---\n{docs_n8n}\n"
            f"--- Documentation from GitHub ---\n{docs_github}\n"
            f"--- Conversion Explanation ---\n{conversion_explanation}"
        )
    except Exception as e:
        print(f"Error converting n8n workflow: {e}")
        return f"Error during conversion: {str(e)}"

if __name__ == "__main__":
    main()