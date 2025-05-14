from __future__ import annotations as _annotations

from dataclasses import dataclass
from dotenv import load_dotenv
import logfire
import asyncio
import httpx
import os
import sys
import json
from typing import List
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel
from openai import AsyncOpenAI
from supabase import Client

# Add the parent directory to sys.path to allow importing from the parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.utils import get_env_var
from archon.agent_prompts import primary_coder_prompt
from archon.agent_tools import (
    retrieve_relevant_github_code_tool,
    list_github_repositories_tool,
    get_github_content_tool,
    list_github_sources_tool,
    clone_github_repo_tool,
    process_youtube_url_tool,
    crawl_website_tool,
    retrieve_youtube_content_tool,
    list_youtube_sources_tool,
    retrieve_website_content_tool,
    list_website_sources_tool,
    is_github_url,
    is_youtube_url,
    is_web_url,
    extract_github_url,
    extract_youtube_url,
    extract_web_url,
    get_capabilities
)

load_dotenv()

provider = get_env_var('LLM_PROVIDER') or 'OpenAI'
llm = get_env_var('PRIMARY_MODEL') or 'gpt-4o-mini'
base_url = get_env_var('BASE_URL') or 'https://api.openai.com/v1'
api_key = get_env_var('LLM_API_KEY') or 'no-llm-api-key-provided'

model = AnthropicModel(llm, api_key=api_key) if provider == "Anthropic" else OpenAIModel(llm, base_url=base_url, api_key=api_key)

logfire.configure(send_to_logfire='if-token-present')

@dataclass
class GitHubCoderDeps:
    supabase: Client
    embedding_client: AsyncOpenAI
    reasoner_output: str
    advisor_output: str

github_coder = Agent(
    model,
    system_prompt=primary_coder_prompt,
    deps_type=GitHubCoderDeps,
    retries=2
)

@github_coder.system_prompt  
def add_reasoner_output(ctx: RunContext[str]) -> str:
    return f"""
    
    Additional GitHub repositories and patterns from the reasoner LLM: 
    {ctx.deps.reasoner_output}

    Recommended GitHub sources and code patterns from the advisor agent:
    {ctx.deps.advisor_output}
    
    When using GitHub repositories:
    1. ALWAYS access the GitHub table from Supabase and use repo names to cross-reference the source column
    2. Always check the source column first to identify relevant repositories
    3. Try different spelling variations of keywords when searching
    4. Match your search keyword to the appropriate source before retrieving content
    5. Pay attention to both summary and content sections in retrieved documents
"""

@github_coder.tool
async def retrieve_relevant_github_code(ctx: RunContext[GitHubCoderDeps], user_query: str) -> str:
    """
    Retrieve relevant GitHub code snippets based on the query with RAG.
    ALWAYS access the GitHub table from Supabase and use repo names to cross-reference the source column.
    
    Args:
        ctx: The context including the Supabase client and OpenAI client
        user_query: The user's code request or query
        
    Returns:
        A formatted string containing the most relevant GitHub code snippets and patterns
    """
    return await retrieve_relevant_github_code_tool(ctx.deps.supabase, ctx.deps.embedding_client, user_query)

@github_coder.tool
async def list_github_sources(ctx: RunContext[GitHubCoderDeps]) -> List[str]:
    """
    Retrieve a list of all unique sources in the github table.
    
    Args:
        ctx: The context including the Supabase client
        
    Returns:
        List[str]: List of unique source values from the github table
    """
    return await list_github_sources_tool(ctx.deps.supabase)


@github_coder.tool
async def list_github_repositories(ctx: RunContext[GitHubCoderDeps]) -> List[str]:
    """
    Retrieve a list of all available GitHub repositories indexed in the system.
    This will help you find the right repository sources to reference in your code generation.
    
    Returns:
        List[str]: List of unique repository sources in the GitHub table
    """
    return await list_github_repositories_tool(ctx.deps.supabase)

@github_coder.tool
async def get_github_content(ctx: RunContext[GitHubCoderDeps], source: str) -> str:
    """
    Retrieve the full content of a specific GitHub repository by combining all its chunks.
    ALWAYS access the GitHub table from Supabase and use repo names to cross-reference the source column.
    
    Args:
        ctx: The context including the Supabase client
        source: The repository source identifier to retrieve
        
    Returns:
        str: The complete repository content with all chunks combined in order
    """
    return await get_github_content_tool(ctx.deps.supabase, source)

