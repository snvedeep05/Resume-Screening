from fastapi import FastAPI
from resume_screening_automation.backend.api.jobs import router as jobs_router
from resume_screening_automation.backend.api.screening import router as screening_router

app = FastAPI(title="Resume Screening Backend")

app.include_router(jobs_router, prefix="/jobs")


app.include_router(screening_router)
