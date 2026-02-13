import os
import zipfile
import tempfile
import hashlib

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks

from backend.db.session import SessionLocal
from backend.db.models import ResumeRun, ResumeFile, ResumeResult, JobConfig
from backend.services.resume_processor import process_single_resume
from backend.services.scoring_engine import score_resume

router = APIRouter(prefix="/screening", tags=["Screening"])


def get_or_create_resume(db, resume_path: str) -> int:
    with open(resume_path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()

    file_name = os.path.basename(resume_path)

    resume = db.query(ResumeFile).filter_by(file_hash=file_hash).first()
    if resume:
        return resume.resume_id

    resume = ResumeFile(
        file_name=file_name,
        file_hash=file_hash,
        file_path=resume_path
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return resume.resume_id


@router.post("/start")
def start_screening(
    background_tasks: BackgroundTasks,
    job_id: int = Form(...),
    batch_size: int = Form(...),
    zip_file: UploadFile = File(...)
):
    db = SessionLocal()
    try:
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

        # 🔥 IMPORTANT FIX
        zip_bytes = zip_file.file.read()

        background_tasks.add_task(
            process_zip_and_screen,
            run.run_id,
            job_id,
            batch_size,
            zip_file.filename,
            zip_bytes
        )

        return {"run_id": run.run_id, "status": "started"}

    finally:
        db.close()


def process_zip_and_screen(
    run_id: int,
    job_id: int,
    batch_size: int,
    zip_filename: str,
    zip_bytes: bytes
):
    db = SessionLocal()
    try:
        run = db.query(ResumeRun).filter_by(run_id=run_id).first()
        job = db.query(JobConfig).filter_by(job_id=job_id).first()

        if not run or not job:
            return

        job_config = job.job_config

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, zip_filename)

            with open(zip_path, "wb") as f:
                f.write(zip_bytes)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            resume_files = []
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    if file.lower().endswith((".pdf", ".docx")):
                        resume_files.append(os.path.join(root, file))

            run.total_resumes = len(resume_files)
            db.commit()

            print(f"[RUN {run_id}] Total resumes found: {len(resume_files)}")

            for i in range(0, len(resume_files), batch_size):
                batch = resume_files[i:i + batch_size]
                batch_no = (i // batch_size) + 1
                total_batches = (len(resume_files) + batch_size - 1) // batch_size

                print(f"[RUN {run_id}] Batch {batch_no}/{total_batches} started")

                for idx, resume_path in enumerate(batch, start=1):
                    overall_index = i + idx
                    file_name = os.path.basename(resume_path)

                    print(
                        f"[RUN {run_id}] Processing resume "
                        f"{overall_index}/{len(resume_files)} → {file_name}"
                    )

                    try:
                        resume_id = get_or_create_resume(db, resume_path)

                        # 🔎 Check if already processed for this job
                        existing_result = db.query(ResumeResult).filter_by(
                            resume_id=resume_id,
                            job_id=job_id
                        ).first()

                        if existing_result:
                            print(f"[RUN {run_id}] Reusing existing result for job")

                            db.add(
                                ResumeResult(
                                    run_id=run_id,
                                    resume_id=resume_id,
                                    job_id=job_id,
                                    extracted_data=existing_result.extracted_data,
                                    score=existing_result.score,
                                    decision=existing_result.decision,
                                    decision_reason=existing_result.decision_reason,
                                    ai_status="reused"
                                )
                            )

                        else:
                            # 🔎 Check if extracted before (for other jobs)
                            previous_any = db.query(ResumeResult).filter_by(
                                resume_id=resume_id
                            ).first()

                            if previous_any:
                                print(f"[RUN {run_id}] Reusing extracted data, re-scoring")

                                extracted_data = previous_any.extracted_data

                            else:
                                # 🚀 New resume → Call AI
                                print(f"[RUN {run_id}] Calling AI extraction")

                                extracted = process_single_resume(resume_path)
                                extracted_data = extracted["extracted_data"]

                            # Score for this job
                            score, reason = score_resume(
                                job_config,
                                extracted_data
                            )

                            decision = "shortlisted" if score >= 60 else "rejected"

                            db.add(
                                ResumeResult(
                                    run_id=run_id,
                                    resume_id=resume_id,
                                    job_id=job_id,
                                    extracted_data=extracted_data,
                                    score=score,
                                    decision=decision,
                                    decision_reason=reason,
                                    ai_status="success"
                                )
                            )

                        run.processed_count += 1

                    except Exception as e:
                        db.add(
                            ResumeResult(
                                run_id=run_id,
                                resume_id=None,
                                job_id=job_id,
                                score=0,
                                decision="failed",
                                ai_status="failed",
                                error_message=str(e)
                            )
                        )
                        run.failed_count += 1

                    finally:
                        db.commit()

        run.status = "completed"
        db.commit()
        print(f"[RUN {run_id}] Completed")

    finally:
        db.close()


@router.get("/results/{job_id}")
def get_results(job_id: int):
    print("Fetching results from DB")
    db = SessionLocal()
    try:
        # Get job title once
        job = db.query(JobConfig).filter(
            JobConfig.job_id == job_id
        ).first()

        if not job:
            return []

        results = db.query(ResumeResult).filter(
            ResumeResult.job_id == job_id
        ).all()

        output = []

        for r in results:
            if r.extracted_data and "personal_details" in r.extracted_data:
                pd_data = r.extracted_data.get("personal_details", {})

                output.append({
                    "full_name": pd_data.get("full_name"),
                    "email": pd_data.get("email"),
                    "phone": pd_data.get("phone"),
                    "job_title": job.job_title,   # ✅ NEW COLUMN
                    "score": r.score,
                    "decision": r.decision,
                    "decision_reason": r.decision_reason,
                    "processed_at": r.processed_at
                })

        return output

    finally:
        db.close()