@github_coder.tool
async def clone_github_repo(ctx: RunContext[GitHubCoderDeps], repo_url: str) -> str:
    """
    Clone a GitHub repository and index it in the Supabase database for RAG.
    ONLY use this tool when a user explicitly mentions or requests to clone a GitHub repository.
    
    Args:
        ctx: The context including the Supabase client
        repo_url: The GitHub repository URL to clone and process
        
    Returns:
        str: Status message indicating success or error
    """
    return clone_github_repo_tool(repo_url)

@github_coder.tool
async def process_youtube_url(ctx: RunContext[GitHubCoderDeps], youtube_url: str) -> str:
    """
    Process a YouTube video or playlist URL and add its transcripts to the RAG system.
    ONLY use this tool when a user explicitly mentions or requests to process a YouTube video or playlist.
    
    Args:
        ctx: The context including the Supabase client
        youtube_url: The YouTube video or playlist URL to process
        
    Returns:
        str: Status message indicating success or error
    """
    return process_youtube_url_tool(youtube_url)

@github_coder.tool
async def retrieve_youtube_content(ctx: RunContext[GitHubCoderDeps], user_query: str) -> str:
    """
    Retrieve relevant YouTube content based on the query with RAG.
    This tool searches through processed YouTube transcripts to find relevant information.
    
    Args:
        ctx: The context including the Supabase client and OpenAI client
        user_query: The user's query about YouTube content
        
    Returns:
        A formatted string containing the most relevant YouTube transcript segments
    """
    return await retrieve_youtube_content_tool(ctx.deps.supabase, ctx.deps.embedding_client, user_query)

@github_coder.tool
async def list_youtube_sources(ctx: RunContext[GitHubCoderDeps]) -> List[str]:
    """
    Retrieve a list of all unique video sources in the YouTube table.
    This helps identify what YouTube content is available for retrieval.
    
    Args:
        ctx: The context including the Supabase client
        
    Returns:
        List[str]: List of unique source values from the YouTube table
    """
    return await list_youtube_sources_tool(ctx.deps.supabase)

@github_coder.tool
async def crawl_website(ctx: RunContext[GitHubCoderDeps], url: str, source_name: str = None, crawl_type: str = None) -> str:
    """
    Crawl a website or sitemap URL and add its content to the RAG system.
    ONLY use this tool when a user explicitly mentions or requests to crawl a website or sitemap.
    
    Args:
        ctx: The context including the Supabase client
        url: The website URL or sitemap URL to crawl
        source_name: Optional name to identify the source (defaults to domain name)
        crawl_type: Optional type of crawl: 'single' for a single page, 'sitemap' for a sitemap URL
        
    Returns:
        str: Status message indicating success or error
    """
    return crawl_website_tool(url, source_name, crawl_type)

@github_coder.tool
async def retrieve_website_content(ctx: RunContext[GitHubCoderDeps], user_query: str) -> str:
    """
    Retrieve relevant website content based on the query with RAG.
    This tool searches through crawled websites to find relevant information.
    
    Args:
        ctx: The context including the Supabase client and OpenAI client
        user_query: The user's query about website content
        
    Returns:
        A formatted string containing the most relevant website content segments
    """
    return await retrieve_website_content_tool(ctx.deps.supabase, ctx.deps.embedding_client, user_query)

@github_coder.tool
async def list_website_sources(ctx: RunContext[GitHubCoderDeps]) -> List[str]:
    """
    Retrieve a list of all unique website sources in the crawled_pages table.
    This helps identify what website content is available for retrieval.
    
    Args:
        ctx: The context including the Supabase client
        
    Returns:
        List[str]: List of unique source values from the crawled_pages table's metadata
    """
    return await list_website_sources_tool(ctx.deps.supabase)

@github_coder.tool
async def describe_capabilities(ctx: RunContext[GitHubCoderDeps]) -> str:
    """
    Returns a user-friendly description of the agent's capabilities.
    Use this tool when a user asks "What are your capabilities?" or "What can you do?"
    
    Returns:
        A formatted description of all agent capabilities with examples
    """
    return get_capabilities()

@github_coder.system_prompt
def detect_urls(ctx: RunContext[str]) -> str:
    """
    Detect URLs in user messages and ask if the user wants to process them.
    This prompt will be added to the system prompt to guide URL detection.
    """
    return """
If you detect a GitHub repository URL in the user's message, ask if they want to clone it:
"I noticed you mentioned a GitHub repository. Would you like me to clone it for you?"

If you detect a YouTube URL, ask if they want to process the transcript:
"I noticed you shared a YouTube link. Would you like me to extract and process the transcript?"

If you detect a website URL, ask if they want to crawl it:
"I noticed you shared a website URL. Would you like me to crawl and index this content?"
"""
    
    # URL detection is now handled through a standard system prompt
    # rather than trying to parse the input directly