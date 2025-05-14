# backend.py
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
import requests
import shutil
import sys
import site
from crawl4ai import *      # Assuming these modules are available in your PYTHONPATH
from utils import *         # Ensure your utils module defines functions like chunk_text

from dotenv import load_dotenv
load_dotenv()

# --------------------- Cleanup Functions ---------------------
def kill_child_processes():
    """Kill all child processes of the current process."""
    current_pid = os.getpid()
    parent = psutil.Process(current_pid)
    children = parent.children(recursive=True)
    if children:
        print(f"Killing {len(children)} child process(es) before exit.")
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
        data.get("title") or        # From crawled page
        "Untitled Page"             # Fallback
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
        print(f"Error reading PDF {pdf_path}: {e}")
        return

    # Assume chunk_text is defined in utils
    chunks = chunk_text(all_text, chunk_size=1000)
    print(f"Extracted {len(chunks)} chunks from {pdf_path}")
    
    for i, chunk in enumerate(chunks):
        try:
            metadata = {
                "source": "PDF",
                "source_type": "document",
                "file_path": pdf_path,
                "chunk_number": i,
                "total_chunks": len(chunks),
                "extracted_at": datetime.now().isoformat(),
                "file_name": os.path.basename(pdf_path)
            }
            
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
                
            print(f"Stored chunk {i+1} from {pdf_path} (Document ID: {doc_id})")
            
        except Exception as e:
            print(f"Error processing chunk {i+1} from {pdf_path}: {e}")

# --------------------- YouTube Helpers ---------------------
import re
import googleapiclient.discovery
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

def extract_youtube_ids(url: str) -> tuple[str, str]:
    """Extract video or playlist ID from various YouTube URL formats."""
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

def initialize_youtube_api():
    """Initialize YouTube API with error handling."""
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            print("YouTube API key not found in environment variables!")
            return None
        youtube = googleapiclient.discovery.build(
            "youtube", 
            "v3", 
            developerKey=api_key,
            cache_discovery=False
        )
        return youtube
    except Exception as e:
        print(f"Failed to initialize YouTube API: {str(e)}")
        return None

def get_all_videos_from_playlist(playlist_id: str, progress_callback=None) -> list:
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
                print(f"YouTube API Error: {response['error']['message']}")
                return []
            items = response.get("items", [])
            all_items.extend(items)
            if progress_callback:
                progress_callback(len(all_items))
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
        print(f"Error fetching playlist videos: {str(e)}")
        return []

def get_video_transcript(video_id: str) -> str:
    """Fetch transcript of the video, if available."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry["text"] for entry in transcript_list])
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"No transcript available for video ID {video_id}: {str(e)}")
        return ""
    except Exception as e:
        print(f"Error fetching transcript for video ID {video_id}: {str(e)}")
        return ""

def process_youtube_playlist(playlist_id: str):
    """Process all videos in a YouTube playlist with progress tracking."""
    try:
        print("Starting playlist processing...")
        videos = get_all_videos_from_playlist(playlist_id)
        if not videos:
            print("No videos found in the playlist.")
            return
        print(f"Found {len(videos)} videos in the playlist.")
        for idx, video in enumerate(videos, 1):
            try:
                print(f"Processing video {idx}/{len(videos)}: {video['title']}")
                video_id = video["video_id"]
                transcript = get_video_transcript(video_id)
                if not transcript:
                    print(f"No transcript available for: {video['title']} ({video_id})")
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
                    "processed_at": datetime.now().isoformat(),
                    "playlist_id": playlist_id
                }
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
                print(f"Successfully processed and stored: {video['title']} (Document ID: {doc_id})")
            except Exception as e:
                print(f"Error processing video {video.get('title', 'Unknown')}: {str(e)}")
        print("Playlist processing completed!")
    except Exception as e:
        print(f"Fatal error processing playlist: {str(e)}")

def preview_playlist_videos(playlist_id: str) -> list:
    """Get playlist videos for preview without processing."""
    youtube = initialize_youtube_api()
    if not youtube:
        return []
    try:
        videos = get_all_videos_from_playlist(playlist_id)
        return videos
    except Exception as e:
        print(f"Error fetching playlist preview: {str(e)}")
        return []
