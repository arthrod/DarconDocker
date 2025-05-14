import re
import os
import asyncio
import googleapiclient.discovery
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import logging
from datetime import datetime
from googleapiclient.errors import HttpError
from google.oauth2 import credentials
import asyncpg
from pathlib import Path
from asyncpg import InterfaceError, ConnectionDoesNotExistError, InvalidAuthorizationSpecificationError
from asyncpg.pool import Pool
from asyncpg.exceptions import PostgresConnectionError
from dotenv import load_dotenv
import tiktoken
import httpx
import random
import json

# Load environment variables from .env
load_dotenv()

# Constants
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
EMBEDDING_DIM = 768
EMBEDDING_MODEL = "nomic-embed-text"
TOKEN_LIMIT = 8000
CHUNK_MAX_TOKENS = TOKEN_LIMIT // 2

CONTENT_TEMPLATE = """
Title: {title}
Channel: {channel}
Published: {published_at}

Transcript:
{transcript}
"""

# Module-level constants
TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
EMBEDDING_SEMAPHORE = asyncio.Semaphore(5)

DB_PARAMS = {
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT"),
    "database": None  # Database name will be set dynamically
}

async def create_db_pool(db_name: str, max_retries: int = 3, base_delay: float = 1.0):
    conn_params = DB_PARAMS.copy()
    conn_params["database"] = db_name
    
    for attempt in range(1, max_retries + 1):
        try:
            pool = await asyncpg.create_pool(**conn_params, min_size=1, max_size=20)
            return pool
        except Exception as e:
            if attempt == max_retries:
                logging.error(f"Failed to create connection pool after {max_retries} attempts: {e}")
                return None
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logging.warning(f"Connection attempt {attempt} failed, retrying in {delay:.2f}s")
            await asyncio.sleep(delay)

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
    """Initialize YouTube API with error handling."""
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            logging.error("YouTube API key not found in environment variables!")
            return None
            
        youtube = googleapiclient.discovery.build(
            "youtube", 
            "v3", 
            developerKey=api_key,
            cache_discovery=False  # Disable file cache warning
        )
        return youtube
    except Exception as e:
        logging.error(f"Failed to initialize YouTube API: {str(e)}")
        return None

async def get_all_videos_from_playlist(playlist_id: str, progress_callback=None) -> list:
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
                logging.error(f"YouTube API Error: {response['error']['message']}")
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
        logging.error(f"Error fetching playlist videos: {str(e)}")
        return []

async def get_embedding(text: str, max_retries: int = 3, base_delay: float = 1.0) -> list[float]:
    """Asynchronously get an embedding for a text chunk using the Ollama API."""
    ollama_url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/embeddings"
    model_name = EMBEDDING_MODEL

    async with EMBEDDING_SEMAPHORE:
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        ollama_url,
                        json={"model": model_name, "prompt": text},
                        timeout=60
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result["embedding"]
            except httpx.HTTPStatusError as e:
                logging.error(f"HTTP error getting embedding (attempt {attempt}): {e}")
                if attempt == max_retries:
                    return [0] * EMBEDDING_DIM
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
            except httpx.TimeoutException as e:
                logging.error(f"Timeout error getting embedding (attempt {attempt}): {e}")
                if attempt == max_retries:
                    return [0] * EMBEDDING_DIM
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
            except Exception as e:
                logging.error(f"Error getting embedding (attempt {attempt}): {e}")
                if attempt == max_retries:
                    return [0] * EMBEDDING_DIM
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

def chunk_text_tokens(text: str, max_tokens: int = 1000) -> list[str]:
    """Chunk text using token counts. Uses the 'cl100k_base' encoding."""
    tokens = TIKTOKEN_ENCODING.encode(text)
    chunks = [tokens[i: i + max_tokens] for i in range(0, len(tokens), max_tokens)]
    return [TIKTOKEN_ENCODING.decode(chunk) for chunk in chunks]

async def generate_embedding(file_content: str) -> list:
    """Generate embeddings for the given file content."""
    chunks = chunk_text_tokens(file_content, max_tokens=1000)
    embeddings = []
    for chunk in chunks:
        embedding = await get_embedding(chunk)
        embeddings.append(embedding)
    return embeddings

async def get_video_transcript(video_id: str) -> str:
    """Fetches transcript of the video, if available."""
    try:
        transcript_list = await asyncio.to_thread(YouTubeTranscriptApi.get_transcript, video_id)
        return " ".join([entry["text"] for entry in transcript_list])
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        logging.warning(f"No transcript available for video ID {video_id}: {str(e)}")
        return ""
    except Exception as e:
        logging.error(f"Error fetching transcript for video ID {video_id}: {str(e)}")
        return ""

