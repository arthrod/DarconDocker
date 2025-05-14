import os
import asyncio
import logging
import shutil
import httpx
import random
import json
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import asyncpg
import fitz  # PyMuPDF: for PDF text extraction
from typing import List, Optional
import aiofiles

# Load environment variables
load_dotenv()

# DB and token settings (consistent with the other tools)
TOKEN_LIMIT = 8000
CHUNK_MAX_TOKENS = TOKEN_LIMIT // 2
DB_PARAMS = {
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT"),
    "database": None  # To be set dynamically per tool
}

# Global HTTP client for reuse
http_client = None  # Will be initialized in main()

async def create_db_pool(db_name: str):
    conn_params = DB_PARAMS.copy()
    conn_params["database"] = db_name
    try:
        pool = await asyncpg.create_pool(**conn_params, min_size=1, max_size=20)
        return pool
    except Exception as e:
        logging.error(f"Failed to create pool for {db_name}: {e}")
        return None

def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = start + chunk_size
        if end >= text_length:
            chunks.append(text[start:].strip())
            break
        chunk = text[start:end]
        # Attempt to split on a code block or newline for sensible breakpoints
        code_block = chunk.rfind("```")
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block
        elif "\n\n" in chunk:
            last_break = chunk.rfind("\n\n")
            if last_break > chunk_size * 0.3:
                end = start + last_break
        elif ". " in chunk:
            last_period = chunk.rfind(". ")
            if last_period > chunk_size * 0.3:
                end = start + last_period + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(start + 1, end)
    return chunks

async def get_embedding(text: str, max_retries: int = 3, base_delay: float = 1.0) -> List[float]:
    ollama_url = "http://10.147.20.20:11434/api/embeddings"
    model_name = "nomic-embed-text"
    for attempt in range(1, max_retries + 1):
        try:
            response = await http_client.post(
                ollama_url,
                json={"model": model_name, "prompt": text},
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result["embedding"]
        except Exception as e:
            logging.error(f"Error getting embedding (attempt {attempt}): {e}")
            if attempt == max_retries:
                return [0] * 768  # updated to 768 dimensions
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)

async def generate_embedding(text: str) -> List[float]:
    """Generate embedding for the entire text by chunking and averaging."""
    chunks = chunk_text(text, chunk_size=CHUNK_MAX_TOKENS)
    if not chunks:
        return [0] * 768  # updated to 768 dimensions
    embeddings = await asyncio.gather(*(get_embedding(chunk) for chunk in chunks))
    # Average the embeddings across chunks
    avg_embedding = [sum(x) / len(x) for x in zip(*embeddings)]
    return avg_embedding

async def download_pdf(pdf_url: str, dest_folder: Path) -> Optional[Path]:
    """Download a PDF from the given URL into dest_folder and return the file path."""
    try:
        response = await http_client.get(pdf_url, timeout=120)
        response.raise_for_status()
        filename = os.path.basename(pdf_url.split("?")[0])
        file_path = dest_folder / filename
        # Offload file writing to a thread to avoid blocking
        await asyncio.to_thread(lambda: file_path.write_bytes(response.content))
        return file_path
    except Exception as e:
        logging.error(f"Error downloading PDF from {pdf_url}: {e}")
        return None

def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF file using PyMuPDF (fitz), logging page-by-page."""
    try:
        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        logging.info(f"Extracting {page_count} pages from {pdf_path.name}")
        texts = []
        for page_num in range(page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            texts.append(page_text)
            logging.info(f"Processed page {page_num + 1} of {page_count} from {pdf_path.name}")
        return "\n".join(texts).strip()
    except Exception as e:
        logging.error(f"Error extracting text from {pdf_path}: {e}")
        return ""

async def upload_to_documents_table(content: str, metadata: dict, pool: asyncpg.Pool):
    """Upload PDF content and metadata into the documents table."""
    embedding = await generate_embedding(content)
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO documents (content, metadata, embedding)
                VALUES ($1, $2, $3)
                """,
                content, json.dumps(metadata), str(tuple(embedding)).replace("(", "[").replace(")", "]")
            )
            logging.info("Successfully stored PDF document in database.")
        except Exception as e:
            logging.error(f"Error inserting PDF data into documents table: {e}")

async def process_pdf_url(pdf_url: str, pool: asyncpg.Pool):
    """Process a single PDF URL: download, extract text, upload, and cleanup."""
    temp_folder = Path("/home/ai-agents/post_data/temp_pdf")
    temp_folder.mkdir(exist_ok=True)
    
    file_path = await download_pdf(pdf_url, temp_folder)
    if not file_path:
        return

    # Offload PDF text extraction to avoid blocking the event loop
    text = await asyncio.to_thread(extract_pdf_text, file_path)
    if not text:
        logging.warning(f"No text extracted from {pdf_url}")
        await asyncio.to_thread(file_path.unlink, True)  # missing_ok=True
        return

    # Prepare metadata (include original URL and processing time)
    metadata = {
        "source": "PDF",
        "pdf_url": pdf_url,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "file_name": file_path.name
    }
    await upload_to_documents_table(text, metadata, pool)

    # Remove the temporary PDF file after processing
    try:
        await asyncio.to_thread(file_path.unlink)
        logging.info(f"Deleted temporary file {file_path}")
    except Exception as e:
        logging.error(f"Error deleting file {file_path}: {e}")

async def process_pdf_urls_from_txt():
    """Process PDF URLs listed in txt files (e.g. pdf_n8n.txt, pdf_pydantic_ai.txt, etc.)."""
    base_path = Path('/home/ai-agents/post_data')
    pdf_txt_files = [
        "pdf_n8n.txt",
        "pdf_pydantic_ai.txt",
        "pdf_make.txt",
        "pdf_lang_agent.txt",
        "pdf_huggingface_smol.txt",
        "pdf_flowise.txt"
    ]
    
    async def process_pdf_file(pdf_file: str):
        tool_db_name = pdf_file.replace("pdf_", "").replace(".txt", "")
        pool = await create_db_pool(tool_db_name)
        if not pool:
            logging.error(f"Failed to create pool for {tool_db_name}, skipping")
            return
        
        file_path = base_path / pdf_file
        if file_path.exists():
            async with aiofiles.open(file_path, "r") as f:
                content = await f.read()
                urls = [line.strip() for line in content.splitlines() if line.strip()]
            if urls:
                tasks = [process_pdf_url(url, pool) for url in urls]
                await asyncio.gather(*tasks)
            else:
                logging.warning(f"No PDF URLs found in {pdf_file}")
        else:
            logging.error(f"File not found: {file_path}")
        await pool.close()
    
    await asyncio.gather(*(process_pdf_file(file) for file in pdf_txt_files))

async def main():
    global http_client
    http_client = httpx.AsyncClient()
    logging.info("🚀 Starting PDF processing...")
    await process_pdf_urls_from_txt()
    logging.info("✅ All PDF URLs processed and stored in PostgreSQL.")
    await http_client.aclose()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("🚀 Starting PDF processing...")
    asyncio.run(main())
    print("✅ All PDF URLs processed and stored in PostgreSQL.")
