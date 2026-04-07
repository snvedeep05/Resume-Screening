# Canonical skill aliases — keys are variants, value is the canonical form.
# Both job config and resume skills are resolved to canonical before matching.
# Canonical degree groups — any degree in the same group matches any other.
_DEGREE_GROUPS: list[set[str]] = [
    {"btech", "be", "bachelor of technology", "bachelor of engineering",
     "bachelors", "bachelor", "bachelor of science", "bs", "bsc",
     "bachelor of computer science", "bca", "bachelor of computer applications",
     "b tech", "b e", "b sc", "b s"},
    {"mtech", "me", "master of technology", "master of engineering",
     "masters", "master", "master of science", "ms", "msc",
     "master of computer science", "mca", "master of computer applications",
     "m tech", "m e", "m sc", "m s"},
    {"mba", "master of business administration", "pgdm"},
    {"phd", "ph d", "doctorate", "doctor of philosophy"},
    {"diploma", "polytechnic"},
    {"12th", "hsc", "higher secondary", "intermediate", "plus two", "+2"},
    {"10th", "ssc", "secondary", "matriculation"},
]


def _degree_canonical(degree_norm: str) -> str:
    """Return a canonical group ID for a degree, or the degree itself if unknown."""
    for i, group in enumerate(_DEGREE_GROUPS):
        if degree_norm in group:
            return f"__group_{i}__"
    return degree_norm


_SKILL_ALIASES: dict[str, str] = {
    "js":                   "javascript",
    "node":                 "nodejs",
    "node js":              "nodejs",
    "node.js":              "nodejs",
    "react js":             "reactjs",
    "react.js":             "reactjs",
    "vue js":               "vuejs",
    "vue.js":               "vuejs",
    "ts":                   "typescript",
    "py":                   "python",
    "ml":                   "machine learning",
    "dl":                   "deep learning",
    "ai":                   "artificial intelligence",
    "nlp":                  "natural language processing",
    "cv":                   "computer vision",
    "c sharp":              "c#",
    "csharp":               "c#",
    "c plus plus":          "c++",
    "golang":               "go",
    "k8s":                  "kubernetes",
    "postgres":             "postgresql",
    "mongo":                "mongodb",
    "aws":                  "amazon web services",
    "gcp":                  "google cloud platform",
    "azure":                "microsoft azure",
    "rest":                 "rest api",
    "restful":              "rest api",
    "rest apis":            "rest api",
    "restful apis":         "rest api",
    "oop":                  "object oriented programming",
    "object oriented":      "object oriented programming",
    "data structures":      "data structures and algorithms",
    "dsa":                  "data structures and algorithms",
    "os":                   "operating systems",
    "dbms":                 "database management systems",
    "sql server":           "microsoft sql server",
    "mssql":                "microsoft sql server",
    "scss":                 "css",
    "sass":                 "css",
    "html5":                "html",
    "css3":                 "css",
    "es6":                  "javascript",
    "es2015":               "javascript",
    "next":                 "nextjs",
    "next js":              "nextjs",
    "next.js":              "nextjs",
    "nuxt":                 "nuxtjs",
    "nuxt.js":              "nuxtjs",
    "express":              "expressjs",
    "express.js":           "expressjs",
    "flask":                "flask",
    "django rest framework": "django",
    "drf":                  "django",
    "tf":                   "tensorflow",
    "sklearn":              "scikit-learn",
    "scikit learn":         "scikit-learn",
    "pandas":               "pandas",
    "numpy":                "numpy",
}


def normalize(text: str) -> str:
    """
    Normalize text for comparison:
    - lowercase
    - remove dots
    - replace slashes with space
    """
    return (
        text.lower()
        .replace(".", "")
        .replace("/", " ")
        .strip()
    )


def resolve_skill(text: str) -> str:
    """Normalize then apply alias resolution so 'JS' matches 'JavaScript'."""
    n = normalize(text)
    return _SKILL_ALIASES.get(n, n)


def expand_skills(skill_set: set[str]) -> set[str]:
    """
    Expand a set of normalized skill strings by adding all aliases that
    resolve to any skill already in the set, so matching works both ways.
    E.g. if 'javascript' is in the set, 'js' / 'es6' also become valid.
    """
    resolved = {resolve_skill(s) for s in skill_set}
    # Build reverse map: canonical → all its variants
    for variant, canonical in _SKILL_ALIASES.items():
        if canonical in resolved:
            resolved.add(variant)
    return resolved


_EXPECTED_WEIGHT_KEYS = {
    "required_skills", "nice_to_have_skills", "projects", "education", "eligibility"
}


