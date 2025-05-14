import os
from dotenv import load_dotenv
import streamlit as st

def load_env():
    """Load environment variables from .env file"""
    load_dotenv()
    
    # Ollama settings
    st.session_state.ollama_config = {
        'api_url': os.getenv('OLLAMA_API_URL', 'http://10.147.20.20:11434'),
        'default_model': os.getenv('OLLAMA_DEFAULT_MODEL', 'llama3.2:3b'),
        'timeout': int(os.getenv('OLLAMA_TIMEOUT', 30))
    }
    
    # Email settings
    st.session_state.email_config = {
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', 587)),
        'sender_email': os.getenv('SENDER_EMAIL'),
        'smtp_password': os.getenv('SMTP_PASSWORD')
    }
    
    # App settings
    st.session_state.app_config = {
        'debug': os.getenv('DEBUG', 'False').lower() == 'true',
        'allowed_file_types': os.getenv('ALLOWED_FILE_TYPES', 'xlsx,xls,jpg,jpeg,png').split(','),
        'max_upload_size': int(os.getenv('MAX_UPLOAD_SIZE', 10))
    }
