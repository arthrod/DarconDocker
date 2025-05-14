import os
import openai
import subprocess
import tempfile
import tiktoken
from supabase import create_client, Client
from pathlib import Path
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Set API Keys & Supabase Connection
openai.api_key = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_API_KEY:
    raise ValueError("Missing Supabase URL or Key in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

# Embedding Model Configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
TOKEN_LIMIT = 8000  # Ensure under 8192 tokens per request

SUPABASE_TABLE_NAME = "github"

# Clone the repository
def clone_repo(repo_url: str):
    """Clones a GitHub repository into a temporary directory."""
    temp_dir = tempfile.mkdtemp()
    subprocess.run(["git", "clone", "--depth=1", repo_url, temp_dir], check=True)
    return Path(temp_dir)

# Split text into chunks
def chunk_text(text: str, max_tokens: int = 1000):
    """Splits text into manageable chunks within token limits."""
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    return [encoding.decode(tokens[i:i + max_tokens]) for i in range(0, len(tokens), max_tokens)]

# Generate embeddings
def generate_embedding(file_content: str):
    """Generates embeddings for file chunks using OpenAI API with a slight delay."""
    try:
        chunks = chunk_text(file_content, max_tokens=TOKEN_LIMIT // 2)
        embeddings = []

        for chunk in chunks:
            print(f" Sending chunk to OpenAI: {chunk[:80]}...")
            response = openai.embeddings.create(model=EMBEDDING_MODEL, input=[chunk])
            embeddings.append(response.data[0].embedding)
            time.sleep(0.5)  # 500ms delay to prevent rate limiting

        return embeddings
    except Exception as e:
        print(f" Embedding error: {e}")
        return None

# Upload to Supabase
def upload_to_supabase(repo_name, repo_owner, branch, commit_hash, file_path, file_type, file_size, file_content, embeddings):
    """Uploads processed file chunks to Supabase."""
    try:
        for i, embedding in enumerate(embeddings):
            insert_data = {
                "source": "n8n",
                "url": GITHUB_REPO_URL,
                "repo_name": repo_name or "unknown",
                "repo_owner": repo_owner or "unknown",
                "branch": branch or "main",
                "commit_hash": commit_hash or "unknown",
                "chunk_number": i,
                "title": file_path or "unknown",
                "summary": file_content[:250] or "No summary available",
                "content": file_content or "No content",
                "metadata": {"file_path": file_path, "file_type": file_type, "file_size": file_size},
                "embedding": embedding
            }

            # Check if entry exists
            try:
                response_check = supabase.rpc("match_github_files", {"query_embedding": embedding, "match_count": 1}).execute()
                if response_check and response_check.data:
                    print(f" Skipping existing entry: {file_path} (chunk {i})")
                    continue
            except Exception as e:
                print(f" Error checking existing entry: {e}")

            # Insert data into Supabase
            try:
                response = supabase.table(SUPABASE_TABLE_NAME).upsert(insert_data, on_conflict=["source", "url", "chunk_number"]).execute()
                if response and hasattr(response, "error") and response.error:
                    print(f" Supabase error: {response.error}")
                else:
                    print(f" Uploaded: {file_path} (chunk {i})")
            except Exception as e:
                print(f" Upload failed for {file_path}: {e}")
    except Exception as e:
        print(f" Error in upload_to_supabase: {e}")
        return None

# Process the GitHub repo
def process_github_repo(repo_url: str):
    """Clones and processes a GitHub repository, storing its data in Supabase."""
    print(f" Cloning repo: {repo_url}")
    repo_path = clone_repo(repo_url)

    repo_name = repo_url.split("/")[-1]
    repo_owner = repo_url.split("/")[-2]
    branch = "main"
    commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path).strip().decode()

    # Process files in the repo
    for file in repo_path.rglob("*"):
        if file.is_file():
            file_size = file.stat().st_size
            file_type = file.suffix[1:].lower()

            # Skip unnecessary file types
            if file_type in {"png", "jpg", "jpeg", "gif", "ico", "svg", "pack", "idx"} or file_size > 5_000_000:
                print(f" Skipping: {file} ({file_type}, {file_size} bytes)")
                continue

            try:
                with open(file, "r", encoding="utf-8", errors="ignore") as f:
                    file_content = f.read()
            except Exception as e:
                print(f" Read error: {file}: {e}")
                continue

            # Generate embeddings
            embeddings = generate_embedding(file_content)
            if embeddings:
                upload_to_supabase(
                    repo_name, repo_owner, branch, commit_hash,
                    str(file.relative_to(repo_path)), file_type, file_size, file_content, embeddings
                )
                # Indicate success for external callers
                return True

# Alias for external scripts (e.g., streamlit)
process_and_upload_repo = process_github_repo

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Process and upload a GitHub repo to Supabase.")
    parser.add_argument("github_url", type=str, help="GitHub repository URL to process.")
    args = parser.parse_args()
    success = process_and_upload_repo(args.github_url)
    if success:
        print(" Repository processed and uploaded successfully.")
    else:
        print(" Failed to process and upload the repository.")
