from typing import List, Optional
import os
import asyncio
import logging
import tempfile
import random
import httpx
import tiktoken
from pathlib import Path
import subprocess
import asyncpg
from dotenv import load_dotenv
import shutil
import json
import numpy as np
import PyPDF2  

# Load environment variables from .env
load_dotenv()

# Constants
TOKEN_LIMIT = 8000
CHUNK_MAX_TOKENS = TOKEN_LIMIT // 2
EMBEDDING_DIMENSION = 768  # Set the correct dimension for the embedding

def validate_db_params():
    required_vars = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
validate_db_params()
DB_PARAMS = {
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT"),
    "database": None  # Database name will be set dynamically
}

# Cache the tokenizer encoding globally
ENCODING = tiktoken.get_encoding("cl100k_base")

# Global semaphore to limit concurrent DB operations
db_semaphore = asyncio.Semaphore(10)
# Global semaphore to limit concurrent embedding API calls
embedding_semaphore = asyncio.Semaphore(5)

async def create_db_pool(db_name: str, max_retries: int = 3, base_delay: float = 1.0) -> Optional[asyncpg.Pool]:
    conn_params = DB_PARAMS.copy()
    conn_params["database"] = db_name
    
    for attempt in range(1, max_retries + 1):
        try:
            pool = await asyncpg.create_pool(**conn_params, min_size=1, max_size=20)
            return pool
        except Exception as e:
            logging.error(f"Attempt {attempt}/{max_retries} failed to create connection pool for {db_name}: {e}")
            if attempt == max_retries:
                logging.error(f"Failed to create connection pool for {db_name} after {max_retries} attempts.")
                return None
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logging.warning(f"Retrying in {delay:.2f}s...")
            await asyncio.sleep(delay)
    return None

async def create_tables(pool: asyncpg.Pool):
    """Create tables if they don't exist with vector type."""
    async with pool.acquire() as conn:
        # First create vector extension if it doesn't exist
        await conn.execute('CREATE EXTENSION IF NOT EXISTS vector;')
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS github (
                id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
                repo_name TEXT NOT NULL,
                repo_owner TEXT NOT NULL,
                branch TEXT NOT NULL DEFAULT 'main',
                commit_hash TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                embedding vector(768)
            );
        """)

async def average_embeddings(embeddings_list: List[List[float]]) -> List[float]:
    """Average multiple embeddings into a single embedding vector."""
    if not embeddings_list:
        return [0.0] * EMBEDDING_DIMENSION
    embeddings_list = [[float(x) for x in emb] for emb in embeddings_list]
    return np.mean(embeddings_list, axis=0).tolist()

async def upload_to_postgres_batch(values: List[tuple], pool: asyncpg.Pool):
    """Upload data to PostgreSQL with vector type handling."""
    async with db_semaphore:
        async with pool.acquire() as conn:
            processed_values = []
            for repo_name, repo_owner, branch, commit_hash, file_path, file_type, file_size, file_content, embedding in values:
                avg_embedding = await average_embeddings(embedding)
                if len(avg_embedding) != EMBEDDING_DIMENSION:
                    avg_embedding = (avg_embedding[:EMBEDDING_DIMENSION] 
                                     if len(avg_embedding) > EMBEDDING_DIMENSION 
                                     else avg_embedding + [0.0] * (EMBEDDING_DIMENSION - len(avg_embedding)))
                vector_str = '[' + ','.join(map(str, avg_embedding)) + ']'
                processed_values.append((
                    repo_name, repo_owner, branch, commit_hash,
                    file_path, file_type, file_size, file_content,
                    vector_str
                ))
            stmt = await conn.prepare("""
                INSERT INTO github 
                (repo_name, repo_owner, branch, commit_hash, file_path, 
                 file_type, file_size, file_content, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector(768))
            """)
            await stmt.executemany(processed_values)

async def clone_repo(repo_url: str, max_retries: int = 3, base_delay: float = 1.0) -> Path:
    temp_dir = tempfile.mkdtemp()
    for attempt in range(1, max_retries + 1):
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "clone", "--depth", "1", repo_url, temp_dir],
                check=True,
                capture_output=True
            )
            return Path(temp_dir)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error cloning {repo_url} (attempt {attempt}/{max_retries}): {e.stderr.decode()}")
            if attempt == max_retries:
                logging.error(f"Failed to clone {repo_url} after {max_retries} attempts.")
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logging.warning(f"Retrying clone in {delay:.2f}s...")
            await asyncio.sleep(delay)
    raise Exception(f"Failed to clone {repo_url} after {max_retries} attempts")

async def is_valid_repo(repo_path: Path) -> bool:
    """Check if the repository is valid and not empty."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--git-dir",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception as e:
        logging.error(f"Error checking repository validity: {e}")
        return False

