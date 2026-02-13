from fastapi import FastAPI
from backend.api.jobs import router as jobs_router
from backend.api.screening import router as screening_router

app = FastAPI(title="Resume Screening Backend")

app.include_router(jobs_router, prefix="/jobs")


app.include_router(screening_router)