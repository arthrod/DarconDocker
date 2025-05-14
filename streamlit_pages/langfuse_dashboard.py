"""
Langfuse Embedded Dashboard for Darcon

Simple iframe embedding of the Langfuse UI.
"""
import os
import streamlit as st

# Define the default Langfuse URL
LANGFUSE_URL = os.environ.get("LANGFUSE_HOST", "http://10.147.20.5:8002")

def main():
    # Title is handled by the main UI file
    
    # Add minimal CSS for the iframe
    st.markdown("""
    <style>
    .langfuse-iframe {
        width: 100%;
        height: 900px;
        border: none;
        border-radius: 4px;
        margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Display the iframe directly
    st.markdown(f"""
    <iframe 
        src="{LANGFUSE_URL}" 
        class="langfuse-iframe"
        allow="fullscreen"
        title="Langfuse Dashboard"
        id="langfuse-dashboard-iframe"
        name="langfuse-dashboard-iframe">
    </iframe>
    """, unsafe_allow_html=True)

def langfuse_dashboard_tab():
    """Main entry point for the Langfuse Dashboard tab in the Streamlit UI"""
    main()

if __name__ == "__main__":
    main()
