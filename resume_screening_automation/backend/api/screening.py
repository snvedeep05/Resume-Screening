import os
import zipfile
import tempfile
import hashlib
from datetime import datetime
from email_validator import validate_email, EmailNotValidError


def _normalize_email(extracted_data: dict) -> dict:
    """Set personal_details.email to None if the AI returned a non-email string."""
    personal = extracted_data.get("personal_details")
    if not isinstance(personal, dict):
        return extracted_data
    raw = str(personal.get("email") or "").strip()
    try:
        personal["email"] = validate_email(raw, check_deliverability=False).email
    except EmailNotValidError:
        personal["email"] = None
    return extracted_data

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from groq import RateLimitError

from db.session import SessionLocal
from db.models import ResumeRun, ResumeFile, ResumeResult, JobConfig
from services.resume_processor import process_single_resume
from services.scoring_engine import score_resume

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

            rate_limit_hit = False

            for i in range(0, len(resume_files), batch_size):
                batch = resume_files[i:i + batch_size]
                batch_no = (i // batch_size) + 1
                total_batches = (len(resume_files) + batch_size - 1) // batch_size

                print(f"[RUN {run_id}] Batch {batch_no}/{total_batches} started")

                for idx, resume_path in enumerate(batch, start=1):
                    overall_index = i + idx
                    file_name = os.path.basename(resume_path)

                    if rate_limit_hit:
                        resume_id = get_or_create_resume(db, resume_path)
                        existing_result = db.query(ResumeResult).filter(
                            ResumeResult.resume_id == resume_id,
                            ResumeResult.job_id == job_id,
                            ResumeResult.extracted_data.isnot(None)
                        ).first()

                        if existing_result:
                            print(f"[RUN {run_id}] Rate limit hit but reusing existing result → {file_name}")
                            existing_result.run_id = run_id
                            existing_result.processed_at = datetime.utcnow()
                            existing_result.ai_status = "reused"
                            run.processed_count += 1
                        else:
                            print(f"[RUN {run_id}] ⏳ Skipping (rate limit already hit) → {file_name}")
                            run.failed_count += 1
                            db.add(ResumeResult(
                                run_id=run_id,
                                resume_id=resume_id,
                                job_id=job_id,
                                ai_status="rate_limited",
                                error_message="Groq rate limit hit earlier in this run"
                            ))
                        db.commit()
                        continue

                    print(
                        f"[RUN {run_id}] Processing resume "
                        f"{overall_index}/{len(resume_files)} → {file_name}"
                    )

                    resume_id = None
                    try:
                        resume_id = get_or_create_resume(db, resume_path)

                        if resume_id is None:
                            print(f"[RUN {run_id}] ❌ Failed to create resume record → {file_name}")
                            run.failed_count += 1
                            continue  
                        # 🔎 Check if already processed for this job (skip failed rows)
                        existing_result = db.query(ResumeResult).filter(
                            ResumeResult.resume_id == resume_id,
                            ResumeResult.job_id == job_id,
                            ResumeResult.extracted_data.isnot(None)
                        ).first()

                        if existing_result:
                            print(f"[RUN {run_id}] Reusing existing result for job")

                            existing_result.run_id = run_id
                            existing_result.processed_at = datetime.utcnow()
                            existing_result.ai_status = "reused"

                            # Backfill passed_out_year if missing but present in stored data
                            if existing_result.passed_out_year is None and existing_result.extracted_data:
                                raw_year = existing_result.extracted_data.get("passed_out_year")
                                existing_result.passed_out_year = int(raw_year) if raw_year is not None else None

                        else:
                            # 🔎 Check if extracted before (for other jobs)
                            # Only reuse if extracted_data is not None (skip failed results)
                            previous_any = db.query(ResumeResult).filter(
                                ResumeResult.resume_id == resume_id,
                                ResumeResult.extracted_data.isnot(None)
                            ).first()

                            if previous_any:
                                print(f"[RUN {run_id}] Reusing extracted data, re-scoring")

                                extracted_data = previous_any.extracted_data

                            else:
                                # 🚀 New resume → Call AI
                                print(f"[RUN {run_id}] Calling AI extraction")

                                extracted = process_single_resume(resume_path)
                                extracted_data = extracted["extracted_data"]

                            extracted_data = _normalize_email(extracted_data)

                            # Score for this job
                            score, reason, disqualified = score_resume(
                                job_config,
                                extracted_data
                            )

                            decision = "rejected" if disqualified or score < 60 else "shortlisted"

                            raw_year = extracted_data.get("passed_out_year")
                            if raw_year is None and previous_any is not None:
                                raw_year = previous_any.passed_out_year
                            passed_out_year = int(raw_year) if raw_year is not None else None

                            db.add(
                                ResumeResult(
                                    run_id=run_id,
                                    resume_id=resume_id,
                                    job_id=job_id,
                                    extracted_data=extracted_data,
                                    score=score,
                                    decision=decision,
                                    decision_reason=reason,
                                    passed_out_year=passed_out_year,
                                    ai_status="success"
                                )
                            )

                        run.processed_count += 1

                    except RateLimitError as e:
                        print(f"[RUN {run_id}] ⏳ Groq rate limit hit: {file_name}")
                        rate_limit_hit = True
                        db.rollback()
                        run.failed_count += 1
                        if resume_id:
                            try:
                                db.add(ResumeResult(
                                    run_id=run_id,
                                    resume_id=resume_id,
                                    job_id=job_id,
                                    ai_status="rate_limited",
                                    error_message=str(e)
                                ))
                                db.commit()
                            except Exception:
                                db.rollback()
                        continue

                    except Exception as e:
                        print(f"[RUN {run_id}] ❌ Error processing {file_name}: {e}")
                        db.rollback()
                        run.failed_count += 1
                        if resume_id:
                            try:
                                db.add(ResumeResult(
                                    run_id=run_id,
                                    resume_id=resume_id,
                                    job_id=job_id,
                                    ai_status="failed",
                                    error_message=str(e)
                                ))
                                db.commit()
                            except Exception:
                                db.rollback()
                        continue

                    finally:
                        try:
                            db.commit()
                        except Exception:
                            db.rollback()
                        

        run.ended_at = datetime.utcnow()
        run.status = "completed"
        db.commit()
        print(f"[RUN {run_id}] Completed")

    finally:
        try:
            stale = db.query(ResumeRun).filter_by(run_id=run_id).first()
            if stale and stale.status == "running":
                stale.status = "crashed"
                stale.ended_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        db.close()


@router.get("/runs/{run_id}")
def get_run_status(run_id: int):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@router.patch("/results/{result_id}")
def patch_result(result_id: int, body: dict):
    db = SessionLocal()
    try:
        result = db.query(ResumeResult).filter_by(result_id=result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result not found")
        if "decision" in body:
            val = body["decision"]
            result.decision = val if val in ("shortlisted", "rejected") else result.decision
        db.commit()
        return {"result_id": result_id, "decision": result.decision}
    finally:
        db.close()


@router.get("/results/{job_id}")
def get_results(job_id: int, limit: int = 500, offset: int = 0):
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
        ).order_by(ResumeResult.processed_at.desc()).offset(offset).limit(limit).all()

        output = []

        for r in results:
            if r.extracted_data and "personal_details" in r.extracted_data:
                pd_data = r.extracted_data.get("personal_details", {})

                output.append({
                    "result_id": r.result_id,
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

    finally:
        db.close()

