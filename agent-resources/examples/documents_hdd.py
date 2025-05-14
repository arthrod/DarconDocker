import os
import json
import time
import asyncio
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
import threading
import psutil
import atexit
import streamlit as st
import streamlit.components.v1 as components
import requests
import shutil
import sys
import site
from crawl4ai import *
from utils import * 
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

# --------------------- Cleanup: Kill Child Processes & Port 8081 ---------------------
def kill_child_processes():
    """Kill all child processes of the current process."""
    current_pid = os.getpid()
    parent = psutil.Process(current_pid)
    children = parent.children(recursive=True)
    if children:
        st.info(f"Killing {len(children)} child process(es) before exit.")
    for child in children:
        try:
            child.kill()
        except Exception as e:
            print(f"Error killing child process {child.pid}: {e}")

def kill_port(port):
    """Kill any process listening on the specified port."""
    for conn in psutil.net_connections():
        if conn.laddr and conn.laddr.port == port:
            try:
                p = psutil.Process(conn.pid)
                p.kill()
                print(f"Killed process {conn.pid} on port {port}")
            except Exception as e:
                print(f"Error killing process on port {port}: {e}")

def cleanup():
    kill_child_processes()
    kill_port(8081)

atexit.register(cleanup)

# --------------------- Database Helpers ---------------------
import psycopg2
from psycopg2.extras import Json

# Use the POSTGRES_ variables from your .env file
conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST", "10.147.20.2"),
    port=os.getenv("POSTGRES_PORT", "5432"),
    database=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD")
)

def insert_github(data):
    """Insert a record into the github table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO github (
                repo_name, repo_owner, branch, commit_hash, file_path, file_type,
                file_size, file_content, tech_stack_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                data["repo_name"],
                data["repo_owner"],
                data.get("branch", "main"),
                data["commit_hash"],
                data["file_path"],
                data["file_type"],
                data["file_size"],
                data["file_content"],
                data.get("tech_stack_id")
            )
        )
        conn.commit()
        return cur.fetchone()[0]

def insert_site_page(data):
    """Insert a record into the crawled_pages table with improved title logic."""
    title = (
        data.get("crawl_label") or  # From user input (GUI)
        data.get("title") or       # From crawled page
        "Untitled Page"            # Fallback
    )
    
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO crawled_pages (
                url, chunk_number, title, summary, content, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                data["url"],
                data["chunk_number"],
                title,
                data.get("summary") or "",
                data["content"],
                Json(data["metadata"])
            )
        )
        conn.commit()
        return cur.fetchone()[0]


def insert_document(data):
    """Insert a record into the documents table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (
                content, metadata, tech_stack_id
            )
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (
                data["content"],
                Json(data["metadata"]),
                data.get("tech_stack_id")
            )
        )
        conn.commit()
        return cur.fetchone()[0]

def check_database_connection():
    """Check database connection status"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return True, "✅ Connected to Database"
    except Exception as e:
        return False, f"❌ Database Error: {str(e)}"

# --------------------- GitHub Cloner Helper ---------------------
def clone_repo(repo_url: str) -> Path:
    temp_dir = tempfile.mkdtemp()
    subprocess.run(["git", "clone", repo_url, temp_dir], check=True)
    return Path(temp_dir)

# --------------------- PDF Processing Helper ---------------------
import pdfplumber
def process_pdf_file(pdf_path: str):
    """Process a single PDF file: extract text, chunk it, and store into the documents table."""
    all_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    all_text += page_text + "\n"
    except Exception as e:
        st.error(f"Error reading PDF {pdf_path}: {e}")
        return

    chunks = chunk_text(all_text, chunk_size=1000)
    st.info(f"Extracted {len(chunks)} chunks from {pdf_path}")
    
    for i, chunk in enumerate(chunks):
        try:
            # Create metadata for the chunk
            metadata = {
                "source": "PDF",
                "source_type": "document",
                "file_path": pdf_path,
                "chunk_number": i,
                "total_chunks": len(chunks),
                "extracted_at": datetime.now().isoformat(),
                "file_name": os.path.basename(pdf_path)
            }
            
            # Store directly in Postgres documents table
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documents (content, metadata)
                    VALUES (%s, %s)
                    RETURNING id;
                    """,
                    (chunk, Json(metadata))
                )
                doc_id = cur.fetchone()[0]
                conn.commit()
                
            st.success(f"Stored chunk {i+1} from {pdf_path} (Document ID: {doc_id})")
            
        except Exception as e:
            st.error(f"Error processing chunk {i+1} from {pdf_path}: {e}")

