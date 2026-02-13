import requests
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL")

def create_job(job_title, job_config):
    response = requests.post(
        f"{BACKEND_URL}/jobs",
        json={
            "job_title": job_title,
            "job_config": job_config
        }
    )
    response.raise_for_status()
    return response.json()


def get_jobs():
    response = requests.get(f"{BACKEND_URL}/jobs")
    response.raise_for_status()
    return response.json()

def generate_job_config_ai(job_description):
    response = requests.post(
        f"{BACKEND_URL}/jobs/ai-generate",
        json={"job_description": job_description}
    )
    response.raise_for_status()
    return response.json()["job_config"]
