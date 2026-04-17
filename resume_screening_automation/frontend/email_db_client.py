import streamlit as st
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, Text, JSON,
    TIMESTAMP, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()


# ── Models ─────────────────────────────────────────────────────────────────────

class EmailLog(Base):
    __tablename__ = "email_logs"

    log_id      = Column(Integer, primary_key=True)
    email       = Column(Text, nullable=False)
    template_id = Column(Integer, nullable=False)
    full_name   = Column(Text)
    job_title   = Column(Text)
    job_id      = Column(Integer)          # NULL for legacy records
    sent_at     = Column(TIMESTAMP, server_default=func.now())

    # New-style records deduplicated by (email, template_id, job_id).
    # Legacy records (job_id IS NULL) are handled by a partial unique index
    # created in migrate.py — SQLAlchemy create_all does not manage that.
    __table_args__ = (
        UniqueConstraint("email", "template_id", "job_id", name="uq_email_template_job"),
    )


class CandidatePipeline(Base):
    __tablename__ = "candidate_pipeline"

    pipeline_id      = Column(Integer, primary_key=True)
    job_id           = Column(Integer, nullable=False)
    result_id        = Column(Integer)           # link to resume_results.result_id
    email            = Column(Text, nullable=False)
    full_name        = Column(Text)
    phone            = Column(Text)
    score            = Column(Integer)
    stage            = Column(Text, nullable=False, default="new")
    stage_updated_at = Column(TIMESTAMP, server_default=func.now())
    added_at         = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("email", "job_id", name="uq_pipeline_email_job"),
    )



class CustomEmailLog(Base):
    """Stores ad-hoc emails sent via the Custom Email Sender page."""
    __tablename__ = "custom_email_logs"

    log_id        = Column(Integer, primary_key=True)
    full_name     = Column(Text)
    email         = Column(Text, nullable=False)
    job_title     = Column(Text)
    template_id   = Column(Integer, nullable=False)
    template_name = Column(Text)
    reason        = Column(Text)
    sent_at       = Column(TIMESTAMP, server_default=func.now())


class EmailQueue(Base):
    __tablename__ = "email_queue"

    queue_id        = Column(Integer, primary_key=True)
    pipeline_id     = Column(Integer)
    email           = Column(Text, nullable=False)
    full_name       = Column(Text)
    template_id     = Column(Integer, nullable=False)
    params          = Column(JSON)
    job_id          = Column(Integer)
    stage_after_send = Column(Text)   # stage to set once email is sent
    queued_at       = Column(TIMESTAMP, server_default=func.now())
    status          = Column(Text, default="pending")  # pending | sent | failed | cancelled
    sent_at         = Column(TIMESTAMP)


# ── Engine / Session ───────────────────────────────────────────────────────────

def get_engine():
    return create_engine(st.secrets["DATABASE_URL"], pool_pre_ping=True)


def get_session():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# ── EmailLog helpers ───────────────────────────────────────────────────────────

def is_already_sent(db, email: str, template_id: int, job_id: int = None) -> bool:
    """
    Checks if this exact email was already sent for this template + job.
    Falls back to legacy NULL-job_id records so we don't re-send to
    candidates who received the email before job_id tracking was added.
    """
    # Exact match (new records)
    if db.query(EmailLog).filter_by(
        email=email, template_id=template_id, job_id=job_id
    ).first():
        return True
    # Legacy fallback: record with same email+template but NULL job_id
    if job_id is not None:
        if db.query(EmailLog).filter(
            EmailLog.email == email,
            EmailLog.template_id == template_id,
            EmailLog.job_id.is_(None)
        ).first():
            return True
    return False


def has_conflicting_email(db, email: str, conflicting_template_id: int, job_id: int = None) -> bool:
    """Check if the opposing decision email was already sent to this address."""
    if db.query(EmailLog).filter_by(
        email=email, template_id=conflicting_template_id, job_id=job_id
    ).first():
        return True
    if job_id is not None:
        if db.query(EmailLog).filter(
            EmailLog.email == email,
            EmailLog.template_id == conflicting_template_id,
            EmailLog.job_id.is_(None)
        ).first():
            return True
    return False


def log_email_sent(
    db, email: str, template_id: int,
    full_name: str = None, job_title: str = None, job_id: int = None
):
    db.add(EmailLog(
        email=email, template_id=template_id,
        full_name=full_name, job_title=job_title, job_id=job_id
    ))
    db.commit()


def get_all_logs(db) -> list:
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT DISTINCT ON (el.log_id)
            el.log_id,
            el.full_name,
            el.email,
            el.template_id,
            el.job_title,
            el.job_id,
            el.sent_at,
            rf.file_name AS resume_file
        FROM email_logs el
        LEFT JOIN candidate_pipeline cp
               ON cp.email = el.email
              AND cp.result_id IS NOT NULL
        LEFT JOIN resume_results rr ON rr.result_id = cp.result_id
        LEFT JOIN resume_files   rf ON rf.resume_id = rr.resume_id
        ORDER BY el.log_id, el.sent_at DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


# ── CustomEmailLog helpers ─────────────────────────────────────────────────────

