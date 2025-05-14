from utils import *
import streamlit as st
import streamlit.components.v1 as components

def main():
    st.title("🖥️ Theia IDE")
    components.iframe(
        "http://localhost:3001/", height=700, width=1000, scrolling=False
    )

if __name__ == "__main__":
    main()