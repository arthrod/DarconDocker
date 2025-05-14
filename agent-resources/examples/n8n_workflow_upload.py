import os
import asyncio
import logging
import tempfile
from pathlib import Path
import asyncpg
from dotenv import load_dotenv
import shutil

# Load environment variables from .env
load_dotenv()

# Validate required env variables
def validate_db_params():
    required_vars = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing env vars: {', '.join(missing)}")
validate_db_params()

# DB parameters
DB_PARAMS = {
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT"),
    "database": None  # set dynamically
}

# Create connection pool
async def create_db_pool(db_name: str, max_retries: int = 3, base_delay: float = 1.0) -> asyncpg.Pool:
    params = DB_PARAMS.copy()
    params["database"] = db_name
    for attempt in range(1, max_retries + 1):
        try:
            pool = await asyncpg.create_pool(**params, min_size=1, max_size=10)
            return pool
        except Exception as e:
            logging.error(f"Pool creation attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(base_delay * attempt)
    raise Exception("Could not create DB pool")

# Create table for n8n workflows if not exists
async def create_table_n8n(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS n8n_user_wrkflows (
                id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

# Process files in the n8n workflow folder (only .json files)
async def process_n8n_workflows(pool: asyncpg.Pool):
    folder = Path("/home/ai-agents/post_data/n8n_userflows")
    if not folder.exists():
        logging.error(f"Folder not found: {folder}")
        return

    async with pool.acquire() as conn:
        query = """
            INSERT INTO n8n_user_wrkflows
                (file_path, file_type, file_size, file_content)
            VALUES ($1, $2, $3, $4)
        """
        for file_path in folder.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() != ".json":
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                file_type = "json"
                file_size = file_path.stat().st_size
                
                await conn.execute(query, str(file_path.relative_to(folder)), file_type, file_size, content)
                logging.info(f"Inserted file: {file_path}")
            except Exception as e:
                logging.error(f"Error processing {file_path}: {e}")

async def main():
    # Use a DB name for n8n workflows e.g., "n8n"
    pool = await create_db_pool("n8n")
    await create_table_n8n(pool)
    await process_n8n_workflows(pool)
    await pool.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
