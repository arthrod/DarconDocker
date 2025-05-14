import sys
import concurrent.futures
import os
import requests
import googleapiclient.discovery
import re
import time
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from supabase import create_client, Client
from requests.exceptions import RequestException, Timeout, ConnectionError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === CONFIG ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SUPABASE_TABLE_NAME = "youtube"
OLLAMA_URL = "http://10.147.20.20:11434"
EMBED_MODEL = "nomic-embed-text"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY") or ""
REQUEST_TIMEOUT = 30  # Seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # Seconds
SKIP_EMBEDDINGS = False  # Set to True to skip embeddings if server is down

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)

def chunk_text(text: str, max_chars: int = 3000):
    return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]

def generate_embedding(text: str):
    if SKIP_EMBEDDINGS:
        print("[Info] Skipping embedding generation as configured")
        return []
        
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except (ConnectionError, Timeout) as e:
            print(f"[Embedding Error] Connection issue (attempt {attempt+1}/{MAX_RETRIES}): {str(e)}")
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print("[Warning] Max retries reached. Proceeding without embeddings.")
                return []
        except Exception as e:
            print(f"[Embedding Error] Unexpected error: {str(e)}")
            return []

def upload_chunk(data):
    # Check if embeddings are empty and note it in metadata
    if "embedding" in data and not data["embedding"]:
        if "metadata" not in data:
            data["metadata"] = {}
        data["metadata"]["embedding_status"] = "failed"
        
    response = supabase.table(SUPABASE_TABLE_NAME).insert(data).execute()
    if hasattr(response, 'error') and response.error:
        print(f"[Upload Error] {response.error}")
    else:
        print(f"✅ Uploaded: {data['title']} [chunk {data['chunk_number']}] from {data['video_id']}")

def extract_youtube_ids(url: str):
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
    return googleapiclient.discovery.build(
        "youtube", "v3", developerKey=YOUTUBE_API_KEY, cache_discovery=False
    )

def get_video_metadata(video_id):
    youtube = initialize_youtube_api()
    request = youtube.videos().list(part="snippet", id=video_id)
    response = request.execute()
    item = response["items"][0]["snippet"]
    return item

def get_playlist_videos(playlist_id):
    youtube = initialize_youtube_api()
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
        items = response.get("items", [])
        all_items.extend(items)
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
    return [item["snippet"]["resourceId"]["videoId"] for item in all_items]

def fetch_transcript(video_id):
    """
    Fetch transcript for a YouTube video using only the local proxy service.
    """
    try:
        # Use local machine as proxy - skip direct fetch entirely
        print(f"[Info] Fetching transcript via proxy service at 10.147.20.20...")
        import requests
        response = requests.get(f"http://10.147.20.20:5050/api/transcript?video_id={video_id}")
        data = response.json()
        
        if data.get("success", False):
            print(f"[Success] Transcript fetched for {video_id}")
            return data.get("transcript", "")
        else:
            print(f"[Error] Proxy service error: {data.get('error', 'Unknown error')}")
            return ""
    except Exception as proxy_error:
        print(f"[Error] Failed to use proxy service: {str(proxy_error)}")
        return ""

def process_single_video(video_id):
    print(f"\n🎬 Processing video: {video_id}")
    metadata = get_video_metadata(video_id)
    transcript = fetch_transcript(video_id)
    if not transcript:
        return

    chunks = chunk_text(transcript)

    for idx, chunk in enumerate(chunks):
        try:
            embedding = generate_embedding(chunk)
            data = {
                "source": "YouTube",
                "url": f"https://youtube.com/watch?v={video_id}",
                "video_id": video_id,
                "channel_name": metadata["channelTitle"],
                "chunk_number": idx,
                "file_size": len(chunk),
                "title": metadata["title"],
                "summary": chunk[:250],
                "file_content": chunk,
                "metadata": {
                    "published_at": metadata["publishedAt"],
                    "channel": metadata["channelTitle"]
                },
                "embedding": embedding
            }
            upload_chunk(data)
        except Exception as e:
            print(f"[Chunk Error] {e}")

def process_youtube_url(url: str):
    """
    Process a YouTube video or playlist URL (UI callable). Prints/logs progress and errors.
    """
    url_type, url_id = extract_youtube_ids(url)
    if url_type == 'video':
        process_single_video(url_id)
    elif url_type == 'playlist':
        video_ids = get_playlist_videos(url_id)
        print(f"\n📜 Playlist has {len(video_ids)} videos.")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(process_single_video, video_ids)
    else:
        print("\n❌ Invalid YouTube URL.")

if __name__ == "__main__":
    # Add command line option for skipping embeddings
    if "--skip-embeddings" in sys.argv:
        SKIP_EMBEDDINGS = True
        sys.argv.remove("--skip-embeddings")
    
    if len(sys.argv) != 2:
        print("\nUsage: python3 youtube_tool.py [--skip-embeddings] <youtube_video_or_playlist_url>\n")
        sys.exit(1)

    url = sys.argv[1]
    process_youtube_url(url)
