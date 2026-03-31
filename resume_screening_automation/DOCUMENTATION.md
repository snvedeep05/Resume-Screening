# Resume Screening Automation

AI-powered resume screening system that automates candidate evaluation against job requirements.

## Architecture

```
resume_screening_automation/
├── backend/          # FastAPI REST API
│   ├── api/          # Route handlers
│   ├── db/           # SQLAlchemy models + session
│   ├── services/     # Business logic
│   ├── prompts/      # LLM prompt templates
│   ├── alembic/      # Database migrations
│   ├── tests/        # Pytest test suite
│   ├── main.py       # App entrypoint
│   ├── schemas.py    # Pydantic request models
│   └── security.py   # API key auth
├── web/              # Next.js frontend
│   └── src/
│       ├── app/      # Pages (Jobs, Screening, Results)
│       └── lib/      # API client
└── frontend/         # Legacy Streamlit UI (deprecated)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Database | PostgreSQL |
| AI/LLM | Groq API (llama-3.1-8b-instant) |
| Auth | API key via `x-api-key` header |

## Environment Variables

### Backend (`backend/.env`)
```
DATABASE_URL=postgresql://user:pass@localhost:5432/resume_screening
GROQ_API_KEY=your_groq_api_key
API_KEY=your_api_key_for_auth
```

### Frontend (`web/.env.local`)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=your_api_key_for_auth
```

## Running Locally

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
```bash
cd web
npm install
npm run dev
```

### Database Migrations
```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

## API Reference

All endpoints require `x-api-key` header (except `/health`).

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/jobs` | Create a job |
| GET | `/jobs` | List active jobs |
| GET | `/jobs/{job_id}` | Get job details |
| PATCH | `/jobs/{job_id}` | Update job (creates new version) |
| POST | `/jobs/ai-generate` | AI-generate job config from JD |

#### POST `/jobs`
```json
// Request
{ "job_title": "Data Engineer", "job_config": {} }

// Response
{ "job_id": 1 }
```

#### POST `/jobs/ai-generate`
```json
// Request
{ "job_description": "Looking for a data engineer with Python, SQL..." }

// Response
{
  "job_config": {
    "required_skills": ["python", "sql"],
    "nice_to_have_skills": ["spark", "airflow"],
    "education_requirements": ["bachelor of technology"],
    "candidate_type": "experienced",
    "project_expectations": { "domains": ["data", "backend"] },
    "scoring_weights": {
      "required_skills": 35,
      "nice_to_have_skills": 15,
      "projects": 20,
      "education": 15,
      "eligibility": 15
    }
  }
}
```

### Screening

| Method | Path | Description |
|--------|------|-------------|
| POST | `/screening/start` | Bulk screen (zip upload) |
| POST | `/screening/upload-single` | Screen single resume |
| GET | `/screening/runs/{run_id}` | Get run status |

#### POST `/screening/start`
Multipart form: `job_id` (int), `batch_size` (int), `zip_file` (file)
```json
// Response
{ "run_id": 1, "status": "started" }
```

#### POST `/screening/upload-single`
Multipart form: `job_id` (int), `resume_file` (PDF/DOCX)
```json
// Response
{ "run_id": 2, "status": "started" }
```

#### GET `/screening/runs/{run_id}`
```json
{
  "run_id": 1,
  "status": "completed",
  "total_resumes": 50,
  "processed_count": 48,
  "failed_count": 2,
  "started_at": "2026-03-30T10:00:00",
  "ended_at": "2026-03-30T10:05:00"
}
```

### Results

| Method | Path | Description |
|--------|------|-------------|
| GET | `/screening/results/job/{job_id}` | Get results with filters |
| GET | `/screening/results/job/{job_id}/export` | Export CSV |
| PATCH | `/screening/results/bulk` | Bulk update decisions |
| PATCH | `/screening/results/{result_id}` | Update single decision |
| GET | `/screening/results/{result_id}/history` | Decision audit trail |

#### GET `/screening/results/job/{job_id}`
Query params: `search`, `decision`, `min_score`, `max_score`, `limit`, `offset`
```json
[
  {
    "result_id": 1,
    "candidate_id": 5,
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "+91-9876543210",
    "job_title": "Data Engineer",
    "passed_out_year": 2023,
    "score": 78,
    "decision": "shortlisted",
    "decision_reason": "Required skills matched 4/5; Education requirement met",
    "processed_at": "2026-03-30T10:02:00"
  }
]
```

#### PATCH `/screening/results/bulk`
```json
// Request
{ "result_ids": [1, 2, 3], "decision": "shortlisted", "reason": "Good fit" }

// Response
{ "updated": [1, 2, 3], "count": 3 }
```

#### GET `/screening/results/{result_id}/history`
```json
[
  {
    "audit_id": 1,
    "old_decision": "rejected",
    "new_decision": "shortlisted",
    "changed_at": "2026-03-30T11:00:00",
    "reason": "Reconsidered after interview"
  }
]
```

---

## Database Schema

### candidates
| Column | Type | Constraints |
|--------|------|-------------|
| candidate_id | INT | PK, auto-increment |
| email | TEXT | UNIQUE, nullable |
| phone | TEXT | nullable |
| full_name | TEXT | nullable |
| created_at | TIMESTAMP | default now() |
| updated_at | TIMESTAMP | default now(), auto-update |

### job_configs
| Column | Type | Constraints |
|--------|------|-------------|
| job_id | INT | PK, auto-increment |
| job_title | TEXT | NOT NULL |
| job_config | JSON | NOT NULL |
| version | INT | default 1 |
| is_active | BOOL | default TRUE |
| created_at | TIMESTAMP | default now() |

