from __future__ import annotations as _annotations

import os
import json
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
import shutil
import atexit
import subprocess
import tempfile
import threading
import logging
import httpx
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal, TypedDict
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv, dotenv_values, set_key
from functools import wraps
import psycopg2
from psycopg2.extras import Json
from supabase import create_client, Client
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from contextlib import contextmanager, asynccontextmanager
from streamlit.runtime.scriptrunner.script_runner import ScriptRunContext, get_script_run_ctx, add_script_run_ctx
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path  # Ensure Path is imported

load_dotenv()

# Define RAG_UPLOADS and create the directory if it doesn't exist
RAG_UPLOADS = os.getenv("RAG_UPLOADS", "./uploads")
Path(RAG_UPLOADS).mkdir(exist_ok=True)

def extract_urls_from_sitemap(sitemap_url: str) -> list:
    """
    Recursively extract URLs from a sitemap or sitemap index.
    
    Args:
        sitemap_url (str): The URL of the sitemap or sitemap index.
    
    Returns:
        list: A list of URLs extracted from the sitemap.
    """
    try:
        response = requests.get(sitemap_url)
        response.raise_for_status()
        tree = ET.fromstring(response.content)
        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = []
        if tree.tag.endswith("urlset"):
            for url_elem in tree.findall("ns:url", namespaces=namespace):
                loc_elem = url_elem.find("ns:loc", namespaces=namespace)
                if loc_elem is not None and loc_elem.text:
                    urls.append(loc_elem.text.strip())
        elif tree.tag.endswith("sitemapindex"):
            for sitemap in tree.findall("ns:sitemap", namespaces=namespace):
                loc_elem = sitemap.find("ns:loc", namespaces=namespace)
                if loc_elem is not None and loc_elem.text:
                    nested_urls = extract_urls_from_sitemap(loc_elem.text.strip())
                    urls.extend(nested_urls)
        return urls
    except Exception as e:
        st.error(f"Failed to parse sitemap {sitemap_url}: {e}")
        return []

def parse_urls(url_input: str) -> List[str]:
    urls = []
    for url in url_input.strip().split("\n"):
        url = url.strip()
        if not url:
            continue
        if url.lower().endswith(".xml"):
            try:
                response = requests.get(url)
                root = ET.fromstring(response.content)
                namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                sitemap_urls = [loc.text for loc in root.findall(".//ns:loc", namespace)]
                urls.extend(sitemap_urls)
            except Exception as e:
                st.error(f"Error processing sitemap {url}: {str(e)}")
        else:
            urls.append(url)
    return urls

def check_database_connection():
    """Check if the database connection is successful."""
    try:
        conn = get_db_connection()
        conn.close()
        return True, "Database connection successful."
    except Exception as e:
        return False, f"Database connection failed: {str(e)}"

@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]
    embedding: List[float]

def clean_text_field(text: str, default: str = "Untitled") -> str:
    if text is None:
        return default
    cleaned = str(text).strip()
    return cleaned if cleaned else default

def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = start + chunk_size
        if end >= text_length:
            chunks.append(text[start:].strip())
            break
        chunk = text[start:end]
        code_block = chunk.rfind("```")
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block
        elif "\n\n" in chunk:
            last_break = chunk.rfind("\n\n")
            if last_break > chunk_size * 0.3:
                end = start + last_break
        elif ". " in chunk:
            last_period = chunk.rfind(". ")
            if last_period > chunk_size * 0.3:
                end = start + last_period + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(start + 1, end)
    return chunks

def log_memory(prefix: str = "") -> int:
    process = psutil.Process(os.getpid())
    current_mem = process.memory_info().rss
    print(f"{prefix} Current Memory: {current_mem // (1024 * 1024)} MB")
    return current_mem // (1024 * 1024)

@contextmanager
def maintain_session_context():
    ctx = get_script_run_ctx()
    try:
        yield ctx
    finally:
        if ctx:
            add_script_run_ctx(ctx)

def safe_streamlit_status(container, message: str, type: str = "info"):
    try:
        with maintain_session_context():
            if type == "info":
                container.info(message)
            elif type == "error":
                container.error(message)
            elif type == "success":
                container.success(message)
            elif type == "warning":
                container.warning(message)
    except Exception:
        print(f"{type.upper()}: {message}")

def add_title_to_crawl_result(result, title):
    result.title = title
    return result

def display_memory_usage(container, message: str):
    memory_mb = psutil.Process(os.getpid()).memory_info().rss // (1024 * 1024)
    safe_streamlit_status(container, f"{message}\n**Memory:** {memory_mb} MB", "info")

