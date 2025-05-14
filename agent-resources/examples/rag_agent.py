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
from utils import *


RAG_UPLOADS = "RAG_uploads"


# --------------------- RAG Agent Class ---------------------
class RAGAgent(Agent):
    """An AI agent that retrieves and summarizes files stored locally."""

    def retrieve_document(self, filename: str) -> str:
        file_path = os.path.join(RAG_UPLOADS, filename)
        if os.path.exists(file_path):
            if filename.endswith(".txt"):
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            elif filename.endswith(".pdf"):
                with pdfplumber.open(file_path) as pdf:
                    return "\n".join(
                        [
                            page.extract_text()
                            for page in pdf.pages
                            if page.extract_text()
                        ]
                    )
            elif filename.endswith(".csv"):
                df = pd.read_csv(file_path)
                return df.to_string()
        return "File not found."

    async def answer_query(
        self,
        question: str,
        filename: str,
        model: str,
        use_cloud: bool,
        base_url: Optional[str] = None,
    ) -> str:
        content = self.retrieve_document(filename)
        if content:
            messages = [
                {
                    "role": "system",
                    "content": f"You have access to a document named {filename}. Answer this question based on its content: {question}",
                },
                {"role": "assistant", "content": content},
            ]
            if use_cloud:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://openrouter.ai/",
                        "X-Title": "Echo-Ai/M.E.O",
                    },
                    json={"model": model, "messages": messages},
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]
                else:
                    return f"Failed to get a response from OpenRouter. Status code: {response.status_code}"
            else:
                if not base_url:
                    return "Please enter Ollama Base URL."
                response = requests.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": 0.7, "top_p": 0.9},
                    },
                )
                if response.status_code == 200:
                    response_data = response.json()
                    return response_data.get("message", {}).get(
                        "content", "Empty response from Ollama"
                    )
                else:
                    return f"Failed to get response from Ollama. Status: {response.status_code}"
        return "Could not find the requested document."


rag_agent = RAGAgent()


