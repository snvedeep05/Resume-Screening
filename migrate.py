"""
Run this script ONCE to apply the schema changes needed for the pipeline feature.

Usage:
    cd Resume-Screening
    python migrate.py

It is safe to run multiple times — all statements use IF NOT EXISTS / IF EXISTS.
"""

import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")

MIGRATIONS = [
    # 1. Add result_id to resume_results if it doesn't already exist as a column
    #    (it already exists as primary key — this is a no-op guard)
    "SELECT 1",  # placeholder — result_id is already the PK

    # 2. Add job_id column to email_logs (NULL = legacy record)
    """
    ALTER TABLE email_logs
        ADD COLUMN IF NOT EXISTS job_id INTEGER;
    """,

    # 3. Drop the old unique constraint (email, template_id)
    """
    ALTER TABLE email_logs
        DROP CONSTRAINT IF EXISTS uq_email_template;
    """,

    # 4. New constraint for records WITH a job_id
    #    (NULL != NULL in Postgres so this naturally allows multiple legacy NULLs)
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_email_template_job'
        ) THEN
            ALTER TABLE email_logs
                ADD CONSTRAINT uq_email_template_job
                UNIQUE (email, template_id, job_id);
        END IF;
    END$$;
    """,

    # 5. Partial unique index for legacy records where job_id IS NULL
    #    Prevents duplicate (email, template_id) among old records.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_email_template_null_job
        ON email_logs (email, template_id)
        WHERE job_id IS NULL;
    """,

    # 6. Create candidate_pipeline table
    """
    CREATE TABLE IF NOT EXISTS candidate_pipeline (
        pipeline_id      SERIAL PRIMARY KEY,
        job_id           INTEGER NOT NULL,
        result_id        INTEGER,
        email            TEXT NOT NULL,
        full_name        TEXT,
        phone            TEXT,
        score            INTEGER,
        stage            TEXT NOT NULL DEFAULT 'new',
        stage_updated_at TIMESTAMP DEFAULT NOW(),
        added_at         TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_pipeline_email_job UNIQUE (email, job_id)
    );
    """,

    # 7. Create email_queue table
    """
    CREATE TABLE IF NOT EXISTS email_queue (
        queue_id         SERIAL PRIMARY KEY,
        pipeline_id      INTEGER REFERENCES candidate_pipeline(pipeline_id),
        email            TEXT NOT NULL,
        full_name        TEXT,
        template_id      INTEGER NOT NULL,
        params           JSONB,
        job_id           INTEGER,
        stage_after_send TEXT,
        queued_at        TIMESTAMP DEFAULT NOW(),
        status           TEXT DEFAULT 'pending',
        sent_at          TIMESTAMP
    );
    """,
]


def run_migrations():
    conn   = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    conn.autocommit = False

    try:
        for i, sql in enumerate(MIGRATIONS, 1):
            sql = sql.strip()
            if not sql or sql == "SELECT 1":
                continue
            print(f"[{i}] Running migration...")
            cursor.execute(sql)

        conn.commit()
        print("\n✅ All migrations applied successfully.")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run_migrations()
