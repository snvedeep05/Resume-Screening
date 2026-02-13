import requests
import streamlit as st

BACKEND_URL = st.secrets["BACKEND_URL"]
API_KEY = st.secrets["API_KEY"]  # 🔐 read from Streamlit secrets


def get_headers():
    """Return headers with API key for secure backend access."""
    return {
        "x-api-key": API_KEY
    }


def create_job(job_title, job_config):
    response = requests.post(
        f"{BACKEND_URL}/jobs",
        json={
            "job_title": job_title,
            "job_config": job_config
        },
        headers=get_headers()  # 🔐 added
    )
    response.raise_for_status()
    return response.json()


def get_jobs():
    response = requests.get(
        f"{BACKEND_URL}/jobs",
        headers=get_headers()  # 🔐 added
    )
    response.raise_for_status()
    return response.json()


def generate_job_config_ai(job_description):
    response = requests.post(
        f"{BACKEND_URL}/jobs/ai-generate",
        json={"job_description": job_description},
        headers=get_headers()  # 🔐 added
    )
    response.raise_for_status()
    return response.json()["job_config"]
