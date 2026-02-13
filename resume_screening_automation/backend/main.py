from fastapi import FastAPI, Depends
from api.jobs import router as jobs_router
from api.screening import router as screening_router
from security import verify_api_key

app = FastAPI(
    title="Resume Screening Backend",
    swagger_ui_parameters={"persistAuthorization": True}
)

# 🔒 Protect all routes with API key
app.include_router(jobs_router, prefix="/jobs", dependencies=[Depends(verify_api_key)])
app.include_router(screening_router, dependencies=[Depends(verify_api_key)])
