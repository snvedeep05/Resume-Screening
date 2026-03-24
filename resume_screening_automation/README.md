# Resume Screening Automation

An AI-powered resume screening system that automatically extracts, scores, and ranks candidates against job requirements. Built with FastAPI (backend) and Streamlit (frontend), powered by Groq's LLaMA model.

---

## Recent Updates

### March 2026

#### 1. `/health` Endpoint Added — UptimeRobot Support
**Why:** Render's free tier spins down any web service after **15 minutes of no incoming HTTP requests**. Background processing tasks (resume screening) do not count as activity — so the server was shutting down mid-run on large batches.

**Fix:** Added a public `/health` endpoint in `backend/main.py`. Registered as two separate decorators so GET and HEAD have distinct OpenAPI operation IDs (avoids Swagger duplicate operation ID warning):

```python
@app.get("/health")
def health():
    return {"status": "ok"}

@app.head("/health", include_in_schema=False)
def health_head():
    pass
```

**UptimeRobot setup:** A monitor is configured to ping `{BACKEND_URL}/health` every **5 minutes**, keeping the Render server alive throughout batch runs.

---

#### 2. pdfminer FontBBox Warnings Suppressed
**Why:** Render logs were flooded with repeated harmless warnings from `pdfminer`. Text extraction is unaffected.

**Fix:** Added at the top of `backend/services/resume_processor.py`:
```python
logging.getLogger("pdfminer").setLevel(logging.ERROR)
```

---

#### 3. Re-run Bug Fixed — Failed Resumes Now Re-extracted on Retry
**Fix:** Changed the reuse query to filter `extracted_data IS NOT NULL` so failed rows are not treated as valid cached results:
```python
existing_result = db.query(ResumeResult).filter(
    ResumeResult.resume_id == resume_id,
    ResumeResult.job_id == job_id,
    ResumeResult.extracted_data.isnot(None)
).first()
```

---

#### 4. `failed_count` Not Persisting After Rollback — Fixed
**Why:** `run.failed_count += 1` was called before `db.rollback()` in both except handlers. After rollback, SQLAlchemy expires all session objects — discarding the in-memory increment. `failed_count` in the DB never actually updated for failed/rate-limited resumes.

**Fix:** Moved `run.failed_count += 1` to after `db.rollback()` in both handlers so SQLAlchemy re-loads the fresh DB value before incrementing.

---

#### 5. Groq Rate Limit — Early Exit Added
**Why:** Once Groq's daily token limit is hit, every subsequent API call in the same run also fails — wasting time attempting calls that will all error. Old resumes (already extracted) were being incorrectly marked as `rate_limited` instead of being reused.

**Fix:** Added a `rate_limit_hit` flag. On first `RateLimitError`:
- All subsequent **new** resumes are marked `rate_limited` immediately (no API call)
- All subsequent **old** resumes (with existing `extracted_data`) are still reused normally — Groq is not called for them regardless

---

#### 6. Email Automation Integrated via Streamlit Multipage
**What:** Brevo Email Automation merged into the Resume Screening app using Streamlit's `pages/` directory. No changes to `app.py`. Three new pages added:

| Page | File | Description |
|---|---|---|
| 📧 Shortlisting Emails | `pages/4_Shortlisting_Emails.py` | Send shortlist/rejection emails via Brevo |
| 📝 Assignment Emails | `pages/5_Assignment_Emails.py` | Send assignment emails to interested candidates |
| 📊 Email Dashboard | `pages/6_Email_Dashboard.py` | Email log, metrics, grouped bar chart by date |

All pages are login-guarded via `st.session_state.get("logged_in")`.

---

#### 7. Brevo Daily Usage Banner
**What:** A live usage indicator shown at the top of all three email pages. Fetches real-time data from `AccountApi.get_account()` (matches the Brevo dashboard exactly). Cached for 60 seconds with a manual `↺` refresh button.

```
📬 Brevo ● Healthy    ████░░░░░░░░░░░░░░░░  46/300    🟩 254 left    ✅ 43 delivered    ⚠️ 3 bounced
```

Color coding: 🟢 Healthy (0–66%), 🟡 Moderate (67–89%), 🔴 Critical (90–100%).

**Note:** Brevo IP allowlisting must be **deactivated** in Brevo settings (`Settings → Authorized IPs → Deactivated`) since Streamlit Cloud uses dynamic IPs that change on every redeploy.

---

