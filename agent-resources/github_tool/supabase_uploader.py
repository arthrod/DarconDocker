import streamlit as st
from supa_github import process_and_upload_repo

st.title("GitHub Repo → Supabase Uploader")
st.markdown(
    "Paste a GitHub repository URL below. The tool will clone it, process the files, generate embeddings, and upload to Supabase."
)

github_url = st.text_input("GitHub Repository URL", "")

if st.button("Process and Upload Repo"):
    if github_url.strip():
        with st.spinner("Processing and uploading repo..."):
            success = process_and_upload_repo(github_url.strip())
        if success:
            st.success("Repository processed and uploaded successfully!")
        else:
            st.error("Failed to process and upload the repository.")
    else:
        st.warning("Please enter a valid GitHub repository URL.")
