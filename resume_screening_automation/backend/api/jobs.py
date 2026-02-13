from fastapi import APIRouter
from db.session import SessionLocal
from db.models import JobConfig
from services.ai_service import generate_job_config
from fastapi import HTTPException
router = APIRouter()

@router.post("")
def create_job(payload: dict):
    db = SessionLocal()
    try:
        job = JobConfig(
            job_title=payload["job_title"],
            job_config=payload.get("job_config", {})
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return {"job_id": job.job_id}
    finally:
        db.close()


@router.get("")
def list_jobs():
    db = SessionLocal()
    try:
        jobs = db.query(JobConfig).all()
        return [
            {
                "job_id": j.job_id,
                "job_title": j.job_title
            }
            for j in jobs
        ]
    finally:
        db.close()


@router.post("/ai-generate")
def ai_generate_job_config(payload: dict):
    job_description = payload.get("job_description")

    if not job_description:
        raise HTTPException(status_code=400, detail="job_description is required")

    try:
        job_config = generate_job_config(job_description)
        return {"job_config": job_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