### resume_runs
| Column | Type | Constraints |
|--------|------|-------------|
| run_id | INT | PK, auto-increment |
| job_id | INT | FK → job_configs |
| batch_size | INT | NOT NULL |
| total_resumes | INT | NOT NULL |
| processed_count | INT | default 0 |
| failed_count | INT | default 0 |
| status | TEXT | default "running" |
| started_at | TIMESTAMP | default now() |
| ended_at | TIMESTAMP | nullable |

### resume_files
| Column | Type | Constraints |
|--------|------|-------------|
| resume_id | INT | PK, auto-increment |
| file_name | TEXT | NOT NULL |
| file_hash | TEXT | UNIQUE, NOT NULL (SHA-256) |
| file_path | TEXT | nullable |
| uploaded_at | TIMESTAMP | default now() |

### resume_results
| Column | Type | Constraints |
|--------|------|-------------|
| result_id | INT | PK, auto-increment |
| run_id | INT | FK → resume_runs |
| resume_id | INT | FK → resume_files |
| job_id | INT | FK → job_configs |
| candidate_id | INT | FK → candidates, nullable |
| extracted_data | JSON | nullable |
| score | INT | nullable (0-100) |
| decision | TEXT | "shortlisted" or "rejected" |
| decision_reason | TEXT | nullable |
| passed_out_year | INT | nullable |
| ai_status | TEXT | success/reused/rate_limited/failed |
| error_message | TEXT | nullable |
| processed_at | TIMESTAMP | default now() |

### decision_audit
| Column | Type | Constraints |
|--------|------|-------------|
| audit_id | INT | PK, auto-increment |
| result_id | INT | FK → resume_results |
| old_decision | TEXT | nullable |
| new_decision | TEXT | NOT NULL |
| changed_at | TIMESTAMP | default now() |
| reason | TEXT | nullable |

---

## Scoring Engine

### How Scoring Works

Each resume is scored 0-100 against a job config. The score is a weighted sum of 5 components:

| Component | What it checks | Matching |
|-----------|---------------|----------|
| Required Skills | Resume skills vs job required skills | Fuzzy (token overlap + aliases) |
| Nice-to-Have Skills | Resume skills vs preferred skills | Fuzzy (token overlap + aliases) |
| Projects | Resume project domains vs job domains | Exact domain match |
| Education | Resume degrees vs required degrees | Fuzzy (abbreviation aliases) |
| Eligibility | Candidate type (student/experienced/any) | Rule-based |

Weights are defined per job config and must sum to 100.

### Fuzzy Matching

**Skill aliases** — common variations are normalized:
- `reactjs`, `react.js` → `react`
- `nodejs`, `node.js` → `node`
- `js` → `javascript`, `ts` → `typescript`
- `postgres` → `postgresql`, `mongo` → `mongodb`
- `k8s` → `kubernetes`, `cpp` → `c++`, `csharp` → `c#`

**Education aliases** — degree abbreviations are expanded:
- `btech`, `b.tech` → `bachelor of technology`
- `mba` → `master of business administration`
- `bsc` → `bachelor of science`
- `phd` → `doctor of philosophy`
- And more (be, me, bca, mca, msc, mtech)

### Shortlist Threshold

Default: **60** (configurable per job via `job_config.shortlist_threshold`)

Score >= threshold → `shortlisted`, otherwise → `rejected`

---

## Deduplication

### File-level
Same file uploaded twice (same SHA-256 hash) → reuses existing `resume_id`. Extraction is skipped if already processed.

### Cross-job
If a resume was extracted for Job A, the extracted data is reused when screening for Job B. Only scoring is re-run.

### Candidate-level
After extraction, candidates are deduplicated by:
1. **Email** (primary identifier) — if email matches, same candidate
2. **Phone** (fallback) — if no email but phone matches, same candidate
3. **New** — if neither matches, new candidate record

---

## LLM Prompts

### Job Config Generation
Given a job description, the LLM outputs:
- `required_skills` / `nice_to_have_skills` — skill arrays
- `education_requirements` — degree requirements
- `candidate_type` — student / experienced / any
- `project_expectations.domains` — relevant project domains
- `scoring_weights` — integer weights summing to 100

### Resume Extraction
Given resume text, the LLM outputs:
- `personal_details` — name, email, phone
- `skills` — skill list
- `education` — array of {degree, field, institution, passed_out_year}
- `projects` — array of {title, domain, tech_stack}
- `experience_years` — numeric
- `passed_out_year` — most recent graduation year

Both prompts enforce strict JSON output with no hallucination.

---

## Frontend Pages

### Jobs Dashboard (`/`)
- List all active jobs
- Create new job with AI-generated config from JD
- Click job to view results

### Job Results (`/jobs/{id}`)
- Results table with columns: Name, Email, Phone, Score, Year, Decision, Reason
- **Search** by name or email
- **Filter** by decision (shortlisted/rejected) and minimum score
- **Bulk actions**: select multiple → shortlist/reject all
- **Individual actions**: shortlist/reject per row
- **Export CSV**: download filtered results
- **View Config**: toggle job config JSON

### Screen Resumes (`/screening`)
- Select job from dropdown
- Choose upload mode: Zip (bulk) or Single Resume
- Set batch size (for zip)
- Upload file and start screening
- **Live progress**: status indicator, counts, progress bar (polls every 2s)

---

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

**66 tests** covering:
- Scoring engine: normalization, skill aliases, fuzzy matching, education matching, candidate types, thresholds, end-to-end scoring
- Schemas: Pydantic validation for all request models
