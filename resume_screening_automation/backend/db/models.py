from sqlalchemy import (
    Column,
    Integer,
    Text,
    Boolean,
    JSON,
    ForeignKey,
    TIMESTAMP
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class JobConfig(Base):
    __tablename__ = "job_configs"

    job_id = Column(Integer, primary_key=True)
    job_title = Column(Text, nullable=False)
    job_config = Column(JSON, nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())


class ResumeRun(Base):
    __tablename__ = "resume_runs"

    run_id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("job_configs.job_id"), nullable=False)
    batch_size = Column(Integer, nullable=False)
    total_resumes = Column(Integer, nullable=False)
    processed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    status = Column(Text, default="running")
    started_at = Column(TIMESTAMP, server_default=func.now())
    ended_at = Column(TIMESTAMP)


class ResumeFile(Base):
    __tablename__ = "resume_files"

    resume_id = Column(Integer, primary_key=True)
    file_name = Column(Text, nullable=False)
    file_hash = Column(Text, unique=True, nullable=False)
    file_path = Column(Text)
    uploaded_at = Column(TIMESTAMP, server_default=func.now())


class ResumeResult(Base):
    __tablename__ = "resume_results"

    result_id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("resume_runs.run_id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resume_files.resume_id"), nullable=False)
    job_id = Column(Integer, ForeignKey("job_configs.job_id"), nullable=False)

    extracted_data = Column(JSON)
    score = Column(Integer)
    decision = Column(Text)
    decision_reason = Column(Text)

    ai_status = Column(Text)
    error_message = Column(Text)
    processed_at = Column(TIMESTAMP, server_default=func.now())