#### 8. Groq Free Tier Rate Limit — Known Behavior
**Limit:** 500,000 tokens/day, resets at midnight UTC (5:30 AM IST).

**Recovery:** Re-run the same ZIP after reset. Successfully processed resumes hit the reuse path (no AI call). Only failed ones are re-extracted.

---

#### 9. `update_job` — Atomic Transaction Fix
**Why:** The previous implementation used two separate `db.commit()` calls — one to deactivate the old job config, another to create the new one. If the server crashed or threw an exception between the two commits, the old job was permanently deactivated with no replacement, silently disappearing from the job dropdown.

**Fix:** Merged both operations into a single atomic transaction in `backend/api/jobs.py`:
```python
old_job.is_active = False
new_job = JobConfig(...)
db.add(new_job)
try:
    db.commit()       # single commit — both changes or neither
except Exception:
    db.rollback()
    raise HTTPException(status_code=500, detail="Failed to update job config")
```

---

#### 10. HTTP Timeouts Added to All Frontend Requests
**Why:** Render's free tier takes ~30 seconds to wake from spindown. Without a timeout, the Streamlit frontend would hang indefinitely with no feedback whenever the backend was cold-starting.

**Fix:** Added `timeout=30` to every `requests.get`, `requests.post`, and `requests.patch` call in `frontend/api_client.py` and the inline POST in `frontend/app.py`. After 30 seconds with no response, a clean error is shown instead of an infinite hang.

---

#### 11. Results Dashboard — `passed_out_year` Crash Fixed
**Why:** `df["passed_out_year"].astype("Int64")` raised a `ValueError` and crashed the entire Results Dashboard tab if any resume had a non-numeric year value (e.g. AI returned `"N/A"` or `"Present"`).

**Fix:** Added `pd.to_numeric(..., errors="coerce")` before the cast:
```python
df["passed_out_year"] = pd.to_numeric(
    df["passed_out_year"], errors="coerce"
).astype("Int64")
```
Non-numeric values are silently coerced to `NaN`. The row stays in the results table; the year column shows `<NA>` for those entries.

---

#### 12. Contradictory Emails Blocked — Shortlist + Rejection to Same Candidate
**Why:** The existing duplicate check used `UniqueConstraint("email", "template_id")`. Since shortlist (template 28) and rejection (template 36) have different IDs, a candidate could receive both emails across separate send sessions — a serious recruitment mistake.

**Fix:** Added `has_conflicting_email()` to `frontend/email_db_client.py`. Before sending any email, Page 4 now checks whether the opposing template was already sent to that address:
```python
if has_conflicting_email(db, email, conflict_id):
    skipped_list.append(f"{name} — {email} (⚠️ conflicting email already sent)")
    continue
```

---

#### 13. Live Run Progress — `GET /screening/runs/{run_id}`
**Why:** After clicking "Start Screening", users had no visibility into whether the run was progressing, stuck, or done — until manually checking the Results Dashboard.

**Fix:** Two parts added:

**Backend** — new endpoint in `backend/api/screening.py`:

| Method | Path | Description |
|---|---|---|
| GET | `/screening/runs/{run_id}` | Returns run status, processed count, failed count, and timestamps |

**Frontend** — `frontend/app.py` Tab 1 now stores the `run_id` in session state and shows a `@st.fragment(run_every=30)` progress block:
```
[████████░░░░░░░░░░░░]
⏳ Run 42 — 24 / 80 processed · 2 failed
```
Polls every **30 seconds** — enough granularity for a batch process without unnecessary backend calls. Auto-stops and shows a success/error message when the run completes or crashes.

---

#### 14. Results Endpoint Paginated
**Why:** `GET /screening/results/{job_id}` returned all results across all runs for a job with no limit. As runs accumulate, this query grows unboundedly — causing slow responses and potential timeouts on Render free tier.

**Fix:** Added `limit` and `offset` query parameters (default: `limit=500`, `offset=0`):
```python
@router.get("/results/{job_id}")
def get_results(job_id: int, limit: int = 500, offset: int = 0):
    results = db.query(...).order_by(...).offset(offset).limit(limit).all()
```
The frontend passes these params in `fetch_all_results()`. All existing client-side filtering (date, decision, year, score) works on the fetched dataset. Default of 500 covers all realistic single-job result sets.

---

#### 15. Sent Emails — Downloadable Excel After Send
**What:** After clicking Send on Page 4 (Shortlisting) or Page 5 (Assignment), a download button now appears for an Excel file of successfully sent emails only — same columns as the uploaded file.