@st.cache_resource
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "10.147.20.2"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )

def check_db_connection_status():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        return True, "✅ Connected to Database"
    except Exception as e:
        return False, f"❌ Database Error: {str(e)}"

@st.cache_resource
def initialize_youtube_api():
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            st.error("YouTube API key not found in environment variables!")
            return None
        youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        return youtube
    except Exception as e:
        st.error(f"Failed to initialize YouTube API: {str(e)}")
        return None

def extract_youtube_ids(url: str) -> tuple[str, str]:
    playlist_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=([^&\s]+)',
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[^&\s]+&list=([^&\s]+)',
    ]
    video_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^&\s]+)',
        r'(?:https?://)?(?:www\.)?youtu\.be/([^?\s]+)',
    ]
    for pattern in playlist_patterns:
        match = re.match(pattern, url)
        if match:
            return 'playlist', match.group(1)
    for pattern in video_patterns:
        match = re.match(pattern, url)
        if match:
            return 'video', match.group(1)
    return None, None

def get_video_transcript(video_id: str) -> str:
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry["text"] for entry in transcript_list])
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        st.warning(f"No transcript available for video ID {video_id}: {str(e)}")
        return ""
    except Exception as e:
        st.error(f"Error fetching transcript for video ID {video_id}: {str(e)}")
        return ""

def get_all_videos_from_playlist(playlist_id: str, progress_bar=None) -> list:
    youtube = initialize_youtube_api()
    if not youtube:
        return []
    try:
        all_items = []
        next_page_token = None
        while True:
            request = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            if 'error' in response:
                st.error(f"YouTube API Error: {response['error']['message']}")
                return []
            items = response.get("items", [])
            all_items.extend(items)
            if progress_bar:
                progress_bar.progress(len(all_items) / 100)
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        videos = []
        for item in all_items:
            snippet = item["snippet"]
            videos.append({
                "video_id": snippet["resourceId"]["videoId"],
                "title": snippet["title"],
                "description": snippet["description"],
                "publishedAt": snippet["publishedAt"],
                "channelTitle": snippet["channelTitle"]
            })
        return videos
    except Exception as e:
        st.error(f"Error fetching playlist videos: {str(e)}")
        return []

def preview_playlist_videos(playlist_id: str) -> list:
    youtube = initialize_youtube_api()
    if not youtube:
        return []
    try:
        videos = get_all_videos_from_playlist(playlist_id)
        return videos
    except Exception as e:
        st.error(f"Error fetching playlist preview: {str(e)}")
        return []

