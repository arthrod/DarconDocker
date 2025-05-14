import os
from dotenv import load_dotenv
load_dotenv()

import asyncio
from telegram.ext import Application, CommandHandler
from datetime import datetime
from pathlib import Path
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Set base directory to the directory of this script (absolute path)
BASE_DIR = Path(__file__).parent.resolve()

# Define the source_lists directory relative to BASE_DIR.
SOURCE_LISTS_DIR = BASE_DIR / "source_lists"
SOURCE_LISTS_DIR.mkdir(exist_ok=True)

# Define file paths for all our lists inside source_lists.
FILES = {
    "YOUTUBE": SOURCE_LISTS_DIR / "youtube.txt",
    "GITHUB": SOURCE_LISTS_DIR / "github.txt",
    "URL": SOURCE_LISTS_DIR / "site_urls.txt",
    "TOPICS": SOURCE_LISTS_DIR / "research_topics.txt",
    "PDF": SOURCE_LISTS_DIR / "pdf_data.txt"
}
# No explicit creation of the individual files is needed; they'll be created in append mode if missing.

class ResearchBot:
    def __init__(self):
        self.files = FILES

    async def start(self, update, context):
        if str(update.message.chat_id) != AUTHORIZED_CHAT_ID:
            return
        await update.message.reply_text(
            "👋 Hello! I can help you with:\n"
            "/addurl [TYPE] [URL] - Add URL (YOUTUBE/GITHUB/URL) to the list\n"
            "/addpdf [PDF_URL] - Add a direct PDF URL to the list\n"
            "/status - Check system status\n"
            "/addtopic [research topic] - Add research topic"
        )

    async def add_url(self, update, context):
        if str(update.message.chat_id) != AUTHORIZED_CHAT_ID:
            return
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /addurl [TYPE] [URL]")
            return

        url_type = context.args[0].upper()
        url = context.args[1]

        if url_type not in ["YOUTUBE", "GITHUB", "URL"]:
            await update.message.reply_text("Type must be YOUTUBE, GITHUB, or URL")
            return

        target_file = self.files[url_type]
        # Debug: print the absolute path being used.
        print(f"Appending URL to: {target_file.resolve()}")
        if target_file.exists():
            with open(target_file, "r") as f:
                if url in f.read():
                    await update.message.reply_text("❌ URL already exists.")
                    return

        with open(target_file, "a") as f:
            f.write(url + "\n")
        await update.message.reply_text(f"✅ Added {url_type} URL: {url}")

    async def add_pdf(self, update, context):
        """Adds a PDF URL to the PDF file for later downloading."""
        if str(update.message.chat_id) != AUTHORIZED_CHAT_ID:
            return
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /addpdf [PDF_URL]")
            return
        pdf_url = context.args[0]
        if not pdf_url.lower().endswith(".pdf"):
            await update.message.reply_text("The URL does not appear to be a direct PDF link.")
            return
        target_file = self.files["PDF"]
        print(f"Appending PDF URL to: {target_file.resolve()}")
        if target_file.exists():
            with open(target_file, "r") as f:
                existing_urls = set(line.strip() for line in f if line.strip())
            if pdf_url in existing_urls:
                await update.message.reply_text("❌ PDF URL already exists.")
                return
        with open(target_file, "a") as f:
            f.write(pdf_url + "\n")
        await update.message.reply_text(f"✅ Added PDF URL: {pdf_url}")

    async def status(self, update, context):
        """Check system status by reporting pending items from each list."""
        if str(update.message.chat_id) != AUTHORIZED_CHAT_ID:
            return

        status_lines = ["🔍 System Status:"]
        for key, file_path in self.files.items():
            if file_path.exists():
                with open(file_path, "r") as f:
                    count = sum(1 for line in f if line.strip() and not line.startswith("#"))
                status_lines.append(f"{key}: {count} pending items")
            else:
                status_lines.append(f"{key}: File not found")
        await update.message.reply_text("\n".join(status_lines))

    async def add_topic(self, update, context):
        if str(update.message.chat_id) != AUTHORIZED_CHAT_ID:
            return
        if not context.args:
            await update.message.reply_text("Usage: /addtopic [research topic]")
            return

        topic = " ".join(context.args).strip()
        target_file = self.files["TOPICS"]
        
        # Add comparative debugging
        print("\nPath Resolution Debug:")
        print(f"Current working directory: {os.getcwd()}")
        print(f"BASE_DIR: {BASE_DIR}")
        print(f"SOURCE_LISTS_DIR: {SOURCE_LISTS_DIR}")
        print(f"Topic file path (from FILES): {self.files['TOPICS']}")
        print(f"Topic file absolute path: {target_file.absolute()}")
        print(f"Topic file resolved path: {target_file.resolve()}")
        print(f"Source lists dir exists: {SOURCE_LISTS_DIR.exists()}")
        
        try:
            # Ensure directory exists
            SOURCE_LISTS_DIR.mkdir(exist_ok=True)
            # Add more detailed debugging
            print(f"Debug info:")
            print(f"Target file path: {target_file.resolve()}")
            print(f"File exists before write: {target_file.exists()}")
            print(f"File permissions: {oct(os.stat(target_file).st_mode)[-3:]}" if target_file.exists() else "File doesn't exist")
            
            if target_file.exists():
                with open(target_file, "r") as f:
                    content = f.read()
                    if topic in content:
                        await update.message.reply_text("❌ Topic already exists.")
                        return
            
            with open(target_file, "a") as f:
                f.write(topic + "\n")
            print(f"Debug: Write operation completed")
            await update.message.reply_text(f"✅ Topic added: {topic}")
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            await update.message.reply_text(f"❌ Error adding topic: {str(e)}")

def main():
    bot = ResearchBot()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("addurl", bot.add_url))
    application.add_handler(CommandHandler("addpdf", bot.add_pdf))
    application.add_handler(CommandHandler("status", bot.status))
    application.add_handler(CommandHandler("addtopic", bot.add_topic))

    application.run_polling()

if __name__ == "__main__":
    main()
