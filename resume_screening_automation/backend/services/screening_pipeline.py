"""
Screening pipeline — orchestrates resume extraction, scoring, and persistence.
Broken out of api/screening.py for clarity and testability.
"""
import os
import zipfile
import tempfile
import hashlib
from datetime import datetime

from groq import RateLimitError

from db.session import SessionLocal
from db.models import ResumeRun, ResumeFile, ResumeResult, JobConfig
from services.resume_processor import process_single_resume
from services.scoring_engine import score_resume, get_shortlist_threshold
from services.candidate_dedup import get_or_create_candidate


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_or_create_resume(db, file_path: str) -> int:
    """Get existing resume by hash or create new entry."""
    file_hash = compute_file_hash(file_path)
    file_name = os.path.basename(file_path)

    existing = db.query(ResumeFile).filter_by(file_hash=file_hash).first()
    if existing:
        return existing.resume_id

    resume = ResumeFile(
        file_name=file_name,
        file_hash=file_hash,
        file_path=file_name  # Store filename only, not temp path
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume.resume_id


def extract_resume_files(zip_bytes: bytes, zip_filename: str, tmpdir: str) -> list[str]:
    """Extract zip and return list of resume file paths (.pdf, .docx)."""
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
    return resume_files


def find_existing_result(db, resume_id: int, job_id: int):
    """Check if this resume was already successfully processed for this job."""
    return db.query(ResumeResult).filter(
        ResumeResult.resume_id == resume_id,
        ResumeResult.job_id == job_id,
        ResumeResult.extracted_data.isnot(None)
    ).first()


def find_any_extracted_data(db, resume_id: int):
    """Check if this resume was extracted for any job before."""
    result = db.query(ResumeResult).filter(
        ResumeResult.resume_id == resume_id,
        ResumeResult.extracted_data.isnot(None)
    ).first()
    return result.extracted_data if result else None


def normalize_email(extracted_data: dict) -> dict:
    """Validate and normalize email in extracted data."""
    from email_validator import validate_email, EmailNotValidError
    personal = extracted_data.get("personal_details")
    if not isinstance(personal, dict):
        return extracted_data
    raw = str(personal.get("email") or "").strip()
    try:
        personal["email"] = validate_email(raw, check_deliverability=False).email
    except EmailNotValidError:
        personal["email"] = None
    return extracted_data


def process_single(db, run_id: int, resume_path: str, job_id: int, job_config: dict) -> str:
    """
    Process a single resume: extract, score, persist.
    Returns: "success", "reused", "rate_limited", or "failed"
    """
    resume_id = get_or_create_resume(db, resume_path)
    file_name = os.path.basename(resume_path)

    # Check if already processed for this job
    existing = find_existing_result(db, resume_id, job_id)
    if existing:
        existing.run_id = run_id
        existing.processed_at = datetime.utcnow()
        existing.ai_status = "reused"
        if existing.passed_out_year is None and existing.extracted_data:
            raw_year = existing.extracted_data.get("passed_out_year")
            existing.passed_out_year = int(raw_year) if raw_year is not None else None
        db.commit()
        return "reused"

    # Check if extracted for another job (reuse extraction, re-score)
    previous_data = find_any_extracted_data(db, resume_id)
    if previous_data:
        extracted_data = previous_data
    else:
        extracted = process_single_resume(resume_path)
        extracted_data = extracted["extracted_data"]

    extracted_data = normalize_email(extracted_data)

    score, reason = score_resume(job_config, extracted_data)
    threshold = get_shortlist_threshold(job_config)
    decision = "shortlisted" if score >= threshold else "rejected"

    raw_year = extracted_data.get("passed_out_year")
    passed_out_year = int(raw_year) if raw_year is not None else None

    candidate_id = get_or_create_candidate(db, extracted_data)

    db.add(ResumeResult(
        run_id=run_id,
        resume_id=resume_id,
        job_id=job_id,
        candidate_id=candidate_id,
        extracted_data=extracted_data,
        score=score,
        decision=decision,
        decision_reason=reason,
        passed_out_year=passed_out_year,
        ai_status="success"
    ))
    db.commit()
    return "success"


def process_single_upload(run_id: int, job_id: int, filename: str, file_bytes: bytes):
    """Process a single uploaded resume file."""
    db = SessionLocal()
    try:
        run = db.query(ResumeRun).filter_by(run_id=run_id).first()
        job = db.query(JobConfig).filter_by(job_id=job_id).first()
        if not run or not job:
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, filename)
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            try:
                status = process_single(db, run_id, file_path, job_id, job.job_config)
                run.processed_count = 1
                print(f"[RUN {run_id}] Single upload {filename} → {status}")
            except Exception as e:
                print(f"[RUN {run_id}] Error: {filename}: {e}")
                run.failed_count = 1
                try:
                    resume_id = get_or_create_resume(db, file_path)
                    db.add(ResumeResult(
                        run_id=run_id, resume_id=resume_id, job_id=job_id,
                        ai_status="failed", error_message=str(e)
                    ))
                    db.commit()
                except Exception:
                    db.rollback()

        run.ended_at = datetime.utcnow()
        run.status = "completed"
        db.commit()
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


