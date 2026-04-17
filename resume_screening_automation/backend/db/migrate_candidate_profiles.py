"""
Migration: create candidate_profiles table and backfill from existing extracted_data.

Run once:
    cd backend
    python -m db.migrate_candidate_profiles
"""

from db.session import engine, SessionLocal
from db.models import Base, CandidateProfile, ResumeResult
from email_validator import validate_email, EmailNotValidError

BATCH_SIZE = 20


def _safe_email(value):
    try:
        return validate_email(str(value or "").strip(), check_deliverability=False).email
    except EmailNotValidError:
        return None


def run():
    # 1. Create table if it doesn't exist
    Base.metadata.create_all(engine, tables=[CandidateProfile.__table__])
    print("Table candidate_profiles ensured.")

    db = SessionLocal()
    try:
        # 2. Count total rows to process
        total = db.query(ResumeResult.result_id).count()
        print(f"Total resume results found: {total}")

        seen = set()
        created = 0
        skipped = 0
        offset = 0

        while True:
            batch = (
                db.query(ResumeResult)
                .order_by(ResumeResult.result_id)
                .offset(offset)
                .limit(BATCH_SIZE)
                .all()
            )
            if not batch:
                break

            for r in batch:
                if r.resume_id in seen:
                    skipped += 1
                    continue
                seen.add(r.resume_id)

                data = r.extracted_data
                if not data:
                    skipped += 1
                    continue

                # Skip if profile already exists
                exists = db.query(CandidateProfile.profile_id).filter_by(resume_id=r.resume_id).scalar()
                if exists:
                    skipped += 1
                    continue

                personal = data.get("personal_details") or {}
                raw_year = data.get("passed_out_year")

                profile = CandidateProfile(
                    resume_id        = r.resume_id,
                    full_name        = personal.get("full_name"),
                    email            = _safe_email(personal.get("email")),
                    phone            = personal.get("phone"),
                    experience_years = data.get("experience_years"),
                    passed_out_year  = int(raw_year) if raw_year is not None else None,
                    skills           = data.get("skills", []),
                    education        = data.get("education", []),
                    projects         = data.get("projects", []),
                )
                db.add(profile)
                created += 1

            db.commit()
            offset += BATCH_SIZE
            print(f"  Processed {min(offset, total)}/{total} — created so far: {created}")

        print(f"\nDone. Created: {created}, Skipped: {skipped}")

    finally:
        db.close()


if __name__ == "__main__":
    run()