async def get_git_branch(repo_path: Path, max_retries: int = 3, base_delay: float = 1.0) -> str:
    """Get the current branch name, with better error handling."""
    for attempt in range(1, max_retries + 1):
        try:
            head_check = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--verify", "HEAD",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await head_check.communicate()
            if head_check.returncode != 0:
                logging.warning(f"No commits found in repository {repo_path}")
                return "main"
            proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--abbrev-ref", "HEAD",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                branch = stdout.decode().strip()
                return branch if branch else "main"
            else:
                logging.warning(f"Could not determine branch for {repo_path}: {stderr.decode().strip()}")
                return "main"
        except Exception as e:
            logging.warning(f"Error determining branch for {repo_path}: {e}")
            if attempt == max_retries:
                return "main"
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
    return "main"

async def get_commit_hash(repo_path: Path, max_retries: int = 3, base_delay: float = 1.0) -> str:
    """Get the current commit hash, with better error handling."""
    for attempt in range(1, max_retries + 1):
        try:
            head_check = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--verify", "HEAD",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await head_check.communicate()
            if head_check.returncode != 0:
                logging.warning(f"No commits found in repository {repo_path}")
                return "initial"
            proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "HEAD",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return stdout.decode().strip()
            else:
                logging.error(f"Could not retrieve commit hash for {repo_path}: {stderr.decode().strip()}")
                return "unknown"
        except Exception as e:
            logging.error(f"Error retrieving commit hash for {repo_path}: {e}")
            if attempt == max_retries:
                return "unknown"
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
    return "unknown"

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF file using PyPDF2 and clean null bytes."""
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text += page_text
        return text.replace("\x00", "")
    except Exception as e:
        logging.error(f"Error extracting text from {pdf_path}: {e}")
        return ""

async def process_repository(repo_url: str, db_name: str, pool: asyncpg.Pool):
    """Process a single repository and store its contents in PostgreSQL.
       Skips processing if the repository commit has already been stored.
    """
    temp_repo = None
    try:
        await create_tables(pool)
        temp_repo = await clone_repo(repo_url)
        if not await is_valid_repo(temp_repo):
            logging.error(f"Invalid or empty repository: {repo_url}")
            return
            
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_owner = repo_url.split("/")[-2]
        
        try:
            branch = await get_git_branch(temp_repo)
            commit_hash = await get_commit_hash(temp_repo)
        except Exception as e:
            logging.error(f"Failed to get git info for {repo_url}: {e}")
            return

        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT 1 FROM github
                WHERE repo_name = $1
                  AND repo_owner = $2
                  AND commit_hash = $3
                """,
                repo_name, repo_owner, commit_hash
            )
        if existing is not None:
            print(f"Repository {repo_url} already processed, skipping.")
            return

        for file_path in temp_repo.rglob("*"):
            if ".git" in file_path.parts or not file_path.is_file():
                continue

            binary_extensions = {
                '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg',
                '.pack', '.idx', '.onnx', '.wav', '.zip', '.msg',
                '.xlsx', '.odt', '.xz', '.db'
            }
            if file_path.suffix.lower() in binary_extensions:
                print(f"Skipping binary file: {file_path}")
                continue

            try:
                if file_path.suffix.lower() == '.pdf':
                    file_content = extract_text_from_pdf(file_path)
                elif file_path.suffix.lower() == '.txt':
                    try:
                        raw = file_path.read_bytes().replace(b'\x00', b'')
                        file_content = raw.decode('utf-8', errors='replace')
                    except Exception as e:
                        logging.error(f"Error reading text file {file_path}: {e}")
                        continue
                else:
                    file_content = file_path.read_text(encoding='utf-8', errors='ignore')
                    # Remove any null bytes from the content
                    file_content = file_content.replace("\x00", "")
                    
                file_type = file_path.suffix[1:] if file_path.suffix else "unknown"
                file_size = file_path.stat().st_size
    
                embedding = await generate_embedding(file_content)
                await upload_to_postgres_batch(
                    [(repo_name, repo_owner, branch, commit_hash,
                      str(file_path.relative_to(temp_repo)), file_type,
                      file_size, file_content, embedding)],
                    pool
                )
            except Exception as e:
                logging.error(f"Error processing file {file_path}: {e}")
                continue

    except Exception as e:
        logging.error(f"Error processing repository {repo_url}: {e}")
    finally:
        if temp_repo is not None and temp_repo.exists():
            try:
                shutil.rmtree(str(temp_repo))
                logging.info(f"Temporary repository {temp_repo} removed successfully.")
            except Exception as cleanup_error:
                logging.error(f"Error cleaning up temporary repository {temp_repo}: {cleanup_error}")

