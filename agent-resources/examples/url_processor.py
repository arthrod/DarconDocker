import os
import sys
from pathlib import Path
from typing import Literal
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import psutil
import subprocess
import shutil

load_dotenv()

# Import the core functions we need from backend and utils
from backend import (
    process_youtube_playlist,
    clone_repo,
    insert_github,
    insert_site_page,
    conn,
    extract_youtube_ids,
    initialize_youtube_api,
    get_video_transcript,
    insert_document
)
from utils import chunk_text

# Dummy reference to conn to satisfy Pylance (conn is used indirectly in the helper functions)
_ = conn

SOURCE_LISTS_DIR = Path("source_lists")
URLType = Literal["YOUTUBE", "GITHUB", "URL"]

async def wait_for_memory_available(threshold_mb=1000, check_interval=1):
    """Wait until memory usage is below the threshold."""
    while True:
        process = psutil.Process(os.getpid())
        current_mem = process.memory_info().rss // (1024 * 1024)
        if current_mem <= threshold_mb:
            break
        print(f"Memory usage high ({current_mem}MB). Waiting for resources...")
        await asyncio.sleep(check_interval)

class URLProcessor:
    def __init__(self):
        self.files = {
            "YOUTUBE": SOURCE_LISTS_DIR / "youtube.txt",
            "GITHUB": SOURCE_LISTS_DIR / "github.txt",
            "URL": SOURCE_LISTS_DIR / "site_urls.txt"
        }
        
    async def process_new_url(self, url: str, url_type: URLType):
        """Process a new URL and add it to the appropriate list file"""
        if not url.strip():
            return False
            
        file_path = self.files[url_type]
        
        # Check if URL already exists
        if file_path.exists():
            with open(file_path, "r") as f:
                if url in f.read():
                    print(f"URL already exists in {file_path}")
                    return False
        
        # Append URL to file
        with open(file_path, "a") as f:
            f.write(f"\n{url}")
        
        # Optionally process immediately
        await self.process_url(url, url_type)
        return True

    async def process_url(self, url: str, url_type: URLType):
        """Process a single URL based on its type"""
        try:
            if url_type == "YOUTUBE":
                await self.process_youtube(url)
            elif url_type == "GITHUB":
                await self.process_github(url)
            elif url_type == "URL":
                await self.process_site(url)
        except Exception as e:
            print(f"Error processing {url}: {e}")

    async def process_all_pending(self):
        """Process all URLs from all list files"""
        for url_type, file_path in self.files.items():
            if not file_path.exists():
                continue
                
            with open(file_path, "r") as f:
                urls = [url.strip() for url in f if url.strip() and not url.startswith("#")]
                
            for url in urls:
                await self.process_url(url, url_type)

    def remove_url(self, url: str, url_type: URLType):
        """Remove the processed URL from its list file to avoid duplication"""
        file_path = self.files[url_type]
        if not file_path.exists():
            return
        with open(file_path, "r") as f:
            lines = f.readlines()
        # Write back only the lines that don't match the URL (after stripping newlines/spaces)
        with open(file_path, "w") as f:
            for line in lines:
                if line.strip() != url:
                    f.write(line)
        print(f"Removed URL from {file_path}: {url}")

    # YouTube processing: handles both playlist and single video
    async def process_youtube(self, url: str):
        processed = False
        try:
            content_type, content_id = extract_youtube_ids(url)
            if not content_type or not content_id:
                print("Invalid YouTube URL. Please check the URL.")
                return
            
            print(f"Detected YouTube {content_type} with ID: {content_id}")
            
            if content_type == "playlist":
                # Process as a playlist – this function handles each video in the playlist.
                process_youtube_playlist(content_id)
                processed = True
            elif content_type == "video":
                # Process a single video:
                youtube = initialize_youtube_api()
                if not youtube:
                    print("YouTube API initialization failed. Cannot process video.")
                    return
                try:
                    video_info = youtube.videos().list(
                        part="snippet",
                        id=content_id
                    ).execute()
                    
                    if video_info.get('items'):
                        video = video_info['items'][0]['snippet']
                        print("Found video:")
                        print(f"Title: {video['title']}")
                        print(f"Channel: {video['channelTitle']}")
                        print(f"Published: {video['publishedAt'].split('T')[0]}")
                        
                        transcript = get_video_transcript(content_id)
                        if transcript:
                            content = (
                                f"Title: {video['title']}\n"
                                f"Channel: {video['channelTitle']}\n"
                                f"Published: {video['publishedAt']}\n\n"
                                f"Transcript:\n{transcript}"
                            )
                            metadata = {
                                "source": "YouTube",
                                "source_type": "video",
                                "video_id": content_id,
                                "title": video["title"],
                                "channel": video["channelTitle"],
                                "published_at": video["publishedAt"],
                                "processed_at": datetime.now().isoformat()
                            }
                            doc_id = insert_document({
                                "content": content,
                                "metadata": metadata,
                                "tech_stack_id": None
                            })
                            print(f"Successfully processed and stored video: {video['title']} (Document ID: {doc_id})")
                        else:
                            print("No transcript available for this video.")
                        processed = True
                    else:
                        print("Video not found. Please check the URL.")
                except Exception as e:
                    print(f"Error processing single video: {str(e)}")
        finally:
            if processed:
                self.remove_url(url, "YOUTUBE")
                
    # GitHub processing: clones, iterates over files (chunking large files), and inserts them into the database
    async def process_github(self, url: str):
        processed = False
        try:
            print("Cloning GitHub repository...")
            repo_path = clone_repo(url)
            print(f"Repository cloned to {repo_path}")
            
            commit_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path
            ).strip().decode()
            
            parts = url.strip().split("/")
            repo_owner = parts[-2]
            repo_name = parts[-1]
            
            peak_memory = 0
            process_ps = psutil.Process(os.getpid())
            def log_memory(prefix=""):
                nonlocal peak_memory
                current_mem = process_ps.memory_info().rss
                if current_mem > peak_memory:
                    peak_memory = current_mem
                print(f"GitHub {prefix}: Current Memory: {current_mem // (1024*1024)} MB, Peak: {peak_memory // (1024*1024)} MB")
            
            log_memory("Start")
            
            async def process_files():
                for file in repo_path.rglob("*"):
                    await wait_for_memory_available()
                    if file.is_file():
                        if file.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg"}:
                            continue
                        try:
                            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                                file_content = f.read()
                            if file.stat().st_size > 5_000_000:
                                chunks = chunk_text(file_content, chunk_size=1000)
                                for i, chunk in enumerate(chunks):
                                    data = {
                                        "repo_name": repo_name,
                                        "repo_owner": repo_owner,
                                        "branch": "main",
                                        "commit_hash": commit_hash,
                                        "file_path": f"{str(file.relative_to(repo_path))}_chunk_{i+1}",
                                        "file_type": file.suffix.lstrip(".").lower() or "txt",
                                        "file_size": len(chunk),
                                        "file_content": chunk,
                                        "tech_stack_id": None
                                    }
                                    file_id = insert_github(data)
                                    print(f"Processed chunk {i+1} of {file.name} (ID: {file_id})")
                            else:
                                data = {
                                    "repo_name": repo_name,
                                    "repo_owner": repo_owner,
                                    "branch": "main",
                                    "commit_hash": commit_hash,
                                    "file_path": str(file.relative_to(repo_path)),
                                    "file_type": file.suffix.lstrip(".").lower() or "txt",
                                    "file_size": file.stat().st_size,
                                    "file_content": file_content,
                                    "tech_stack_id": None
                                }
                                file_id = insert_github(data)
                                print(f"Processed {file.name} (ID: {file_id})")
                        except Exception as e:
                            print(f"Error processing file {file}: {e}")
                    log_memory("During file processing")
            
            await process_files()
            shutil.rmtree(repo_path)
            print("Repository processed and temporary files cleaned up!")
            processed = True
        except Exception as e:
            print(f"Error processing GitHub repository: {e}")
        finally:
            if processed:
                self.remove_url(url, "GITHUB")

    # Site URL processing: uses crawl4ai to crawl the URL, chunks the resulting content, and inserts each chunk into the database
    async def process_site(self, url: str):
        processed = False
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
                extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
            )
            crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            crawler = AsyncWebCrawler(config=browser_config)
            await crawler.start()
            
            await wait_for_memory_available(1000)
            result = await crawler.arun(url=url, config=crawl_config)
            
            if isinstance(result, Exception):
                print(f"Error processing URL: {result}")
            else:
                if result.success:
                    raw_text = result.markdown_v2.raw_markdown
                    chunks = chunk_text(raw_text, chunk_size=1000)
                    for j, chunk in enumerate(chunks):
                        metadata = {
                            "title": "No Title",
                            "crawl_label": None,
                            "extracted_at": datetime.now().isoformat(),
                            "source": "crawl4ai",
                            "source_type": "webpage",
                            "url": url
                        }
                        data = {
                            "url": url,
                            "chunk_number": j,
                            "title": metadata["title"],
                            "summary": "",
                            "content": chunk,
                            "metadata": metadata
                        }
                        insert_site_page(data)
                    processed = True
                else:
                    print(f"Failed to crawl {url}")
            await crawler.close()
        except Exception as e:
            print(f"Error processing site URL: {e}")
        finally:
            if processed:
                self.remove_url(url, "URL")

def main():
    processor = URLProcessor()
    
    if len(sys.argv) > 2:
        url = sys.argv[1]
        url_type = sys.argv[2].upper()
        if url_type in ["YOUTUBE", "GITHUB", "URL"]:
            asyncio.run(processor.process_new_url(url, url_type))
    else:
        asyncio.run(processor.process_all_pending())

if __name__ == "__main__":
    main()