def run_screening_pipeline(
    run_id: int,
    job_id: int,
    batch_size: int,
    zip_filename: str,
    zip_bytes: bytes
):
    """Main pipeline: extract zip, process each resume, update run status."""
    db = SessionLocal()
    try:
        run = db.query(ResumeRun).filter_by(run_id=run_id).first()
        job = db.query(JobConfig).filter_by(job_id=job_id).first()
        if not run or not job:
            return

        job_config = job.job_config

        with tempfile.TemporaryDirectory() as tmpdir:
            resume_files = extract_resume_files(zip_bytes, zip_filename, tmpdir)
            run.total_resumes = len(resume_files)
            db.commit()

            print(f"[RUN {run_id}] Total resumes: {len(resume_files)}")
            rate_limited = False

            for i, resume_path in enumerate(resume_files):
                file_name = os.path.basename(resume_path)
                print(f"[RUN {run_id}] Processing {i+1}/{len(resume_files)} → {file_name}")

                if rate_limited:
                    resume_id = get_or_create_resume(db, resume_path)
                    # Try reusing existing result
                    existing = find_existing_result(db, resume_id, job_id)
                    if existing:
                        existing.run_id = run_id
                        existing.processed_at = datetime.utcnow()
                        existing.ai_status = "reused"
                        run.processed_count += 1
                    else:
                        run.failed_count += 1
                        db.add(ResumeResult(
                            run_id=run_id, resume_id=resume_id, job_id=job_id,
                            ai_status="rate_limited",
                            error_message="Groq rate limit hit earlier in this run"
                        ))
                    db.commit()
                    continue

                try:
                    status = process_single(db, run_id, resume_path, job_id, job_config)
                    run.processed_count += 1
                    print(f"[RUN {run_id}] {file_name} → {status}")

                except RateLimitError as e:
                    print(f"[RUN {run_id}] Rate limit hit: {file_name}")
                    rate_limited = True
                    db.rollback()
                    run.failed_count += 1
                    try:
                        resume_id = get_or_create_resume(db, resume_path)
                        db.add(ResumeResult(
                            run_id=run_id, resume_id=resume_id, job_id=job_id,
                            ai_status="rate_limited", error_message=str(e)
                        ))
                        db.commit()
                    except Exception:
                        db.rollback()

                except Exception as e:
                    print(f"[RUN {run_id}] Error: {file_name}: {e}")
                    db.rollback()
                    run.failed_count += 1
                    try:
                        resume_id = get_or_create_resume(db, resume_path)
                        db.add(ResumeResult(
                            run_id=run_id, resume_id=resume_id, job_id=job_id,
                            ai_status="failed", error_message=str(e)
                        ))
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
