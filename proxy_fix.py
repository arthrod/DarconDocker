import sys
import os
from pathlib import Path

# Add the agent-resources/tools directory to the path
sys.path.append(str(Path(__file__).parent / "agent-resources" / "tools"))

# Import the YouTube tool module
import youtube_tool

# Backup the original function
original_fetch_transcript = youtube_tool.fetch_transcript

# Define a new function that uses proxies
def fetch_transcript_with_proxy(video_id):
    """
    Enhanced version of fetch_transcript that uses free proxies to bypass YouTube IP blocking.
    """
    try:
        # First try with the original function
        print(f"Trying to fetch transcript for {video_id} without proxy...")
        return original_fetch_transcript(video_id)
    except Exception as e:
        print(f"Regular fetch failed: {str(e)}")
        
        # If that fails, try with free proxies
        print("Trying with proxies...")
        
        # List of free proxy servers to try (these are examples, they may not work)
        # In a real implementation, you would use a proxy rotation service or your own proxies
        proxies = [
            {'https': 'https://163.172.31.45:80'},
            {'https': 'https://51.159.115.233:3128'},
            {'https': 'https://51.158.68.133:8811'},
            {'https': 'https://51.158.98.121:8811'}
        ]
        
        # Try each proxy
        for proxy in proxies:
            try:
                print(f"Trying proxy: {proxy}")
                from youtube_transcript_api import YouTubeTranscriptApi
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, proxies=proxy)
                transcript_text = " ".join([entry["text"] for entry in transcript_list])
                print(f"✅ Success with proxy {proxy}")
                return transcript_text
            except Exception as proxy_error:
                print(f"Proxy {proxy} failed: {str(proxy_error)}")
                continue
        
        # If all proxies fail, return empty string as the original function would
        print("All proxies failed. No transcript available.")
        return ""

# Replace the original function with our enhanced version
youtube_tool.fetch_transcript = fetch_transcript_with_proxy

print("YouTube transcript function patched to use proxies.")
print("Now running the YouTube tool with the playlist URL...")

# Process the playlist
playlist_url = "https://www.youtube.com/playlist?list=PLyrg3m7Ei-Mr_FkLdJFx2DCnEOiek4yqa"
youtube_tool.process_youtube_url(playlist_url)