# --------------------- YouTube Helpers (API Key Version) ---------------------
import re
import googleapiclient.discovery
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

def extract_youtube_ids(url: str) -> tuple[str, str]:
    """
    Extract video or playlist ID from various YouTube URL formats.
    Returns tuple of (type, id) where type is 'video' or 'playlist'
    """
    # Playlist patterns
    playlist_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=([^&\s]+)',
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[^&\s]+&list=([^&\s]+)',
    ]
    
    # Video patterns
    video_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^&\s]+)',
        r'(?:https?://)?(?:www\.)?youtu\.be/([^?\s]+)',
    ]
    
    # Check for playlist first
    for pattern in playlist_patterns:
        match = re.match(pattern, url)
        if match:
            return 'playlist', match.group(1)
    
    # Then check for single video
    for pattern in video_patterns:
        match = re.match(pattern, url)
        if match:
            return 'video', match.group(1)
            
    return None, None

def initialize_youtube_api():
    """Initialize YouTube API with error handling and GUI feedback."""
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            st.error("YouTube API key not found in environment variables!")
            return None
            
        youtube = googleapiclient.discovery.build(
            "youtube", 
            "v3", 
            developerKey=api_key,
            cache_discovery=False  # Disable file cache warning
        )
        return youtube
    except Exception as e:
        st.error(f"Failed to initialize YouTube API: {str(e)}")
        return None

def get_all_videos_from_playlist(playlist_id: str, progress_bar=None) -> list:
    """Retrieve all videos in a given YouTube playlist using pagination."""
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
                progress_bar.progress(len(all_items) / 100)  # Assuming max 100 videos
                
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

def get_video_transcript(video_id: str) -> str:
    """Fetches transcript of the video, if available."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry["text"] for entry in transcript_list])
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        st.warning(f"No transcript available for video ID {video_id}: {str(e)}")
        return ""
    except Exception as e:
        st.error(f"Error fetching transcript for video ID {video_id}: {str(e)}")
        return ""

def process_youtube_playlist(playlist_id: str):
    """Process all videos in a YouTube playlist with detailed progress tracking."""
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
        
        for idx, video in enumerate(videos, 1):
            try:
                video_status.info(f"Processing video {idx}/{len(videos)}: {video['title']}")
                video_id = video["video_id"]
                
                # Get transcript with detailed error handling
                transcript = get_video_transcript(video_id)
                if not transcript:
                    error_log.append(f"No transcript available for: {video['title']} ({video_id})")
                    continue
                
                # Instead of summarizing, store the full transcript
                content = (
                    f"Title: {video['title']}\n"
                    f"Channel: {video['channelTitle']}\n"
                    f"Published: {video['publishedAt']}\n\n"
                    f"Transcript:\n{transcript}"
                )
                # Create metadata
                metadata = {
                    "source": "YouTube",
                    "source_type": "video",
                    "video_id": video_id,
                    "title": video["title"],
                    "channel": video["channelTitle"],
                    "published_at": video["publishedAt"],
                    "processed_at": datetime.now().isoformat(),
                    "playlist_id": playlist_id
                }
                
                # Store directly in Postgres documents table
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
                    
            except Exception as e:
                error_msg = f"Error with video {video.get('title', 'Unknown')}: {str(e)}"
                error_log.append(error_msg)
                video_status.error(error_msg)
                
            progress_bar.progress((idx) / len(videos))
            
        progress_bar.progress(100)
        status_container.success("Playlist processing completed!")
        
        # Display error summary if any errors occurred
        if error_log:
            with st.expander("Processing Errors", expanded=True):
                st.error("The following errors occurred during processing:")
                for error in error_log:
                    st.write(f"- {error}")
                    
    except Exception as e:
        st.error(f"Fatal error processing playlist: {str(e)}")

def preview_playlist_videos(playlist_id: str) -> list:
    """Get playlist videos for preview without processing."""
    youtube = initialize_youtube_api()
    if not youtube:
        return []
    
    try:
        videos = get_all_videos_from_playlist(playlist_id)
        return videos
    except Exception as e:
        st.error(f"Error fetching playlist preview: {str(e)}")
        return []

# --------------------- Streamlit App Interface ---------------------
st.set_page_config(page_title="Unified RAG System", layout="wide")
st.title("Unified RAG System")

def send_telegram_message(message: str):
    """Send a message to Telegram"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        st.error("Telegram credentials not configured")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"  # Allows basic HTML formatting
    }
    
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Failed to send Telegram message: {e}")
        return False

# Test Telegram notification on startup
send_telegram_message("🚀 RAG System is now online!")

