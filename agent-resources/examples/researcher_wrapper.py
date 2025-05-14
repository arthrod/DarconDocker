import os
import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import sys
import requests
import re
from typing import List

# Load environment variables
load_dotenv()

# Add the gpt-researcher directory to PYTHONPATH
from md2pdf.core import md2pdf

# Create necessary directories
Path('outputs').mkdir(exist_ok=True)
Path('temp_pdfs').mkdir(exist_ok=True)
Path('source_lists').mkdir(exist_ok=True)

current_dir = Path(__file__).parent.absolute()
gpt_researcher_dir = current_dir / 'gpt_researcher'
sys.path.append(str(gpt_researcher_dir))

# Import from gpt-researcher
from gpt_researcher import GPTResearcher

# Define our own write_md_to_pdf function since we can't import it
async def write_md_to_pdf(text: str, filename: str = "") -> str:
    """Converts Markdown text to a PDF file and returns the file path.

    Args:
        text (str): Markdown text to convert.
        filename (str): Optional filename for the PDF.

    Returns:
        str: The encoded file path of the generated PDF.
    """
    # Create safe filename and ensure temp_pdfs exists
    safe_filename = "".join(x for x in filename if x.isalnum() or x in "._- ")[:60]
    temp_pdfs_dir = Path("temp_pdfs")
    temp_pdfs_dir.mkdir(exist_ok=True)
    file_path = temp_pdfs_dir / f"{safe_filename}.pdf"

    try:
        # Use absolute paths
        css_path = Path("./gpt_researcher/frontend/pdf_styles.css").absolute()
        md2pdf(
            str(file_path),
            md_content=text,
            css_file_path=str(css_path)
        )
        print(f"Report written to {file_path}")
        return file_path
    except Exception as e:
        print(f"Error in converting Markdown to PDF: {e}")
        return ""

# Helper function to extract and save images from the report content
async def extract_and_save_images(report_content: str, report_title: str) -> List[str]:
    """
    Extracts image URLs from the report content, downloads them, and saves them as JPEGs.
    The images are saved in a directory named with the report title and current timestamp.

    Args:
        report_content (str): The content of the report containing image URLs.
        report_title (str): The title of the report for saving images.

    Returns:
        List[str]: A list of paths to the saved images.
    """
    # Extract image URLs using a regex
    image_urls: List[str] = extract_image_urls(report_content)
    saved_image_paths: List[str] = []

    # Create directory for saving images using the report title and timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(x for x in report_title if x.isalnum() or x in "._- ")[:60]
    image_dir = f"./images/{safe_title}_{timestamp}"
    os.makedirs(image_dir, exist_ok=True)
    print(f"Created directory for images: {image_dir}")

    # Download and save each image
    for idx, url in enumerate(image_urls, start=1):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                image_filename = f"{safe_title}_{timestamp}_{idx}.jpeg"
                image_path = os.path.join(image_dir, image_filename)
                with open(image_path, 'wb') as f:
                    f.write(response.content)
                saved_image_paths.append(image_path)
                print(f"Image saved: {image_path}")
            else:
                print(f"Failed to download image from {url} - Status: {response.status_code}")
        except Exception as e:
            print(f"Error downloading image from {url}: {e}")

    print(f"Total images saved: {len(saved_image_paths)}")
    return saved_image_paths

def extract_image_urls(report_content: str) -> List[str]:
    """
    Extracts image URLs from the report content using regex.

    Args:
        report_content (str): The content of the report.

    Returns:
        List[str]: A list of extracted image URLs.
    """
    image_url_pattern = r'(https?:\/\/[^\s]+?\.(?:jpg|jpeg|png|gif|webp))'
    image_urls: List[str] = re.findall(image_url_pattern, report_content)
    unique_image_urls: List[str] = list(set(image_urls))
    print(f"Found {len(unique_image_urls)} unique image URLs.")
    return unique_image_urls

async def process_research_topic(query: str) -> str:
    """Process a single research topic and save as PDF"""
    try:
        print(f"Starting research for: {query}")
        
        # Check for required API keys
        if not os.getenv('TAVILY_API_KEY'):
            print("Warning: TAVILY_API_KEY not found in environment. Web search capabilities will be limited.")
        
        # Initialize researcher
        researcher = GPTResearcher(
            query=query,
            config_path="config.json"  # Use our config with Ollama settings
        )
        
        # Conduct research and get report
        print("Conducting research...")
        await researcher.conduct_research()
        
        # Extract and save URLs from research sources
        if researcher.research_sources:
            urls = set()
            for source in researcher.research_sources:
                if 'url' in source:
                    urls.add(source['url'])
            urls_file = Path('source_lists/site_urls.txt')
            urls_file.parent.mkdir(exist_ok=True)
            existing_urls: set = set()
            if urls_file.exists():
                with open(urls_file, 'r') as f:
                    existing_urls = set(f.read().splitlines())
            with open(urls_file, 'a') as f:
                for url in urls - existing_urls:
                    f.write(url + '\n')
            print(f"Saved {len(urls - existing_urls)} new URLs to {urls_file}")

        print("Writing report...")
        report_md = await researcher.write_report()

        # Extract and save images from the report content
        safe_filename = "".join(x for x in query if x.isalnum() or x in "._- ")[:60]
        images = await extract_and_save_images(report_md, safe_filename)
        if images:
            print(f"Extracted images: {images}")

        # Convert to PDF and save to outputs directory
        print("Converting to PDF...")
        doc_path = os.getenv('DOC_PATH', 'outputs')
        Path(doc_path).mkdir(exist_ok=True)
        pdf_path = await write_md_to_pdf(report_md, filename=safe_filename)
        if pdf_path and Path(pdf_path).exists():
            print(f"Generated PDF: {pdf_path}")
            return str(pdf_path)
        return None
    except Exception as e:
        print(f"Error processing topic '{query}': {e}")
        return None

async def process_research_topics(topics_file: str = "source_lists/research_topics.txt"):
    """Process all research topics from file"""
    try:
        Path("source_lists").mkdir(exist_ok=True)
        Path("temp_pdfs").mkdir(exist_ok=True)
        with open(topics_file, 'r') as f:
            topics: List[str] = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        print(f"Found {len(topics)} topics to process")
        for i, topic in enumerate(topics, 1):
            print(f"\nProcessing topic {i}/{len(topics)}")
            pdf_path = await process_research_topic(topic)
            if pdf_path:
                print(f"Successfully generated PDF: {pdf_path}")
            else:
                print(f"Failed to process topic: {topic}")
    except Exception as e:
        print(f"Error in process_research_topics: {e}")

if __name__ == "__main__":
    test_query = "Give me a very detailed step by step guide to build an AI agent using Pydantic-AI from https://ai.pydantic.dev/?"
    asyncio.run(process_research_topic(test_query))