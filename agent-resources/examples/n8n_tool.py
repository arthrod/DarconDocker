from __future__ import annotations as _annotations

import os
import json
import time
import threading
import logging
import subprocess
import tempfile
import asyncio
import psutil
import requests
import streamlit as st
import pandas as pd
import pdfplumber
import tiktoken
import openai
import logfire
import nest_asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv, dotenv_values, set_key
from pathlib import Path
from supabase import create_client, Client
from xml.etree import ElementTree
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal, TypedDict
from dataclasses import dataclass, field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from contextlib import asynccontextmanager
import httpx
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel
from functools import wraps
import shutil
import atexit
import streamlit.components.v1 as components
from utils import get_supabase_client, get_openai_client
from n8n_To_Pydantic_RAG import n8n_To_pydantic_RAG, PydanticAIDeps
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    RetryPromptPart,
    ModelMessagesTypeAdapter,
)

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logfire.configure(send_to_logfire="never")

# Load environment variables
env_path = "/home/ai-agent/bolt.diy/.env"
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "")
openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
TOKEN_LIMIT = 8000  # Keep under 8192 tokens per request


async def run_agent_with_streaming(user_input: str):
    logging.debug("Starting run_agent_with_streaming")
    if "pydantic" in user_input.lower() and "pydantic-ai" not in user_input.lower():
        st.error("Please specify 'Pydantic-AI' instead of 'Pydantic'.")
        return
    deps = PydanticAIDeps(supabase=supabase, openai_client=openai_client)
    async with n8n_To_pydantic_RAG.run_stream(
        user_input,
        deps=deps,
        message_history=st.session_state.n8n_messages[:-1],
    ) as result:
        partial_text = ""
        message_placeholder = st.empty()
        async for chunk in result.stream_text(delta=True):
            partial_text += chunk
            message_placeholder.markdown(partial_text)
            logging.debug(f"Received chunk: {chunk}")
        st.session_state.n8n_messages.append(ModelResponse(parts=[TextPart(content=partial_text)]))
def display_message_part(part):
    if isinstance(part, TextPart):
        st.markdown(part.content)
async def main():
    st.title("🔄 Convert n8n to 🐍 Pydantic-AI")
    st.write("You either, Drag and Drop, Ask any question about Pydantic AI, the hidden truths of the beauty of this framework lie within.")
    if "n8n_messages" not in st.session_state:
        st.session_state.n8n_messages = []
    for msg in st.session_state.n8n_messages:
        if isinstance(msg, ModelRequest) or isinstance(msg, ModelResponse):
            for part in msg.parts:
                display_message_part(part)
    user_input = st.chat_input("What questions do you have about Pydantic AI?")
    if user_input:
        st.session_state.n8n_messages.append(ModelRequest(parts=[UserPromptPart(content=user_input)]))
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            await run_agent_with_streaming(user_input)
    uploaded_workflow = st.file_uploader("Upload n8n workflow JSON", type=['json'])
    if uploaded_workflow:
        try:
            workflow_content = json.loads(uploaded_workflow.getvalue())
            st.session_state.current_workflow = workflow_content
            st.success("Workflow loaded successfully!")
            workflow_str = json.dumps(workflow_content, indent=2)
            st.session_state.n8n_messages.append(ModelRequest(parts=[UserPromptPart(content=workflow_str)]))
            with st.chat_message("user"):
                st.markdown(f"Uploaded Workflow:\n\n```json\n{workflow_str}\n```")
            with st.chat_message("assistant"):
                await run_agent_with_streaming(workflow_str)
        except json.JSONDecodeError:
            st.error("Invalid JSON file. Please upload a valid n8n workflow JSON.")


if __name__ == "__main__":
        asyncio.run(main())