async def process_repos_from_txt():
    """Process repositories listed in txt files."""
    base_path = Path('/home/ai-agents/post_data')
    repo_txt_files = [
        "repo_flowise.txt",
        "repo_huggingface.txt",
        "repo_n8n.txt",
        "repo_lang_agent.txt",
        "repo_huggingface_smol.txt",
        "repo_pydantic_ai.txt",
        "repo_ai_agents.txt"
    ]
    
    async def process_repo_file(repo_file):
        print(f"Processing file: {repo_file}")
        tool_db_name = repo_file.replace("repo_", "").replace(".txt", "")
        print(f"Database name: {tool_db_name}")
        
        pool = await create_db_pool(tool_db_name)
        if not pool:
            logging.error(f"Failed to create pool for {tool_db_name}, skipping")
            return
        
        file_path = base_path / repo_file
        if file_path.exists():
            print(f"Found file at: {file_path}")
            with open(file_path, "r") as f:
                repos = f.readlines()
            print(f"Found {len(repos)} repositories to process")
            
            for repo_url in repos:
                repo_url = repo_url.strip()
                if repo_url:
                    print(f"Processing repository: {repo_url}")
                    await process_repository(repo_url, tool_db_name, pool)
        else:
            print(f"File not found: {file_path}")
        
        if pool:
            await pool.close()

    await asyncio.gather(*(process_repo_file(repo_file) for repo_file in repo_txt_files))

def chunk_text_tokens(text: str, max_tokens: int = 1000) -> list[str]:
    """Chunk text using token counts. Uses the 'cl100k_base' encoding."""
    # Remove null bytes to avoid issues in encoding
    text = text.replace("\x00", "")
    try:
        tokens = ENCODING.encode(text, disallowed_special=())
    except Exception as e:
        logging.error(f"Error encoding text: {e}")
        raise
    chunks = [tokens[i: i + max_tokens] for i in range(0, len(tokens), max_tokens)]
    try:
        return [ENCODING.decode(chunk) for chunk in chunks]
    except Exception as e:
        logging.error(f"Error decoding tokens: {e}")
        raise

async def get_embedding(text: str, max_retries: int = 3, base_delay: float = 1.0) -> list[float]:
    """Asynchronously get an embedding for a text chunk using the Ollama API."""
    ollama_url = "http://10.147.20.20:11434/api/embeddings"
    model_name = "nomic-embed-text"

    async with embedding_semaphore:
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        ollama_url,
                        json={"model": model_name, "prompt": text},
                        timeout=90
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result["embedding"]
            except httpx.HTTPStatusError as e:
                logging.error(f"HTTP error getting embedding (attempt {attempt}): {e}")
                if attempt == max_retries:
                    logging.error(f"Failed to get embedding after {max_retries} attempts due to HTTP error.")
                    return [0.0] * EMBEDDING_DIMENSION
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
            except httpx.TimeoutException as e:
                logging.error(f"Timeout error getting embedding (attempt {attempt}): {e}")
                if attempt == max_retries:
                    logging.error(f"Failed to get embedding after {max_retries} attempts due to timeout.")
                    return [0.0] * EMBEDDING_DIMENSION
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
            except Exception as e:
                logging.error(f"Error getting embedding (attempt {attempt}): {e}")
                if attempt == max_retries:
                    logging.error(f"Failed to get embedding after {max_retries} attempts due to an unexpected error.")
                    return [0.0] * EMBEDDING_DIMENSION
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

async def generate_embedding(file_content: str) -> List[List[float]]:
    """Generate embeddings for the given file content."""
    try:
        chunks = chunk_text_tokens(file_content, max_tokens=CHUNK_MAX_TOKENS)
    except Exception as e:
        logging.error(f"Tokenization error: {e}. Skipping embedding generation for this file.")
        return [[0.0] * EMBEDDING_DIMENSION]
    tasks = [get_embedding(chunk) for chunk in chunks]
    embeddings = await asyncio.gather(*tasks)
    return embeddings

async def main():
    logging.info("🚀 Starting repository processing...")
    await process_repos_from_txt()
    logging.info("✅ All repositories processed and stored in PostgreSQL.")

if __name__ == "__main__":
    print("🚀 Starting repository processing...")
    asyncio.run(main())
    print("✅ All repositories processed and stored in PostgreSQL.")
