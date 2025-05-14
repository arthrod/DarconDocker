# frontend.py
import os
import asyncio
import threading
import subprocess
import shutil
from datetime import datetime
import tempfile

import streamlit as st
import streamlit.components.v1 as components
import requests
import psutil
import json

from dotenv import load_dotenv
load_dotenv()

# Import backend functions
from backend import (
    check_database_connection,
    clone_repo,
    process_pdf_file,
    process_youtube_playlist,
    preview_playlist_videos,
    extract_youtube_ids,
    initialize_youtube_api,
    conn  # For any direct DB queries if needed
)
from utils import parse_urls, chunk_text  # Assuming these are defined in your utils

# --------------------- Streamlit App Interface ---------------------
st.set_page_config(page_title="Unified RAG System", layout="wide")
st.title("Unified RAG System")

# Memory management helpers
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

# Telegram notification function
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
        "parse_mode": "HTML"
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

# Create tabs for different tools
tabs = st.tabs([
    "Crawl4AI", 
    "Github Cloner", 
    "Document Uploader", 
    "YouTube Summarizer", 
    "GPT Researcher"
])

# ---------- Crawl4AI Tab ----------
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
    
    # Assume parse_urls is defined in utils
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
                    nonlocal peak_memory
                    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode  # Import backend crawl module
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
                                                    "source_type": "webpage"
                                                }
                                                summary = ""
                                                # Assume insert_site_page from backend
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
                                                            json.dumps(metadata)
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

# ---------- GitHub Cloner Tab ----------
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

                    commit_hash = subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], 
                        cwd=repo_path
                    ).strip().decode()

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
                                                'main',
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
                    # Optionally, display video info in a table or dataframe
                    video_data = []
                    for idx, video in enumerate(videos, 1):
                        video_data.append({
                            "No.": idx,
                            "Title": video['title'],
                            "Channel": video['channelTitle'],
                            "Published": video['publishedAt'].split('T')[0]
                        })
                    st.dataframe(video_data, use_container_width=True)
                    confirm = st.checkbox("I confirm these videos should be processed", key="confirm_youtube_playlist")
                    if st.button("Process and Store These Videos", disabled=not confirm):
                        process_youtube_playlist(content_id)
                else:
                    st.error("Could not fetch playlist videos. Please check the URL and try again.")
            elif content_type == "video":
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
                            st.error("Single video processing not yet implemented.")
                        else:
                            st.error("Video not found. Please check the URL.")
                    except Exception as e:
                        st.error(f"Error fetching video info: {str(e)}")
                        
# ---------- GPT Researcher Tab ----------
with tabs[4]:
    st.header("🎓 GPT Researcher")
    components.iframe("http://localhost:8002/", height=700, width=1000, scrolling=False)
