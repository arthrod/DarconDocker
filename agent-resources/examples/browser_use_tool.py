from utils import *
import streamlit as st
import streamlit.components.v1 as components

def main():
    st.title("Browser Use Web UI")
    st.markdown("Access the Browser Use Web UI below.")
    # Directly point to the service on port 7789
    components.iframe(
        "http://localhost:7789/", height=700, width=1000, scrolling=False
    )

if __name__ == "__main__":
    main()