async def upload_to_documents_table(content: str, metadata: dict, pool: Pool):
    """Uploads content and metadata to the documents table."""
    try:
        embeddings = await generate_embedding(content)

        # Check if embeddings is empty
        if not embeddings:
            logging.error("No embeddings generated for content.")
            return

        # Average the embeddings
        avg_embedding = [sum(x) / len(x) for x in zip(*embeddings)]

        # Format the averaged embedding as a PostgreSQL array string
        embedding_str = str(tuple(avg_embedding)).replace('(', '[').replace(')', ']')

        async with pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO documents (content, metadata, embedding)
                    VALUES ($1, $2, $3)
                    """,
                    content, json.dumps(metadata), embedding_str
                )
                logging.info(f"Successfully stored document in database.")

            except Exception as e:
                logging.error(f"Error inserting data into documents table: {e}")

    except Exception as e:
        logging.error(f"Error generating or uploading embeddings: {e}")

async def process_youtube_video(video_id: str, db_name: str, pool: Pool):
    """Process a single YouTube video and store its contents in PostgreSQL."""
    try:
        # Get transcript with detailed error handling
        transcript = await get_video_transcript(video_id)
        if not transcript:
            logging.warning(f"No transcript available for video ID {video_id}")
            return

        # Get video details
        youtube = initialize_youtube_api()
        if not youtube:
            logging.error("Failed to initialize YouTube API.")
            return

        request = youtube.videos().list(
            part="snippet",
            id=video_id
        )
        response = request.execute()

        if 'error' in response:
            logging.error(f"YouTube API Error: {response['error']['message']}")
            return

        items = response.get("items", [])
        if not items:
            logging.error(f"No video found with ID: {video_id}")
            return

        video = items[0]
        snippet = video["snippet"]

        content = CONTENT_TEMPLATE.format(
            title=snippet['title'],
            channel=snippet['channelTitle'],
            published_at=snippet['publishedAt'],
            transcript=transcript
        )

        # Create metadata
        metadata = {
            "source": "YouTube",
            "source_type": "video",
            "video_id": video_id,
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "published_at": snippet["publishedAt"],
            "processed_at": datetime.now().isoformat()
        }

        await upload_to_documents_table(content, metadata, pool)

    except Exception as e:
        logging.error(f"Error processing video {video_id}: {e}")

async def process_youtube_playlist(playlist_id: str, db_name: str, pool: Pool):
    """Process all videos in a YouTube playlist with detailed progress tracking."""
    try:
        error_log = []
        videos = await get_all_videos_from_playlist(playlist_id)
        
        if not videos:
            logging.error("No videos found in the playlist.")
            return
            
        logging.info(f"Found {len(videos)} videos in the playlist.")
        
        for idx, video in enumerate(videos, 1):
            try:
                logging.info(f"Processing video {idx}/{len(videos)}: {video['title']}")
                video_id = video["video_id"]
                
                # Get transcript with detailed error handling
                transcript = await get_video_transcript(video_id)
                if not transcript:
                    error_log.append(f"No transcript available for: {video['title']} ({video_id})")
                    continue

                content = CONTENT_TEMPLATE.format(
                    title=video['title'],
                    channel=video['channelTitle'],
                    published_at=video['publishedAt'],
                    transcript=transcript
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
                
                await upload_to_documents_table(content, metadata, pool)
                    
            except Exception as e:
                error_msg = f"Error with video {video.get('title', 'Unknown')}: {str(e)}"
                error_log.append(error_msg)
                logging.error(error_msg)
                
        logging.info("Playlist processing completed!")
        
        # Display error summary if any errors occurred
        if error_log:
            logging.error("The following errors occurred during processing:")
            for error in error_log:
                logging.error(f"- {error}")
                    
    except Exception as e:
        logging.error(f"Fatal error processing playlist: {str(e)}")

async def process_youtube_url(url: str, db_name: str, pool: Pool):
    """Process a single YouTube URL (video or playlist)."""
    try:
        url_type, url_id = extract_youtube_ids(url)
        if url_type == 'playlist':
            await process_youtube_playlist(url_id, db_name, pool)
        elif url_type == 'video':
            await process_youtube_video(url_id, db_name, pool)
        else:
            logging.error(f"Invalid YouTube URL: {url}")
    except Exception as e:
        logging.error(f"Error processing YouTube URL {url}: {e}")

async def process_youtube_urls_from_txt():
    """Process YouTube URLs listed in txt files."""
    base_path = Path('/home/ai-agents/post_data')
    youtube_txt_files = [
        "youtube_n8n.txt",
        "youtube_make.txt",
        "youtube_lang_agent.txt",
        "youtube_huggingface_smol.txt",
        "youtube_pydantic_ai.txt",
        "youtube_flowise.txt"
    ]

    async def process_youtube_file(youtube_file):
         tool_db_name = youtube_file.replace("youtube_", "").replace(".txt", "")
         pool = await create_db_pool(tool_db_name)
         if not pool:
             logging.error(f"Failed to create pool for {tool_db_name}, skipping")
             return

         file_path = base_path / youtube_file
         if file_path.exists():
             with open(file_path, "r") as f:
                 urls = f.readlines()

             tasks = [process_youtube_url(url.strip(), tool_db_name, pool)
                      for url in urls if url.strip()]
             await asyncio.gather(*tasks)
         else:
             logging.error(f"File not found: {file_path}")

         await pool.close()

    await asyncio.gather(*(process_youtube_file(youtube_file) for youtube_file in youtube_txt_files))

def preview_playlist_videos(playlist_id: str) -> list:
    """Get playlist videos for preview without processing."""
    youtube = initialize_youtube_api()
    if not youtube:
        return []
    
    try:
        videos = get_all_videos_from_playlist(playlist_id)
        return videos
    except Exception as e:
        logging.error(f"Error fetching playlist preview: {str(e)}")
        return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    print("🚀 Starting YouTube processing...")
    asyncio.run(process_youtube_urls_from_txt())
    print("✅ All YouTube content processed and stored in PostgreSQL.")