def log_custom_email(
    db,
    email: str,
    template_id: int,
    template_name: str,
    full_name: str = None,
    job_title: str = None,
    reason: str = None,
):
    db.add(CustomEmailLog(
        email=email,
        template_id=template_id,
        template_name=template_name,
        full_name=full_name,
        job_title=job_title,
        reason=reason,
    ))
    db.commit()


def get_custom_email_logs(db) -> list:
    rows = db.query(CustomEmailLog).order_by(CustomEmailLog.sent_at.desc()).all()
    return [
        {
            "full_name":     r.full_name,
            "email":         r.email,
            "job_title":     r.job_title,
            "template_name": r.template_name,
            "reason":        r.reason,
            "sent_at":       r.sent_at,
        }
        for r in rows
    ]


# ── CandidatePipeline helpers ──────────────────────────────────────────────────

def seed_candidate(
    db,
    job_id: int,
    email: str,
    full_name: str,
    phone: str,
    score: int,
    result_id: int = None,
) -> bool:
    """
    Add a candidate to the pipeline. Determines starting stage from email_logs.
    Returns True if added, False if already existed.
    """
    from db_stage_map import TEMPLATE_TO_STAGE  # local import to avoid circular
    # Already in pipeline?
    if db.query(CandidatePipeline).filter_by(email=email, job_id=job_id).first():
        return False

    # Determine starting stage from email history
    stage = "new"
    for template_id, stage_name in TEMPLATE_TO_STAGE.items():
        if is_already_sent(db, email, template_id, job_id):
            stage = stage_name
            break  # use the most advanced stage found

    db.add(CandidatePipeline(
        job_id=job_id,
        result_id=result_id,
        email=email,
        full_name=full_name,
        phone=phone,
        score=score,
        stage=stage,
    ))
    db.commit()
    return True


def get_pipeline_candidates(db, job_id: int) -> list:
    rows = db.query(CandidatePipeline).filter_by(job_id=job_id).order_by(
        CandidatePipeline.added_at.desc()
    ).all()
    return [
        {
            "pipeline_id":      r.pipeline_id,
            "email":            r.email,
            "full_name":        r.full_name,
            "phone":            r.phone,
            "score":            r.score,
            "stage":            r.stage,
            "stage_updated_at": r.stage_updated_at,
            "added_at":         r.added_at,
        }
        for r in rows
    ]


def update_pipeline_stage(db, pipeline_id: int, new_stage: str):
    from sqlalchemy import text
    db.execute(
        text(
            "UPDATE candidate_pipeline SET stage = :stage, "
            "stage_updated_at = NOW() WHERE pipeline_id = :pid"
        ),
        {"stage": new_stage, "pid": pipeline_id},
    )
    db.commit()


def bulk_update_stages(db, pipeline_ids: list, new_stage: str):
    from sqlalchemy import func
    if not pipeline_ids:
        return
    db.query(CandidatePipeline).filter(
        CandidatePipeline.pipeline_id.in_(pipeline_ids)
    ).update(
        {"stage": new_stage, "stage_updated_at": func.now()},
        synchronize_session=False,
    )
    db.commit()


# ── EmailQueue helpers ─────────────────────────────────────────────────────────

def enqueue_email(
    db,
    pipeline_id: int,
    email: str,
    full_name: str,
    template_id: int,
    params: dict,
    job_id: int,
    stage_after_send: str,
) -> int:
    item = EmailQueue(
        pipeline_id=pipeline_id,
        email=email,
        full_name=full_name,
        template_id=template_id,
        params=params,
        job_id=job_id,
        stage_after_send=stage_after_send,
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.queue_id


def get_pending_queue(db, job_id: int = None) -> list:
    q = db.query(EmailQueue).filter_by(status="pending")
    if job_id is not None:
        q = q.filter_by(job_id=job_id)
    rows = q.order_by(EmailQueue.queued_at).all()
    return [
        {
            "queue_id":        r.queue_id,
            "pipeline_id":     r.pipeline_id,
            "email":           r.email,
            "full_name":       r.full_name,
            "template_id":     r.template_id,
            "params":          r.params,
            "job_id":          r.job_id,
            "stage_after_send": r.stage_after_send,
            "queued_at":       r.queued_at,
        }
        for r in rows
    ]


def mark_queue_sent(db, queue_id: int):
    from sqlalchemy import text
    db.execute(
        text(
            "UPDATE email_queue SET status='sent', sent_at=NOW() WHERE queue_id=:qid"
        ),
        {"qid": queue_id},
    )
    db.commit()


def mark_queue_failed(db, queue_id: int):
    from sqlalchemy import text
    db.execute(
        text("UPDATE email_queue SET status='failed' WHERE queue_id=:qid"),
        {"qid": queue_id},
    )
    db.commit()


def cancel_queued_emails(db, pipeline_ids: list):
    """Cancel pending queue items for the given pipeline IDs (used for undo)."""
    if not pipeline_ids:
        return
    db.query(EmailQueue).filter(
        EmailQueue.pipeline_id.in_(pipeline_ids),
        EmailQueue.status == "pending",
    ).update({"status": "cancelled"}, synchronize_session=False)
    db.commit()
