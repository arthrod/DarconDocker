import os
import sys
import requests
import subprocess
import tempfile
import shutil
import concurrent.futures
from pathlib import Path
import time
import json
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === CONFIG ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SUPABASE_TABLE_NAME = "github"
OLLAMA_URL = "http://10.147.20.20:11434"
EMBED_MODEL = "nomic-embed-text"

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)

def clone_repo(repo_url: str):
    temp_dir = tempfile.mkdtemp()
    subprocess.run(["git", "clone", "--depth=1", repo_url, temp_dir], check=True)
    return Path(temp_dir)

def chunk_text(text: str, max_chars: int = 3000):
    return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]

def generate_embedding(text: str):
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text}
        )
        if response.status_code != 200:
            print(f"\n[Embedding Error] Status {response.status_code}: {response.text}\n")
            response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        print(f"[Embedding Generation Failed] {e}")
        raise

def parse_dependencies(repo_path: Path):
    dependencies = []
    try:
        req_file = repo_path / "requirements.txt"
        pkg_file = repo_path / "package.json"
        pyproject_file = repo_path / "pyproject.toml"

        if req_file.exists():
            with open(req_file, "r") as f:
                dependencies.extend([line.strip() for line in f if line.strip() and not line.startswith("#")])
        elif pkg_file.exists():
            with open(pkg_file, "r") as f:
                pkg_data = json.load(f)
                deps = pkg_data.get("dependencies", {})
                dependencies.extend(deps.keys())
        elif pyproject_file.exists():
            with open(pyproject_file, "r") as f:
                for line in f:
                    if line.strip().startswith("[tool.poetry.dependencies]"):
                        break
                for line in f:
                    if line.startswith("["):
                        break
                    if "=" in line:
                        dep = line.split("=")[0].strip()
                        dependencies.append(dep)
    except Exception as e:
        print(f"[Dependency Parse Error] {e}")
    return dependencies

def get_last_modified(file_path: Path):
    try:
        timestamp = subprocess.check_output(["git", "log", "-1", "--format=%ct", str(file_path)], cwd=file_path.parent).strip()
        return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(int(timestamp)))
    except Exception as e:
        print(f"[Timestamp Error] {file_path}: {e}")
        return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(file_path.stat().st_mtime))

def upload_chunk(data):
    try:
        response = supabase.table(SUPABASE_TABLE_NAME).insert(data).execute()
        if hasattr(response, 'error') and response.error:
            print(f"[Upload Error] {response.error}")
        else:
            print(f"✅ Uploaded: {data['file_path']} [chunk {data['chunk_number']}]")
    except Exception as e:
        print(f"[Upload Failed] {e}")

def process_file(file_path, repo_info, dependencies):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"[File Read Error] {file_path}: {e}")
        return

    chunks = chunk_text(content)
    doc_type = "documentation" if any(part in str(file_path).lower() for part in ["/docs/", "/documentation/", "/doc/"]) else "source_code"
    if file_path.name.lower() == "readme.md":
        doc_type = "readme"

    last_modified = get_last_modified(file_path)

    for idx, chunk in enumerate(chunks):
        try:
            print(f"🔹 Processing chunk {idx} of {file_path.relative_to(repo_info['repo_path'])}...")
            embedding = generate_embedding(chunk)
            data = {
                "source": repo_info['repo_name'],
                "url": repo_info['repo_url'],
                "repo_name": repo_info['repo_name'],
                "repo_owner": repo_info['repo_owner'],
                "branch": repo_info['branch'],
                "commit_hash": repo_info['commit_hash'],
                "chunk_number": idx,
                "file_path": str(file_path.relative_to(repo_info['repo_path'])) if file_path.exists() else str(file_path),
                "file_type": file_path.suffix[1:],
                "file_size": file_path.stat().st_size,
                "title": file_path.name,
                "summary": chunk[:250],
                "file_content": chunk,
                "metadata": {
                    "doc_type": doc_type,
                    "last_modified": last_modified,
                    "dependencies": dependencies
                },
                "embedding": embedding,
            }
            upload_chunk(data)
        except Exception as e:
            print(f"[Chunk Process Error] {file_path}: {e}")

def process_github_repo(repo_url: str):
    print(f"\n🚀 Cloning {repo_url}...")
    repo_path = clone_repo(repo_url)

    repo_name = repo_url.split("/")[-1].replace(".git", "")
    repo_owner = repo_url.split("/")[-2]
    branch = "main"
    commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path).strip().decode()

    dependencies = parse_dependencies(repo_path)

    repo_info = {
        "repo_url": repo_url,
        "repo_path": repo_path,
        "repo_name": repo_name,
        "repo_owner": repo_owner,
        "branch": branch,
        "commit_hash": commit_hash,
    }

    files = [f for f in repo_path.rglob("*") if f.is_file() and f.suffix[1:].lower() not in {"png", "jpg", "jpeg", "gif", "ico", "svg", "pack", "idx"} and f.stat().st_size <= 5_000_000]

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(lambda f: process_file(f, repo_info, dependencies), files)

    shutil.rmtree(repo_path)
    print(f"\n✅ Deleted temp repo: {repo_path}\n")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("\nUsage: python3 git_supa.py <github_repo_url>\nExample: python3 git_supa.py https://github.com/user/repo.git\n")
        sys.exit(1)

    repo_url = sys.argv[1]
    process_github_repo(repo_url)
    print("\n✅ All done!\n")
    print("Please check the Supabase table for the uploaded data.\n")