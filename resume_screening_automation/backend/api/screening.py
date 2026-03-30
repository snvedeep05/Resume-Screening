import csv
import io

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db.session import get_db
from db.models import ResumeRun, ResumeResult, JobConfig, DecisionAudit
from services.screening_pipeline import run_screening_pipeline, process_single_upload
from schemas import DecisionUpdateRequest, BulkDecisionRequest

router = APIRouter(prefix="/screening", tags=["Screening"])


@router.post("/start")
def start_screening(
    background_tasks: BackgroundTasks,
    job_id: int = Form(...),
    batch_size: int = Form(...),
    zip_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    run = ResumeRun(
        job_id=job_id,
        batch_size=batch_size,
        total_resumes=0,
        processed_count=0,
        failed_count=0,
        status="running"
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    zip_bytes = zip_file.file.read()

    background_tasks.add_task(
        run_screening_pipeline,
        run.run_id,
        job_id,
        batch_size,
        zip_file.filename,
        zip_bytes
    )

    return {"run_id": run.run_id, "status": "started"}


@router.post("/upload-single")
def upload_single_resume(
    background_tasks: BackgroundTasks,
    job_id: int = Form(...),
    resume_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload and screen a single resume (PDF or DOCX)."""
    filename = resume_file.filename.lower()
    if not filename.endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    run = ResumeRun(
        job_id=job_id,
        batch_size=1,
        total_resumes=1,
        processed_count=0,
        failed_count=0,
        status="running"
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    file_bytes = resume_file.file.read()

    background_tasks.add_task(
        process_single_upload,
        run.run_id,
        job_id,
        resume_file.filename,
        file_bytes
    )

    return {"run_id": run.run_id, "status": "started"}


@router.get("/runs/{run_id}")
def get_run_status(run_id: int, db: Session = Depends(get_db)):
    run = db.query(ResumeRun).filter_by(run_id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id":          run.run_id,
        "status":          run.status,
        "total_resumes":   run.total_resumes,
        "processed_count": run.processed_count,
        "failed_count":    run.failed_count,
        "started_at":      run.started_at,
        "ended_at":        run.ended_at,
    }


@router.patch("/results/bulk")
def bulk_update_decisions(body: BulkDecisionRequest, db: Session = Depends(get_db)):
    """Update decision for multiple results at once."""
    updated = []
    for result_id in body.result_ids:
        result = db.query(ResumeResult).filter_by(result_id=result_id).first()
        if not result:
            continue

        old_decision = result.decision
        result.decision = body.decision

        db.add(DecisionAudit(
            result_id=result_id,
            old_decision=old_decision,
            new_decision=body.decision,
            reason=body.reason
        ))
        updated.append(result_id)

    db.commit()
    return {"updated": updated, "count": len(updated)}


@router.patch("/results/{result_id}")
def patch_result(result_id: int, body: DecisionUpdateRequest, db: Session = Depends(get_db)):
    result = db.query(ResumeResult).filter_by(result_id=result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    old_decision = result.decision
    result.decision = body.decision

    db.add(DecisionAudit(
        result_id=result_id,
        old_decision=old_decision,
        new_decision=body.decision,
        reason=getattr(body, 'reason', None)
    ))

    db.commit()
    return {"result_id": result_id, "decision": result.decision}


@router.get("/results/{result_id}/history")
def get_decision_history(result_id: int, db: Session = Depends(get_db)):
    """Get decision change history for a result."""
    audits = db.query(DecisionAudit).filter_by(result_id=result_id).order_by(DecisionAudit.changed_at.desc()).all()
    return [
        {
            "audit_id": a.audit_id,
            "old_decision": a.old_decision,
            "new_decision": a.new_decision,
            "changed_at": a.changed_at,
            "reason": a.reason
        }
        for a in audits
    ]


@router.get("/results/job/{job_id}")
def get_results(
    job_id: int,
    limit: int = 500,
    offset: int = 0,
    search: str = None,
    decision: str = None,
    min_score: int = None,
    max_score: int = None,
    db: Session = Depends(get_db)
):
    job = db.query(JobConfig).filter(JobConfig.job_id == job_id).first()
    if not job:
        return []

    query = db.query(ResumeResult).filter(ResumeResult.job_id == job_id)

    if decision:
        query = query.filter(ResumeResult.decision == decision)
    if min_score is not None:
        query = query.filter(ResumeResult.score >= min_score)
    if max_score is not None:
        query = query.filter(ResumeResult.score <= max_score)
    if search:
        search_lower = f"%{search.lower()}%"
        query = query.filter(
            ResumeResult.extracted_data['personal_details']['full_name'].astext.ilike(search_lower) |
            ResumeResult.extracted_data['personal_details']['email'].astext.ilike(search_lower)
        )

    results = query.order_by(ResumeResult.processed_at.desc()).offset(offset).limit(limit).all()

    output = []
    for r in results:
        if r.extracted_data and "personal_details" in r.extracted_data:
            pd_data = r.extracted_data.get("personal_details", {})
            output.append({
                "result_id": r.result_id,
                "candidate_id": r.candidate_id,
                "full_name": pd_data.get("full_name"),
                "email": pd_data.get("email"),
                "phone": pd_data.get("phone"),
                "job_title": job.job_title,
                "passed_out_year": r.passed_out_year,
                "score": r.score,
                "decision": r.decision,
                "decision_reason": r.decision_reason,
                "processed_at": r.processed_at
            })

    return output


@router.get("/results/job/{job_id}/export")
def export_results_csv(
    job_id: int,
    decision: str = None,
    min_score: int = None,
    db: Session = Depends(get_db)
):
    """Export screening results as CSV."""
    job = db.query(JobConfig).filter(JobConfig.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    query = db.query(ResumeResult).filter(ResumeResult.job_id == job_id)
    if decision:
        query = query.filter(ResumeResult.decision == decision)
    if min_score is not None:
        query = query.filter(ResumeResult.score >= min_score)

    results = query.order_by(ResumeResult.score.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Phone", "Score", "Decision", "Reason", "Passed Out Year", "Processed At"])

    for r in results:
        if r.extracted_data and "personal_details" in r.extracted_data:
            pd = r.extracted_data.get("personal_details", {})
            writer.writerow([
                pd.get("full_name", ""),
                pd.get("email", ""),
                pd.get("phone", ""),
                r.score,
                r.decision,
                r.decision_reason,
                r.passed_out_year,
                r.processed_at
            ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=results_job_{job_id}.csv"}
    )