def score_resume(job_config: dict, extracted_data: dict) -> tuple[int, str, bool]:
    """
    Returns (score, reason_string, disqualified).
    disqualified=True means the candidate must be rejected regardless of score.
    """
    score = 0
    reasons = []

    weights = job_config.get("scoring_weights", {})

    # Warn about misconfigured weights (logged, not raised — screening must not crash)
    missing_keys = _EXPECTED_WEIGHT_KEYS - set(weights.keys())
    if missing_keys:
        print(f"[scoring] WARNING: scoring_weights missing keys {missing_keys} — they default to 0")
    weight_total = sum(weights.get(k, 0) for k in _EXPECTED_WEIGHT_KEYS)
    if weight_total != 100:
        print(f"[scoring] WARNING: scoring_weights sum to {weight_total}, not 100")

    # -------------------------------------------------
    # 1️⃣ REQUIRED SKILLS
    # -------------------------------------------------
    required_skills = {
        resolve_skill(s) for s in job_config.get("required_skills", [])
    }
    resume_skills = expand_skills({
        normalize(s) for s in extracted_data.get("skills") or []
    })

    if required_skills:
        matched = len(required_skills & resume_skills)
        skill_score = int(
            (matched / len(required_skills)) * weights.get("required_skills", 0)
        )
        score += skill_score
        reasons.append(
            f"Required skills matched {matched}/{len(required_skills)}"
        )

    # -------------------------------------------------
    # 2️⃣ NICE TO HAVE SKILLS
    # -------------------------------------------------
    nice_skills = {
        resolve_skill(s) for s in job_config.get("nice_to_have_skills", [])
    }

    if nice_skills:
        matched = len(nice_skills & resume_skills)
        nice_score = int(
            (matched / len(nice_skills)) * weights.get("nice_to_have_skills", 0)
        )
        score += nice_score
        reasons.append(
            f"Nice-to-have skills matched {matched}/{len(nice_skills)}"
        )

    # -------------------------------------------------
    # 3️⃣ PROJECTS (CAPPED)
    # -------------------------------------------------
    project_score = 0

    job_domains = {
        normalize(d)
        for d in job_config
        .get("project_expectations", {})
        .get("domains", [])
    }

    for project in extracted_data.get("projects") or []:
        # normalize turns "web/backend" → "web backend"; split so each token
        # is checked individually against job_domains
        project_domain_tokens = normalize(project.get("domain", "")).split()
        if any(token in job_domains for token in project_domain_tokens):
            project_score += 10  # raw points per relevant project

    # 🔒 CAP PROJECT SCORE TO WEIGHT
    project_weight = weights.get("projects", 0)
    project_score = min(project_score, project_weight)

    score += project_score
    reasons.append(f"Project score {project_score}")

    # -------------------------------------------------
    # 4️⃣ EDUCATION
    # -------------------------------------------------
    allowed_degrees = {
        _degree_canonical(normalize(d))
        for d in job_config.get("education_requirements", [])
    }
    resume_degrees = {
        _degree_canonical(normalize(e.get("degree", "")))
        for e in extracted_data.get("education") or []
    }

    if allowed_degrees & resume_degrees:
        edu_score = weights.get("education", 0)
        score += edu_score
        reasons.append("Education requirement met")

    # -------------------------------------------------
    # 5️⃣ ELIGIBILITY
    # -------------------------------------------------
    candidate_type    = job_config.get("candidate_type", "any")
    required_exp      = job_config.get("required_experience_years")
    max_exp           = job_config.get("max_experience_years")
    # None means AI couldn't determine experience — treat as 0 for comparisons
    # but note the ambiguity in the reason string
    raw_exp           = extracted_data.get("experience_years")
    resume_exp        = raw_exp if raw_exp is not None else 0
    exp_unknown       = raw_exp is None
    elig_weight       = weights.get("eligibility", 0)
    disqualified      = False
    disqualify_reason = None

    if candidate_type == "student" and resume_exp > 0:
        disqualified      = True
        disqualify_reason = f"Not a student (resume shows {resume_exp} yrs experience)"

    elif candidate_type == "experienced" or required_exp is not None:
        min_exp = required_exp if required_exp is not None else 1
        exp_label = "unknown" if exp_unknown else f"{resume_exp} yrs"
        if resume_exp < min_exp:
            disqualified      = True
            disqualify_reason = f"Insufficient experience: {exp_label} (required {min_exp} yrs)"
        elif max_exp is not None and resume_exp > max_exp:
            disqualified      = True
            disqualify_reason = f"Overqualified: {exp_label} experience (max {max_exp} yrs)"

    if disqualified:
        reasons.insert(0, disqualify_reason)
    else:
        score += elig_weight
        reasons.append("Eligibility requirement met")

    # -------------------------------------------------
    # FINALIZE
    # -------------------------------------------------
    final_score = min(int(score), 100)

    return final_score, "; ".join(reasons), disqualified