tabs = st.tabs([
    "Crawl4AI", 
    "Github Cloner", 
    "Document Uploader", 
    "YouTube Summarizer", 
    "GPT Researcher"
])

# Add memory management helpers at the top
def get_memory_usage():
    """Get current memory usage of the process"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss

def check_memory_threshold(threshold_mb=1000):
    """Check if memory usage is above threshold"""
    current_mem = get_memory_usage() // (1024 * 1024)  # Convert to MB
    return current_mem > threshold_mb, current_mem

async def wait_for_memory_available(threshold_mb=1000, check_interval=1):
    """Wait until memory usage is below threshold"""
    while True:
        is_high, current_mem = check_memory_threshold(threshold_mb)
        if not is_high:
            break
        st.warning(f"Memory usage high ({current_mem}MB). Waiting for resources...")
        await asyncio.sleep(check_interval)

# ---------- Tool Tabs ----------
def extract_domain(url):
    parsed_url = urlparse(url)
    return parsed_url.netloc

with tabs[0]:
    st.header("🕷️ Crawl4AI Tool")
    db_ok, db_message = check_database_connection()
    st.info(f"Status: {db_message} | Target: crawled_pages table")
    st.markdown("""
    This tool will:
    1. Crawl provided URLs
    2. Split content into chunks
    3. Store in crawled_pages table
    """)
    
    url_input = st.text_area(
        "Enter URLs (one per line) or a sitemap URL:",
        help="Enter one URL per line; can be website pages or sitemap XML URLs.",
        key="crawl_urls"
    )
    crawl_label = st.text_input(
        "Crawl Label (optional):", 
        placeholder="e.g., documentation-v1", 
        key="crawl_label"
    )
    max_concurrent = st.radio(
        "Max Concurrent Crawls:",
        options=[1, 2, 3, 5, 10],
        index=2,
        horizontal=True,
        key="max_concurrent_crawls"
    )
    
    # Use parse_urls from utils.py to handle both individual and sitemap URLs
    urls = parse_urls(url_input)
    
    if urls:
        st.info(f"Found {len(urls)} URLs to process")
        confirm = st.checkbox("I confirm these URLs should be processed", key="confirm_crawl")
        if st.button("Start Crawling", disabled=not confirm):
            st.info(f"Starting crawl for {len(urls)} URLs...")
            
            def crawl_task():
                peak_memory = 0
                process_ps = psutil.Process(os.getpid())
                
                def log_memory(prefix=""):
                    nonlocal peak_memory
                    current_mem = process_ps.memory_info().rss
                    if current_mem > peak_memory:
                        peak_memory = current_mem
                    st.info(f"Crawl {prefix}: Current Memory: {current_mem // (1024*1024)} MB, Peak: {peak_memory // (1024*1024)} MB")
                
                log_memory("Start")
                
                async def run_crawler():
                    nonlocal peak_memory  # Ensure assignments update the outer variable
                    browser_config = BrowserConfig(
                        headless=True,
                        verbose=False,
                        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
                    )
                    crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
                    crawler = AsyncWebCrawler(config=browser_config)
                    await crawler.start()
                    
                    MEMORY_THRESHOLD_MB = 1000  # 1GB threshold
                    batch_size = min(max_concurrent, 3)  # Limit concurrent processing
                    
                    for i in range(0, len(urls), batch_size):
                        batch = urls[i:i + batch_size]
                        tasks = []
                        for url in batch:
                            # Wait until memory is below the threshold before processing each URL
                            await wait_for_memory_available(MEMORY_THRESHOLD_MB)
                            tasks.append(crawler.arun(url=url, config=crawl_config))
                        
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        current_mem = process_ps.memory_info().rss
                        if current_mem > peak_memory:
                            peak_memory = current_mem
                        st.info(f"Batch {i//batch_size + 1} Memory: {current_mem // (1024*1024)} MB")
                        
                        for result in results:
                            if isinstance(result, Exception):
                                st.error(f"Error processing URL: {result}")
                            else:
                                url = result.url
                                log_memory(f"Before processing {url}")
                                st.info(f"Processing: {url}")
                                try:
                                    if result.success:
                                        raw_text = result.markdown_v2.raw_markdown
                                        chunks = chunk_text(raw_text, chunk_size=1000)
                                        st.info(f"Found {len(chunks)} chunks for {url}")
                                        
                                        for j, chunk in enumerate(chunks):
                                            try:
                                                metadata = {
                                                    "title": crawl_label or "No Title",
                                                    "crawl_label": crawl_label,
                                                    "extracted_at": datetime.now().isoformat(),
                                                    "source": "crawl4ai",
                                                    "source_type": "webpage",
                                                    "domain": extract_domain(url)  # <-- New field added
                                                }
                                                summary = ""
                                                with conn.cursor() as cur:
                                                    cur.execute(
                                                        """
                                                        INSERT INTO crawled_pages (
                                                            url, chunk_number, title, summary, 
                                                            content, metadata
                                                        )
                                                        VALUES (%s, %s, %s, %s, %s, %s)
                                                        RETURNING id;
                                                        """,
                                                        (
                                                            url,
                                                            j,
                                                            metadata["title"],
                                                            summary,
                                                            chunk,
                                                            Json(metadata)
                                                        )
                                                    )
                                                    chunk_id = cur.fetchone()[0]
                                                    conn.commit()
                                                st.success(f"Stored chunk {j+1} for {url} (ID: {chunk_id})")
                                            except Exception as e:
                                                st.error(f"Error processing chunk {j+1} from {url}: {e}")
                                    else:
                                        st.error(f"Failed to crawl {url}")
                                except Exception as e:
                                    st.error(f"Error processing {url}: {e}")
                                log_memory(f"After processing {url}")
                    
                    await crawler.close()
                    log_memory("Final")
                    st.success("Crawling completed!")
                
                asyncio.run(run_crawler())
            
            threading.Thread(target=crawl_task, daemon=True).start()
            st.info("Crawling started in background - you can switch to other tabs!")




# Updated GitHub Cloner Tab (Fully Aligned with Database)

# ---------- Github Cloner Tab ----------
with tabs[1]:
    st.header("🌍 Github Cloner")
    db_ok, db_message = check_database_connection()
    st.info(f"Status: {db_message} | Target: github table")
    st.markdown("""
    This tool will:
    1. Clone the repository
    2. Process all text files
    3. Store in github table
    """)
    
    repo_url = st.text_input("Enter GitHub Repository URL:", placeholder="https://github.com/nodejs/node")
    if repo_url:
        st.info(f"Repository to process: {repo_url}")
        confirm = st.checkbox("I confirm this repository should be processed")
        if st.button("Clone and Process Repository", disabled=not confirm):
            if repo_url:
                def github_task():
                    peak_memory = 0
                    process_ps = psutil.Process(os.getpid())
                    def log_memory(prefix=""):
                        nonlocal peak_memory
                        current_mem = process_ps.memory_info().rss
                        if current_mem > peak_memory:
                            peak_memory = current_mem
                        st.info(f"GitHub {prefix}: Current Memory: {current_mem // (1024*1024)} MB, Peak: {peak_memory // (1024*1024)} MB")
                    log_memory("Start")
                    try:
                        st.info("Cloning repository...")
                        repo_path = clone_repo(repo_url)
                        st.write(f"Repository cloned to {repo_path}")

                        # Get commit hash once for the entire repo
                        commit_hash = subprocess.check_output(
                            ["git", "rev-parse", "HEAD"], 
                            cwd=repo_path
                        ).strip().decode()

                        # Extract repo details from URL
                        repo_owner = repo_url.split("/")[-2]
                        repo_name = repo_url.split("/")[-1]

                        async def process_files():
                            for file in repo_path.rglob("*"):
                                await wait_for_memory_available()
                                if file.is_file():
                                    if file.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg"}:
                                        continue
                                    if file.stat().st_size > 5_000_000:
                                        continue
                                    try:
                                        with open(file, "r", encoding="utf-8", errors="ignore") as f:
                                            file_content = f.read()
                                        # Store directly in Postgres github table, matching exact schema
                                        with conn.cursor() as cur:
                                            cur.execute(
                                                """
                                                INSERT INTO github (
                                                    repo_name, repo_owner, branch, commit_hash,
                                                    file_path, file_type, file_size, file_content
                                                )
                                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                                RETURNING id;
                                                """,
                                                (
                                                    repo_name,
                                                    repo_owner,
                                                    'main',  # Using default branch
                                                    commit_hash,
                                                    str(file.relative_to(repo_path)),
                                                    file.suffix.lstrip(".").lower() or "txt",
                                                    file.stat().st_size,
                                                    file_content
                                                )
                                            )
                                            file_id = cur.fetchone()[0]
                                            conn.commit()
                                            
                                        st.success(f"Processed {file.name} (ID: {file_id})")
                                    except Exception as e:
                                        st.error(f"Error processing file {file}: {e}")
                        
                        asyncio.run(process_files())
                        
                        # Cleanup temp directory after processing
                        shutil.rmtree(repo_path)
                        st.success("Repository processed and temporary files cleaned up!")
                    except Exception as e:
                        st.error(f"Error cloning repository: {e}")
                    log_memory("End")
                threading.Thread(target=github_task, daemon=True).start()
                st.info("Cloning started in background - you can switch to other tabs!")

# ---------- Document Uploader Tab ----------
with tabs[2]:
    st.header("📄 Document Uploader")
    db_ok, db_message = check_database_connection()
    st.info(f"Status: {db_message} | Target: documents table")
    st.markdown("""
    This tool will:
    1. Extract text from PDFs
    2. Store in documents table
    """)
    
    uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True, key="pdf_uploader")
    if uploaded_files:
        st.info(f"Found {len(uploaded_files)} files to process")
        for file in uploaded_files:
            st.write(f"- {file.name}")
        confirm = st.checkbox("I confirm these files should be processed", key="confirm_pdf_upload")
        if st.button("Process PDFs", disabled=not confirm):
            if uploaded_files:
                def pdf_task():
                    peak_memory = 0
                    process_ps = psutil.Process(os.getpid())
                    def log_memory(prefix=""):
                        nonlocal peak_memory
                        current_mem = process_ps.memory_info().rss
                        if current_mem > peak_memory:
                            peak_memory = current_mem
                        st.info(f"PDF {prefix}: Current Memory: {current_mem // (1024*1024)} MB, Peak: {peak_memory // (1024*1024)} MB")
                    log_memory("Start")
                    for uploaded_file in uploaded_files:
                        temp_dir = "temp_pdfs"
                        os.makedirs(temp_dir, exist_ok=True)
                        file_path = os.path.join(temp_dir, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        st.info(f"Processing {uploaded_file.name}...")
                        process_pdf_file(file_path)
                    st.success("Finished processing all uploaded PDFs!")
                    log_memory("End")
                threading.Thread(target=pdf_task, daemon=True).start()

# ---------- YouTube Summarizer Tab ----------
with tabs[3]:
    st.header("📺 YouTube Summarizer")
    db_ok, db_message = check_database_connection()
    st.info(f"Status: {db_message} | Target: documents table")
    st.markdown("""
    This tool will:
    1. Fetch video information
    2. Get transcripts
    3. Store in documents table
    """)
    
    yt_input = st.text_input(
        "Enter YouTube URL:",
        placeholder="https://www.youtube.com/playlist?list=... or https://www.youtube.com/watch?v=...",
        key="youtube_url"
    )
    
    if yt_input:
        content_type, content_id = extract_youtube_ids(yt_input)
        
        if not content_type or not content_id:
            st.error("Invalid YouTube URL. Please enter a valid playlist or video URL.")
        else:
            st.info(f"Detected {content_type.title()} ID: {content_id}")
            
            if content_type == "playlist":
                videos = preview_playlist_videos(content_id)
                if videos:
                    st.success(f"Found {len(videos)} videos in playlist:")
                    
                    # Create a DataFrame for better display
                    video_data = []
                    for idx, video in enumerate(videos, 1):
                        video_data.append({
                            "№": idx,
                            "Title": video['title'],
                            "Channel": video['channelTitle'],
                            "Published": video['publishedAt'].split('T')[0]
                        })
                    
                    st.dataframe(video_data, use_container_width=True)
                    
                    # Add confirmation button
                    confirm = st.checkbox("I confirm these videos should be processed", key="confirm_youtube_playlist")
                    if st.button("Process and Store These Videos", disabled=not confirm):
                        process_youtube_playlist(content_id)
                else:
                    st.error("Could not fetch playlist videos. Please check the URL and try again.")
            
            elif content_type == "video":
                # Display single video info
                youtube = initialize_youtube_api()
                if youtube:
                    try:
                        video_info = youtube.videos().list(
                            part="snippet",
                            id=content_id
                        ).execute()
                        
                        if video_info['items']:
                            video = video_info['items'][0]['snippet']
                            st.success("Found video:")
                            st.write({
                                "Title": video['title'],
                                "Channel": video['channelTitle'],
                                "Published": video['publishedAt'].split('T')[0],
                                "Description": video['description'][:200] + "..."
                            })
                            
                            # Add confirmation button
                            st.error("Single video processing not yet implemented.")
                        else:
                            st.error("Video not found. Please check the URL.")
                    except Exception as e:
                        st.error(f"Error fetching video info: {str(e)}")

# ---------- GPT Researcher Tab ----------
with tabs[4]:
    st.header("🎓 GPT Researcher")
    components.iframe("http://localhost:8002/", height=700, width=1000, scrolling=False)
