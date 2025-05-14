from utils import *
import streamlit as st
import streamlit.components.v1 as components

def main():
    st.title("🖼️ Image Generation with Fooocus")
    components.iframe(
        "http://localhost:7866/", height=700, width=1000, scrolling=False
    )

if __name__ == "__main__":
    main()