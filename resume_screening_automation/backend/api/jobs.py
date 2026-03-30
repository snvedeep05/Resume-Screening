from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import JobConfig
from services.ai_service import generate_job_config
from schemas import JobCreateRequest, JobUpdateRequest, AIGenerateRequest

router = APIRouter()

@router.post("")
def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)):
    job = JobConfig(
        job_title=payload.job_title,
        job_config=payload.job_config
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.job_id}


@router.get("")
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(JobConfig).filter(JobConfig.is_active == True).all()
    return [
        {
            "job_id": j.job_id,
            "job_title": j.job_title,
            "version": j.version
        }
        for j in jobs
    ]


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobConfig).filter(JobConfig.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "job_title": job.job_title,
        "job_config": job.job_config,
        "version": job.version,
        "is_active": job.is_active
    }


@router.patch("/{job_id}")
def update_job(job_id: int, payload: JobUpdateRequest, db: Session = Depends(get_db)):
    old_job = db.query(JobConfig).filter(
        JobConfig.job_id == job_id,
        JobConfig.is_active == True
    ).first()

    if not old_job:
        raise HTTPException(status_code=404, detail="Job not found or already inactive")

    # Deactivate old + create new in a single atomic transaction
    old_job.is_active = False
    new_job = JobConfig(
        job_title=payload.job_title if payload.job_title is not None else old_job.job_title,
        job_config=payload.job_config if payload.job_config is not None else old_job.job_config,
        version=old_job.version + 1,
        is_active=True
    )
    db.add(new_job)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update job config")
    db.refresh(new_job)

    return {
        "job_id": new_job.job_id,
        "version": new_job.version,
        "job_title": new_job.job_title
    }


@router.post("/ai-generate")
def ai_generate_job_config(payload: AIGenerateRequest):
    try:
        job_config = generate_job_config(payload.job_description)
        return {"job_config": job_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