def process_youtube_playlist(playlist_id: str):
    try:
        status_container = st.empty()
        progress_bar = st.progress(0)
        video_status = st.empty()
        error_log = []
        
        status_container.info("Starting playlist processing...")
        videos = get_all_videos_from_playlist(playlist_id, progress_bar)
        if not videos:
            status_container.error("No videos found in the playlist.")
            return
        status_container.success(f"Found {len(videos)} videos in the playlist.")
        conn = get_db_connection()
        
        for idx, video in enumerate(videos, 1):
            try:
                video_status.info(f"Processing video {idx}/{len(videos)}: {video['title']}")
                video_id = video["video_id"]
                transcript = get_video_transcript(video_id)
                if not transcript:
                    error_log.append(f"No transcript available for: {video['title']} ({video_id})")
                    continue
                content = (
                    f"Title: {video['title']}\n"
                    f"Channel: {video['channelTitle']}\n"
                    f"Published: {video['publishedAt']}\n\n"
                    f"Transcript:\n{transcript}"
                )
                metadata = {
                    "source": "YouTube",
                    "source_type": "video",
                    "video_id": video_id,
                    "title": video["title"],
                    "channel": video["channelTitle"],
                    "published_at": video["publishedAt"],
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "playlist_id": playlist_id
                }
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO documents (content, metadata)
                            VALUES (%s, %s)
                            RETURNING id;
                            """,
                            (content, Json(metadata))
                        )
                        doc_id = cur.fetchone()[0]
                        conn.commit()
                        video_status.success(f"Successfully processed and stored: {video['title']} (Document ID: {doc_id})")
                except Exception as db_error:
                    conn.rollback()
                    error_msg = f"Database error with video {video['title']}: {str(db_error)}"
                    error_log.append(error_msg)
                    video_status.error(error_msg)
            except Exception as e:
                error_msg = f"Error processing video {video['title']}: {str(e)}"
                error_log.append(error_msg)
                video_status.error(error_msg)
            progress_bar.progress((idx) / len(videos))
        
        if error_log:
            with st.expander("Processing Errors", expanded=True):
                st.error("The following errors occurred during processing:")
                for error in error_log:
                    st.write(f"- {error}")
    except Exception as e:
        st.error(f"Fatal error processing playlist: {str(e)}")
    finally:
        if conn:
            conn.close()

class FileChangeHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            st.session_state["config_reloaded"] = True

    def on_deleted(self, event):
        if not event.is_directory:
            st.session_state["config_reloaded"] = True

# Start file monitoring; guard against Streamlit context errors when not running under streamlit.
try:
    if "monitoring_started" not in st.session_state:
        monitoring_thread = threading.Thread(target=lambda: Observer().schedule(FileChangeHandler(), path=RAG_UPLOADS, recursive=False) or Observer().start(), daemon=True)
        monitoring_thread.start()
        st.session_state.monitoring_started = True
except Exception as e:
    print(f"File monitoring not started: {e}")

def load_and_process_pdfs(source_dir: str):
    loader = DirectoryLoader(source_dir, glob="**/*.pdf", loader_cls=PyPDFLoader)
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )
    chunks = text_splitter.split_documents(documents)
    return chunks

def save_uploaded_file(uploaded_file):
    file_path = os.path.join(RAG_UPLOADS, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.success(f"Saved file: {uploaded_file.name}")

def remove_file(file_name):
    file_path = os.path.join(RAG_UPLOADS, file_name)
    if os.path.exists(file_path):
        os.remove(file_path)
        if file_name in st.session_state.uploaded_files:
            st.session_state.uploaded_files.remove(file_name)

def kill_process_on_port(port):
    for proc in psutil.process_iter(["pid"]):
        try:
            conns = proc.net_connections()
            for conn in conns:
                if conn.laddr and conn.laddr.port == port:
                    proc.kill()
                    print(f"Killed process {proc.pid} on port {port}")
                    break
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

def cleanup_processes_on_exit():
    print("Cleaning up processes on Streamlit shutdown...")
    kill_process_on_port(7867)
    kill_process_on_port(5174)

atexit.register(cleanup_processes_on_exit)

def create_progress_ui():
    col1, col2 = st.columns([3, 1])
    with col1:
        progress_bar = st.progress(0)
        status_text = st.empty()
    with col2:
        stats = st.empty()
    details = st.expander("View detailed logs", expanded=False)
    return progress_bar, status_text, stats, details

def chunk_text_tokens(text: str, max_tokens: int = 1000):
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    chunks = [tokens[i: i + max_tokens] for i in range(0, len(tokens), max_tokens)]
    return [encoding.decode(chunk) for chunk in chunks]

def generate_embedding(file_content: str):
    try:
        memory_display = st.empty()
        chunks = chunk_text_tokens(file_content, max_tokens=500)
        embeddings = []
        display_memory_usage(memory_display, "Starting embedding generation")
        async def process_chunks():
            nonlocal embeddings
            for i, chunk in enumerate(chunks, 1):
                try:
                    display_memory_usage(memory_display, f"Processing chunk {i}/{len(chunks)}")
                    embedding = asyncio.run(get_embedding(chunk))
                    embeddings.append(embedding)
                except Exception as e:
                    logging.error(f"Error getting embedding for chunk: {str(e)}")
                    continue
        asyncio.run(process_chunks())
        display_memory_usage(memory_display, "Embedding generation complete")
        memory_display.empty()
        return embeddings if embeddings else None
    except Exception as e:
        logging.error(f"Error in generate_embedding: {str(e)}")
        return None

def upload_to_supabase(repo_name, repo_owner, branch, commit_hash, file_path, file_type, file_size, file_content, embeddings):
    try:
        for i, embedding in enumerate(embeddings):
            insert_to_supabase(
                "github",
                {
                    "repo_name": repo_name,
                    "repo_owner": repo_owner,
                    "branch": branch,
                    "commit_hash": commit_hash,
                    "file_path": f"{file_path}#chunk-{i+1}",
                    "file_type": file_type,
                    "file_size": file_size,
                    "file_content": file_content if len(embeddings) == 1 else f"Chunk {i+1} of {len(embeddings)}",
                    "embedding": embedding,
                },
            )
        print(f"Uploaded: {file_path} ({len(embeddings)} chunks)")
    except Exception as e:
        print(f"Failed to upload {file_path}: {e}")
