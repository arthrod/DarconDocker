from utils import *
import streamlit as st
import streamlit.components.v1 as components
import requests
import time

def is_server_ready(url):
    try:
        response = requests.get(url)
        return response.status_code == 200
    except:
        return False

def main():
    st.title("👁️ Edit your app Live with Onlook")
    
    # Wait for server to be ready
    server_url = "http://localhost:5173/"
    if not is_server_ready(server_url):
        st.warning("Waiting for Onlook studio to start...")
        time.sleep(2)
        st.rerun()
        
    components.iframe(
        server_url,
        height=700,
        width=1000,
        scrolling=True
    )

if __name__ == "__main__":
    main()