- **Page 4 columns:** `full_name`, `email`, `decision`, `job_title`
- **Page 5 columns:** `full_name`, `email`, `job_title`
- **Filename format:** `sent_{original_filename}_{YYYY-MM-DD_HH-MM-SS}.xlsx`

Skipped, failed, already-sent, and conflicting rows are excluded. Button only appears if at least one email was sent.

---

#### 16. Backend `requirements.txt` Cleaned Up
Removed unused packages (`streamlit`, `PyPDF2`, `openpyxl`) and added `email-validator` which was already in use for resume email normalization but missing from the dependency list. Deleted dev-only scripts `test_db.py` and `test_models.py` (not part of application runtime).

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Database Schema](#database-schema)
- [Backend](#backend)
  - [Entry Point](#entry-point)
  - [Security](#security)
  - [API Routes](#api-routes)
  - [Services](#services)
  - [AI Prompts](#ai-prompts)
- [Frontend](#frontend)
  - [App Pages / Tabs](#app-pages--tabs)
  - [API Client](#api-client)
- [Screening Pipeline](#screening-pipeline)
- [Scoring Logic](#scoring-logic)
- [Configuration](#configuration)
- [Installation & Running](#installation--running)
- [Known Gaps & Suggested Improvements](#known-gaps--suggested-improvements)
- [Development & Testing Scripts](#development--testing-scripts)

---

## Overview

This system allows a recruiter to:
1. Create a **Job Config** (manually or AI-generated from a job description)
2. Upload a **ZIP of resumes** (PDF or DOCX)
3. Let the system **automatically extract** structured data from each resume using AI
4. **Score and rank** each candidate against the job requirements
5. View and **download results** from a dashboard (Excel or JSON)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        FRONTEND (Streamlit)                  │
│   Login → Job Config Builder → Resume Upload → Dashboard     │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP (x-api-key header)
┌────────────────────────▼─────────────────────────────────────┐
│                       BACKEND (FastAPI)                       │
│   /jobs  ──►  JobConfig CRUD + AI generation                 │
│   /screening/start  ──►  ZIP upload + background processing  │
│   /screening/results/{job_id}  ──►  Results query            │
└──────┬──────────────────────────────────────────┬────────────┘
       │                                          │
┌──────▼──────┐                        ┌──────────▼──────────┐
│  PostgreSQL  │                        │  Groq (LLaMA 3.1)   │
│  (SQLAlchemy)│                        │  - Resume extraction │
│              │                        │  - Job config gen    │
└─────────────┘                        └─────────────────────┘
```

---

## Project Structure

```
resume_screening_automation/
├── backend/
│   ├── main.py                        # FastAPI app entry point
│   ├── security.py                    # API key authentication
│   ├── requirements.txt               # Backend dependencies
│   ├── api/
│   │   ├── jobs.py                    # Job config endpoints
│   │   └── screening.py               # Screening endpoints
│   ├── db/
│   │   ├── models.py                  # SQLAlchemy ORM models
│   │   └── session.py                 # DB engine + session factory
│   ├── services/
│   │   ├── ai_service.py              # Groq: job config generation
│   │   ├── resume_ai_extractor.py     # Groq: resume data extraction
│   │   ├── resume_processor.py        # PDF/DOCX text extraction
│   │   └── scoring_engine.py          # Candidate scoring logic
│   └── prompts/
│       ├── recruiter_prompt.py        # System prompt for job config AI
│       └── resume_extraction_prompt.py # System prompt for resume AI
└── frontend/
    ├── app.py                         # Streamlit main app (Tabs 1–3)
    ├── api_client.py                  # HTTP client helpers
    ├── brevo_client.py                # Brevo API client + daily stats
    ├── email_db_client.py             # email_logs table + helpers
    ├── email_utils.py                 # Shared Brevo usage banner
    ├── pyproject.toml                 # Python 3.11 lock for Streamlit Cloud
    ├── requirements.txt               # Frontend dependencies
    └── pages/
        ├── 4_Shortlisting_Emails.py   # Shortlist/rejection email sender
        ├── 5_Assignment_Emails.py     # Assignment email sender
        └── 6_Email_Dashboard.py       # Email log + chart dashboard
```

---

## Database Schema

### `job_configs`
Stores job configurations used for screening.

| Column      | Type      | Description                          |
|-------------|-----------|--------------------------------------|
| job_id      | Integer   | Primary key                          |
| job_title   | Text      | Name of the job role                 |
| job_config  | JSON      | Structured requirements & weights    |
| version     | Integer   | Config version (default 1)           |
| is_active   | Boolean   | Whether this job is active           |
| created_at  | Timestamp | Auto-set on creation                 |

### `resume_runs`
Tracks each batch screening run.

| Column          | Type      | Description                          |
|-----------------|-----------|--------------------------------------|
| run_id          | Integer   | Primary key                          |
| job_id          | Integer   | FK → job_configs                     |
| batch_size      | Integer   | Number of resumes per batch          |
| total_resumes   | Integer   | Total resumes in the ZIP             |
| processed_count | Integer   | Successfully processed count         |
| failed_count    | Integer   | Failed/skipped count                 |
| status          | Text      | `running` or `completed`             |
| started_at      | Timestamp | Auto-set on creation                 |
| ended_at        | Timestamp | Set when run completes               |

### `resume_files`
Deduplicates uploaded resume files.

| Column      | Type      | Description                          |
|-------------|-----------|--------------------------------------|
| resume_id   | Integer   | Primary key                          |
| file_name   | Text      | Original file name                   |
| file_hash   | Text      | MD5 hash (unique — dedup key)        |
| file_path   | Text      | Temp path at time of processing      |
| uploaded_at | Timestamp | Auto-set on creation                 |

### `resume_results`
Stores screening outcome for each resume × job pair.

| Column           | Type      | Description                                                        |
|------------------|-----------|--------------------------------------------------------------------|
| result_id        | Integer   | Primary key                                                        |
| run_id           | Integer   | FK → resume_runs                                                   |
| resume_id        | Integer   | FK → resume_files                                                  |
| job_id           | Integer   | FK → job_configs                                                   |
| extracted_data   | JSON      | AI-extracted candidate info (NULL if failed)                       |
| score            | Integer   | Final score 0–100 (NULL if failed)                                 |
| decision         | Text      | `shortlisted` or `rejected` (NULL if failed)                       |
| decision_reason  | Text      | Human-readable scoring breakdown                                   |
| ai_status        | Text      | `success`, `reused`, `failed`, or `rate_limited`                   |
| error_message    | Text      | Error details if processing failed                                 |
| processed_at     | Timestamp | Auto-set on creation                                               |

### `email_logs`
Tracks every email sent via Brevo. Prevents duplicate sends across runs.

| Column      | Type      | Description                                          |
|-------------|-----------|------------------------------------------------------|
| log_id      | Integer   | Primary key                                          |
| email       | Text      | Recipient email address                              |
| template_id | Integer   | Brevo template ID (28=Shortlisted, 36=Rejected, 30=Assignment) |
| full_name   | Text      | Recipient name                                       |
| job_title   | Text      | Job title for template personalization               |
| sent_at     | Timestamp | Auto-set on send                                     |

Unique constraint on `(email, template_id)` — same email cannot receive the same template twice.

---

## Backend

### Entry Point

**`backend/main.py`**

Initializes the FastAPI application and registers both routers under API key protection.

```python
app = FastAPI(title="Resume Screening Backend")
app.include_router(jobs_router, prefix="/jobs", dependencies=[Depends(verify_api_key)])
app.include_router(screening_router, dependencies=[Depends(verify_api_key)])
```

All routes require a valid `x-api-key` header. Swagger UI is available at `/docs` with persistent authorization enabled.

**Public endpoint (no API key required):**

| Method       | Path      | Description                                              |
|--------------|-----------|----------------------------------------------------------|
| GET / HEAD   | `/health` | Returns `{ "status": "ok" }` — used by UptimeRobot to keep the Render server alive |

The `/health` endpoint supports HEAD requests because UptimeRobot sends HEAD by default. Without this, Render's free-tier server would spin down after 15 minutes of inactivity and terminate mid-run background tasks.

---

### Security

**`backend/security.py`**

Validates requests using a static API key read from the environment variable `API_KEY`.

- Header name: `x-api-key`
- Returns `401 Unauthorized` if key is missing or incorrect
- Returns `500` if `API_KEY` is not configured in the environment

---

### API Routes

#### Jobs — `backend/api/jobs.py`

| Method | Path                  | Description                                    |
|--------|-----------------------|------------------------------------------------|
| POST   | `/jobs`               | Create a new job config (manual JSON payload)  |
| GET    | `/jobs`               | List all jobs (returns id + title)             |
| POST   | `/jobs/ai-generate`   | Generate a job config from a job description   |

**POST `/jobs`** — Request body:
```json
{
  "job_title": "Backend Engineer",
  "job_config": { ... }
}
```

**POST `/jobs/ai-generate`** — Request body:
```json
{
  "job_description": "We are looking for a Python backend developer..."
}
```
Returns the AI-generated `job_config` JSON.

---

#### Screening — `backend/api/screening.py`

| Method | Path                            | Description                               |
|--------|---------------------------------|-------------------------------------------|
| POST   | `/screening/start`              | Upload ZIP of resumes and start screening |
| GET    | `/screening/runs/{run_id}`      | Get live status of a screening run        |
| GET    | `/screening/results/{job_id}`   | Get screening results for a job (paginated, default limit=500) |

**Helper: `get_or_create_resume(db, resume_path)`**

Called for every resume before scoring. Handles deduplication at the file level:

1. Opens the file and computes its **MD5 hash**
2. Queries `resume_files` by `file_hash`
3. If a match exists → returns the existing `resume_id` (no insert)
4. If no match → creates a new `ResumeFile` record and returns the new `resume_id`

This ensures the same physical file is never stored twice in the database, even across different runs or ZIP uploads.

**POST `/screening/start`** — Form data:
- `job_id` (int): The job to screen against
- `batch_size` (int): How many resumes to process per batch
- `zip_file` (file): A `.zip` containing `.pdf` / `.docx` resumes

Returns immediately with `{ "run_id": ..., "status": "started" }`. Processing continues in the background.

**GET `/screening/results/{job_id}`** — Returns a list of:
```json
[
  {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+1234567890",
    "job_title": "Backend Engineer",
    "score": 78,
    "decision": "shortlisted",
    "decision_reason": "Required skills matched 4/5; Nice-to-have skills matched 2/3; ...",
    "processed_at": "2026-03-08T10:00:00"
  }
]
```

---

### Services

#### `backend/services/resume_processor.py`

Handles raw text extraction from resume files before passing to AI.

- `extract_text_from_pdf(path)` — Uses `pdfplumber` to extract text page by page
- `extract_text_from_docx(path)` — Uses `python-docx` to extract paragraph text
- `process_single_resume(resume_path)` — Dispatches to the correct extractor by file extension, then calls `extract_resume_data()` to get structured AI output

Raises exceptions for unsupported formats or empty resume content.

**Note:** pdfminer (used internally by pdfplumber) is suppressed to `ERROR` level at module load time to eliminate noisy `FontBBox` warnings from PDFs with malformed font descriptors. Text extraction is unaffected.

---

#### `backend/services/resume_ai_extractor.py`

Sends raw resume text to Groq (LLaMA 3.1 8B Instant) and returns structured JSON.

- Model: `llama-3.1-8b-instant`
- Temperature: `0.1` (low, for deterministic extraction)
- Uses `RESUME_EXTRACTION_PROMPT` as the system message

Returns a dict with keys: `personal_details`, `skills`, `education`, `projects`, `experience_years`.

Raises `ValueError` if the model does not return valid JSON.

---

#### `backend/services/ai_service.py`

Sends a job description to Groq and returns a structured job config JSON.

- Model: `llama-3.1-8b-instant`
- Temperature: `0.2`
- Uses `JOB_CONFIG_PROMPT` as the system message
- Calls `normalize_scoring_weights()` to ensure weights always sum to 100

**`normalize_scoring_weights(weights)`**:
- If weights are on a 0–1 float scale → multiplies by 100
- If weights are integers that don't sum to 100 → proportionally rescales
- Otherwise → returns as-is

This guard exists because the AI model occasionally outputs weights in the wrong scale or with rounding errors.

---

#### `backend/services/scoring_engine.py`

Scores a candidate resume against a job config. Returns `(score: int, reason: str)`.

**Scoring categories:**

| Category            | `scoring_weights` key     | How it's scored                                              |
|---------------------|---------------------------|--------------------------------------------------------------|
| Required Skills     | `required_skills`         | `(matched / total_required) × weight`                       |
| Nice-to-have Skills | `nice_to_have_skills`     | `(matched / total_nice) × weight`                           |
| Projects            | `projects`                | +10 per domain-matched project, capped at the weight value  |
| Education           | `education`               | Full weight if any degree matches requirements               |
| Eligibility         | `eligibility`             | Full weight if `candidate_type` is `any` or `student`       |

- Final score is capped at 100
- Decision threshold: `shortlisted` if score ≥ 60, otherwise `rejected`
- Text normalization applied before all comparisons: lowercase, remove dots, replace slashes with spaces

---

### AI Prompts

#### `backend/prompts/recruiter_prompt.py`

System prompt for job config generation. Instructs the AI to output a strict JSON schema:

```json
{
  "required_skills": ["Python", "FastAPI"],
  "nice_to_have_skills": ["Docker"],
  "education_requirements": ["B.Tech", "B.E"],
  "candidate_type": "experienced",
  "project_expectations": {
    "domains": ["backend", "api"]
  },
  "scoring_weights": {
    "required_skills": 40,
    "nice_to_have_skills": 20,
    "projects": 20,
    "education": 10,
    "eligibility": 10
  }
}
```

Key rules enforced in the prompt: all `scoring_weights` must be integers summing to exactly 100; no markdown; no hallucination; no missing keys.

---

#### `backend/prompts/resume_extraction_prompt.py`

System prompt for resume data extraction. Instructs the AI to output:

```json
{
  "personal_details": {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+91XXXXXXXXXX"
  },
  "skills": ["Python", "SQL", "React"],
  "education": [
    { "degree": "B.Tech", "field": "Computer Science", "institution": "XYZ University" }
  ],
  "projects": [
    { "title": "Chat App", "domain": "backend", "tech_stack": ["Node.js", "MongoDB"] }
  ],
  "experience_years": 2
}
```

Key rules: no hallucination of names/emails/degrees, conservative domain inference (e.g. "web", "backend", "ai", "ml").

---

## Frontend

### App Pages / Tabs

**`frontend/app.py`**

Main Streamlit app with session-based login and three tabs. Three additional email pages are loaded automatically by Streamlit from the `pages/` directory and appear in the sidebar.

#### Login Page
- Username/password checked against `st.secrets["APP_USERNAME"]` and `st.secrets["APP_PASSWORD"]`
- Session stored in `st.session_state.logged_in`
- All `pages/` files guard themselves with `if not st.session_state.get("logged_in"): st.stop()`

#### Tab 1 — Resume Screening
1. Loads all available jobs from the backend
2. User selects a job and uploads a `.zip` file
3. On "Start Screening", posts to `/screening/start` with `job_id`, `batch_size=10`, and the zip file
4. Returns `run_id` immediately; processing continues in the background

#### Tab 2 — Job Config Builder
1. Create new or update existing job configs
2. AI generation from pasted job description via `/jobs/ai-generate`
3. Updating a job creates a new version and deactivates the old one

#### Tab 3 — Results Dashboard
1. Results fetched from `/screening/results/{job_id}` (5-minute cache)
2. Filters: date range, decision, passed-out year, minimum score, sort order
3. Summary metrics + full results table
4. Download as Excel or JSON

#### Page 4 — 📧 Shortlisting / Rejection Emails
1. Upload reviewed Excel (columns: `full_name`, `email`, `decision`, `job_title`)
2. Shows decision summary (Shortlisted / Rejected counts)
3. "Send Emails" → sends via Brevo template (28=Shortlisted, 36=Rejected)
4. Skips already-sent emails (checked against `email_logs`)
5. Brevo daily usage banner at top with live count and `↺` refresh button

#### Page 5 — 📝 Assignment Emails
1. Upload Excel (columns: `full_name`, `email`, `job_title`)
2. Sends Brevo template 30 with auto-calculated deadline (today + 10 days)
3. Skips already-sent emails

#### Page 6 — 📊 Email Dashboard
1. Live Brevo daily usage banner (same as pages 4 & 5)
2. Summary metrics: Total, Shortlisted, Rejected, Assignment counts
3. Grouped bar chart — Shortlisted vs Rejected per date (Altair)
4. Filterable log table with CSV export

---

### API Client

**`frontend/api_client.py`**

Helper functions that wrap all HTTP calls to the backend.

| Function                        | Method | Endpoint              | Description                       |
|---------------------------------|--------|-----------------------|-----------------------------------|
| `get_headers()`                 | —      | —                     | Returns `{"x-api-key": API_KEY}`  |
| `create_job(title, config)`     | POST   | `/jobs`               | Creates a new job config          |
| `get_jobs()`                    | GET    | `/jobs`               | Lists all jobs                    |
| `generate_job_config_ai(desc)`  | POST   | `/jobs/ai-generate`   | AI-generates a job config         |

All calls include the `x-api-key` header. All calls raise on non-2xx responses.

---

## Screening Pipeline

The full pipeline triggered by `POST /screening/start`:

```
1. Create ResumeRun record (status="running")
2. Read ZIP bytes from upload into memory
3. Background task: process_zip_and_screen()
   a. Write ZIP to temp directory, extract all files
   b. Walk temp dir → collect all .pdf and .docx files
   c. Update run.total_resumes with count found
   d. For each batch of batch_size resumes:
      For each resume in batch:
        i.   Compute MD5 hash → get_or_create_resume()
             (deduplicates resume_files table)
        ii.  Check if result already exists for this resume × job
             → If yes: insert a NEW ResumeResult row for the current run_id
                       but copy all fields (extracted_data, score, decision,
                       decision_reason) from the old result. ai_status="reused".
                       No AI call is made.
        iii. Else check if this resume was extracted for any other job
             → If yes: reuse extracted_data, only re-run scoring
        iv.  Else (brand new resume): extract text → call AI → get extracted_data
        v.   Score via scoring_engine.score_resume(job_config, extracted_data)
        vi.  decision = "shortlisted" if score >= 60 else "rejected"
        vii. Save ResumeResult to DB
        viii.Increment run.processed_count
   e. On any error per resume: increment failed_count, rollback, continue to next
4. Set run.status = "completed"
```

---

## Scoring Logic

```
score = 0

# Required skills
matched_required = |required_skills ∩ resume_skills|
score += (matched_required / total_required) × weight["required_skills"]

# Nice-to-have skills
matched_nice = |nice_to_have_skills ∩ resume_skills|
score += (matched_nice / total_nice) × weight["nice_to_have_skills"]

# Projects (capped)
for each project in resume:
    if project.domain in job.project_expectations.domains:
        project_score += 10
project_score = min(project_score, weight["projects"])
score += project_score

# Education
if any(resume_degree in job.education_requirements):
    score += weight["education"]

# Eligibility
if job.candidate_type in ("any", "student"):
    score += weight["eligibility"]

final_score = min(score, 100)
decision = "shortlisted" if final_score >= 60 else "rejected"
```

All text comparisons are normalized: lowercased, dots removed, slashes replaced with spaces.

---

## Configuration

### Backend — `.env`

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
GROQ_API_KEY=your_groq_api_key
API_KEY=your_secret_api_key
```

### Frontend — `.streamlit/secrets.toml`

```toml
APP_USERNAME = "admin"
APP_PASSWORD = "your_password"
BACKEND_URL = "http://localhost:8000"
API_KEY = "your_secret_api_key"
COMPANY_LOGO = "https://your-logo-url.png"

# Required for email pages (Brevo integration)
BREVO_API_KEY = "your_brevo_api_key"
BREVO_SENDER_EMAIL = "noreply@yourdomain.com"
BREVO_SENDER_NAME = "Your Company"
DATABASE_URL = "postgresql://user:password@host:5432/dbname"
```

**Note:** `DATABASE_URL` in the frontend secrets is the same PostgreSQL database as the backend. It is used directly by the email pages to read/write `email_logs`. Brevo IP allowlisting must be set to **Deactivated** in Brevo settings — Streamlit Cloud uses dynamic IPs that change on every redeploy.

---

## Installation & Running

### Backend

```bash
cd backend
pip install -r requirements.txt

# Create .env with required variables (see above)

uvicorn main:app --reload --port 8000
```

Swagger UI available at: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
pip install -r requirements.txt

# Create .streamlit/secrets.toml with required variables (see above)

streamlit run app.py
```

### Dependencies

**Backend (`requirements.txt`):**

| Package            | Purpose                              |
|--------------------|--------------------------------------|
| fastapi            | API framework                        |
| uvicorn            | ASGI server                          |
| sqlalchemy         | ORM for PostgreSQL                   |
| psycopg2-binary    | PostgreSQL driver                    |
| groq               | Groq API client (LLaMA access)       |
| python-dotenv      | Load environment variables from .env |
| pdfplumber         | PDF text extraction                  |
| python-docx        | DOCX text extraction                 |
| python-multipart   | Multipart file upload support        |
| openpyxl           | Excel file support                   |

**Frontend (`requirements.txt`):**

| Package          | Purpose                                  |
|------------------|------------------------------------------|
| streamlit        | UI framework                             |
| requests         | HTTP client                              |
| pandas           | Data manipulation                        |
| openpyxl         | Excel export                             |
| brevo-python==1.2.0 | Brevo API client (email sending + stats) |
| email-validator  | Validate recipient emails before sending |
| sqlalchemy       | ORM for email_logs table                 |
| psycopg2-binary  | PostgreSQL driver                        |

---

## Development & Testing Scripts

These are lightweight scripts used during development to verify the environment is set up correctly. They are not part of the application runtime.

### `backend/test_db.py`

Runs a raw `SELECT 1` query against the configured database to confirm the connection is alive.

```bash
cd backend
python test_db.py
# Output: Neon DB connection OK
```

### `backend/test_models.py`

Imports all four ORM models to confirm there are no import errors or misconfigured relationships.

```bash
cd backend
python test_models.py
# Output: Models imported successfully
```

---

## Known Gaps & Suggested Improvements

These are areas where the current implementation has known limitations or incomplete behavior. They are documented here to guide future development.

---

### 1. ~~`ended_at` is never set~~ ✅ Resolved

`run.ended_at` is set in both the happy path (`status = "completed"`) and the crash guard in the `finally` block. No action needed.

---

### 2. `version` and `is_active` fields have no backing logic

**Location:** `backend/db/models.py` → `JobConfig`

Both fields are defined in the model and default to `version=1` and `is_active=True`, but no API endpoint reads or updates them. There is no way to deactivate a job or version a config through the current API.

**Suggested fix:** Add a `PATCH /jobs/{job_id}` endpoint to toggle `is_active`. Filter out inactive jobs in `GET /jobs` and in `process_zip_and_screen()` so deactivated job configs cannot be screened against.

---

### 3. `file_path` in `resume_files` is always stale

**Location:** `backend/api/screening.py` → `get_or_create_resume()`

The `file_path` stored in `resume_files` points to a path inside a temporary directory created by `tempfile.TemporaryDirectory()`. That directory is deleted automatically when the context manager exits, so the stored path is never valid after the run finishes.

**Suggested fix:** Either remove the `file_path` column entirely (it serves no functional purpose currently), or implement persistent file storage (e.g., upload to S3/cloud storage) and store the permanent URL instead.

---

### 4. ~~Failed resumes leave no trace in `resume_results`~~ ✅ Resolved

Both `except` handlers now insert a `ResumeResult` row (when `resume_id` is available) with `ai_status="failed"` or `ai_status="rate_limited"` and `error_message=str(e)`, making every failure traceable per resume.

---

### 5. ~~Decision is computed twice~~ ✅ Resolved

`score_resume()` returns `(score, reason)` only — no decision. The `>= 60` threshold is computed in one place only (`screening.py`). No duplication exists.

---

### 6. MD5 used for file hashing

**Location:** `backend/api/screening.py` → `get_or_create_resume()`

MD5 is used to hash resume files for deduplication. While MD5 collisions are extremely rare for normal files, it is considered cryptographically weak.

**Suggested fix:** Replace `hashlib.md5` with `hashlib.sha256` for stronger collision resistance. No schema change needed — the `file_hash` column is a plain `Text` field.

---

### 7. Batch size hardcoded in frontend

**Location:** `frontend/app.py` → Tab 1

The batch size is hardcoded to `10` in the frontend POST request (`"batch_size": 10`). Even though the backend accepts it as a form parameter, the user has no way to change it from the UI.

**Suggested fix:** Add a number input widget in the Resume Screening tab to let the recruiter configure batch size before starting a run.

---

### 8. ~~No pagination on results endpoint~~ ✅ Resolved

`GET /screening/results/{job_id}` now accepts `limit` (default 500) and `offset` (default 0) query parameters. The SQLAlchemy query applies `.offset(offset).limit(limit)` before fetching. Frontend passes these params in `fetch_all_results()`.

---

### 9. `pool_pre_ping` in DB session

**Location:** `backend/db/session.py`

The SQLAlchemy engine is created with `pool_pre_ping=True`. This means before handing out a connection from the pool, SQLAlchemy issues a lightweight ping to check the connection is still alive. This is important when connecting to cloud-hosted databases (e.g., Neon, Supabase) that may close idle connections. It adds a tiny overhead per request but prevents `OperationalError: SSL connection has been closed unexpectedly` errors in production.

---

### 10. ~~Groq rate limit causes silent mid-run failures with no per-resume trace~~ ✅ Resolved

`groq.RateLimitError` is now caught separately before the generic `except Exception` handler. A `ResumeResult` row with `ai_status="rate_limited"` and the error message is inserted for each rate-limited resume (when `resume_id` is available). Rate-limited resumes are now distinguishable from other failures in the results.
