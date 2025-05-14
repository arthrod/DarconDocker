from utils import *
import streamlit as st
import streamlit.components.v1 as components

def main():
    st.title("🎓 Get your research done with GPT Researcher")
    components.iframe(
        "http://localhost:8002/", height=700, width=1000, scrolling=False
    )

if __name__ == "__main__":
    main()