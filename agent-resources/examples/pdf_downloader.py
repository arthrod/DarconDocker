#!/usr/bin/env python3
import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define the path to the PDF data file (where PDF URLs are stored)
PDF_DATA_FILE = Path("source_lists/pdf_data.txt")
# Ensure the output directory exists
TEMP_PDFS_DIR = Path("temp_pdfs")
TEMP_PDFS_DIR.mkdir(exist_ok=True)

def send_telegram_alert(message: str):
    """Send a Telegram alert using the Bot API."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("Telegram credentials not configured")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print("Telegram alert sent.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def download_pdf(url: str) -> bool:
    """Download a PDF from the given URL and save it in the temp_pdfs folder.
    
    Args:
        url (str): The URL of the PDF.
    
    Returns:
        bool: True if download succeeded, False otherwise.
    """
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            # Generate a filename from the URL's last segment.
            filename = url.split("/")[-1]
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
            output_path = TEMP_PDFS_DIR / filename
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"Downloaded PDF: {output_path}")
            return True
        else:
            print(f"Failed to download PDF from {url} - Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error downloading PDF from {url}: {e}")
        return False

def process_pdf_data_file():
    """Read PDF URLs from pdf_data.txt, download each PDF, update the file,
    and send a Telegram alert summarizing the results."""
    if not PDF_DATA_FILE.exists():
        print(f"{PDF_DATA_FILE} does not exist. Nothing to download.")
        return
    
    with open(PDF_DATA_FILE, "r") as f:
        lines = f.readlines()
    
    # Filter out empty lines and comments
    urls = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    
    if not urls:
        print("No PDF URLs found in pdf_data.txt.")
        return
    
    downloaded_urls = []
    for url in urls:
        if download_pdf(url):
            downloaded_urls.append(url)
    
    # Remove successfully downloaded URLs from the file
    if downloaded_urls:
        remaining_urls = [url for url in urls if url not in downloaded_urls]
        with open(PDF_DATA_FILE, "w") as f:
            for url in remaining_urls:
                f.write(url + "\n")
        print(f"Updated {PDF_DATA_FILE}: {len(remaining_urls)} URLs remain.")
        send_telegram_alert(f"PDF Downloader: {len(downloaded_urls)} PDF(s) downloaded successfully. {len(remaining_urls)} pending.")
    else:
        print("No PDFs were downloaded successfully.")
        send_telegram_alert("PDF Downloader: No PDFs were downloaded successfully.")

if __name__ == "__main__":
    # For testing, you can run the downloader once:
    process_pdf_data_file()
    
    # Alternatively, run continuously (uncomment below)
    # while True:
    #     process_pdf_data_file()
    #     time.sleep(60)
