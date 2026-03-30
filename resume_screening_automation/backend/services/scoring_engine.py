from datetime import datetime

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
DEFAULT_SHORTLIST_THRESHOLD = 60
POINTS_PER_RELEVANT_PROJECT = 10

# ---------------------------------------------------------------------------
# SKILL ALIAS MAP  (alias -> canonical form)
# ---------------------------------------------------------------------------
SKILL_ALIASES: dict[str, str] = {
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node",
    "node.js": "node",
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "cpp": "c++",
    "csharp": "c#",
    "mongo": "mongodb",
}

# ---------------------------------------------------------------------------
# EDUCATION ALIAS MAP  (alias -> canonical long form)
# ---------------------------------------------------------------------------
EDUCATION_ALIASES: dict[str, str] = {
    "btech": "bachelor of technology",
    "b.tech": "bachelor of technology",
    "b tech": "bachelor of technology",
    "mtech": "master of technology",
    "m.tech": "master of technology",
    "m tech": "master of technology",
    "bsc": "bachelor of science",
    "b.sc": "bachelor of science",
    "b sc": "bachelor of science",
    "msc": "master of science",
    "m.sc": "master of science",
    "m sc": "master of science",
    "mba": "master of business administration",
    "m.b.a": "master of business administration",
    "be": "bachelor of engineering",
    "b.e": "bachelor of engineering",
    "me": "master of engineering",
    "m.e": "master of engineering",
    "bca": "bachelor of computer applications",
    "b.c.a": "bachelor of computer applications",
    "mca": "master of computer applications",
    "m.c.a": "master of computer applications",
    "phd": "doctor of philosophy",
    "ph.d": "doctor of philosophy",
}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """
    Normalize text for comparison:
    - lowercase
    - strip whitespace
    """
    return text.lower().strip()


def _canonicalize_skill(raw: str) -> set[str]:
    """Return a set of canonical tokens for a single skill string.

    For example "React.js" produces {"react", "reactjs", "react.js", "react", "js"}
    after alias resolution.  We keep every useful form so that fuzzy
    token-overlap matching works well.
    """
    normed = normalize(raw)

    # Resolve alias first (on the full normalized string)
    canonical = SKILL_ALIASES.get(normed, normed)

    # Build token set: full canonical string + individual word tokens
    tokens: set[str] = set()
    tokens.add(canonical)

    # Also add individual tokens split on common separators
    for sep in (" ", ".", "/", "-"):
        if sep in canonical:
            tokens.update(t for t in canonical.split(sep) if t)

    # Resolve aliases for each token too
    resolved: set[str] = set()
    for t in tokens:
        resolved.add(SKILL_ALIASES.get(t, t))
    return resolved


def _skill_matches(required_skill: str, resume_skills_tokens: set[str]) -> bool:
    """Check if a required skill fuzzy-matches any of the resume skill tokens."""
    required_tokens = _canonicalize_skill(required_skill)
    return bool(required_tokens & resume_skills_tokens)


def _build_resume_skill_tokens(resume_skills: list[str]) -> set[str]:
    """Build a flat set of canonical tokens from all resume skills."""
    tokens: set[str] = set()
    for skill in resume_skills:
        tokens.update(_canonicalize_skill(skill))
    return tokens


def _canonicalize_degree(raw: str) -> set[str]:
    """Return a set of canonical forms for a degree string.

    E.g. "B.Tech" -> {"btech", "b.tech", "bachelor of technology"}
    """
    normed = normalize(raw)

    forms: set[str] = set()
    forms.add(normed)

    # Remove dots for an additional form  ("b.tech" -> "btech")
    no_dots = normed.replace(".", "").replace("/", " ").strip()
    forms.add(no_dots)

    # Resolve aliases for every form we have so far
    resolved: set[str] = set()
    for f in forms:
        alias_val = EDUCATION_ALIASES.get(f)
        if alias_val:
            resolved.add(alias_val)
    forms.update(resolved)

    return forms


def _education_matches(
    allowed_degrees: list[str], resume_degrees: list[str]
) -> bool:
    """Return True if any resume degree fuzzy-matches any allowed degree."""
    allowed_canonical: set[str] = set()
    for d in allowed_degrees:
        allowed_canonical.update(_canonicalize_degree(d))

    for d in resume_degrees:
        resume_forms = _canonicalize_degree(d)
        if resume_forms & allowed_canonical:
            return True
    return False


def get_shortlist_threshold(job_config: dict) -> int:
    """Return the shortlist threshold from job_config, falling back to the
    default constant."""
    return int(job_config.get("shortlist_threshold", DEFAULT_SHORTLIST_THRESHOLD))


# ---------------------------------------------------------------------------
# MAIN SCORING FUNCTION
# ---------------------------------------------------------------------------

def score_resume(job_config: dict, extracted_data: dict) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []

    weights = job_config.get("scoring_weights", {})

    # -----------------------------------------------------------------
    # 1. REQUIRED SKILLS  (fuzzy token-overlap matching)
    # -----------------------------------------------------------------
    required_skills_raw = job_config.get("required_skills", [])
    resume_skills_raw = extracted_data.get("skills") or []
    resume_skill_tokens = _build_resume_skill_tokens(resume_skills_raw)

    if required_skills_raw:
        matched = sum(
            1
            for s in required_skills_raw
            if _skill_matches(s, resume_skill_tokens)
        )
        skill_score = int(
            (matched / len(required_skills_raw))
            * weights.get("required_skills", 0)
        )
        score += skill_score
        reasons.append(
            f"Required skills matched {matched}/{len(required_skills_raw)}"
        )

    # -----------------------------------------------------------------
    # 2. NICE-TO-HAVE SKILLS  (fuzzy token-overlap matching)
    # -----------------------------------------------------------------
    nice_skills_raw = job_config.get("nice_to_have_skills", [])

    if nice_skills_raw:
        matched = sum(
            1
            for s in nice_skills_raw
            if _skill_matches(s, resume_skill_tokens)
        )
        nice_score = int(
            (matched / len(nice_skills_raw))
            * weights.get("nice_to_have_skills", 0)
        )
        score += nice_score
        reasons.append(
            f"Nice-to-have skills matched {matched}/{len(nice_skills_raw)}"
        )

    # -----------------------------------------------------------------
    # 3. PROJECTS  (capped to weight)
    # -----------------------------------------------------------------
    project_score = 0

    job_domains = {
        normalize(d)
        for d in job_config.get("project_expectations", {}).get("domains", [])
    }

    for project in extracted_data.get("projects") or []:
        project_domain = normalize(project.get("domain", ""))
        if project_domain in job_domains:
            project_score += POINTS_PER_RELEVANT_PROJECT

    project_weight = weights.get("projects", 0)
    project_score = min(project_score, project_weight)

    score += project_score
    reasons.append(f"Project score {project_score}")

    # -----------------------------------------------------------------
    # 4. EDUCATION  (fuzzy alias matching)
    # -----------------------------------------------------------------
    allowed_degrees_raw = job_config.get("education_requirements", [])
    resume_degrees_raw = [
        e.get("degree", "")
        for e in extracted_data.get("education") or []
    ]

    if allowed_degrees_raw and _education_matches(
        allowed_degrees_raw, resume_degrees_raw
    ):
        edu_score = weights.get("education", 0)
        score += edu_score
        reasons.append("Education requirement met")

    # -----------------------------------------------------------------
    # 5. ELIGIBILITY  (smarter candidate-type logic)
    # -----------------------------------------------------------------
    candidate_type = normalize(job_config.get("candidate_type", "any"))
    elig_weight = weights.get("eligibility", 0)
    experience_years = extracted_data.get("experience_years") or 0
    passed_out_year = extracted_data.get("passed_out_year")

    if candidate_type == "any":
        # "any" means no restriction -- full points
        score += elig_weight
        reasons.append("Eligibility met (open to any candidate type)")

    elif candidate_type == "experienced":
        if experience_years > 0:
            score += elig_weight
            reasons.append(
                f"Eligibility met (experienced, {experience_years} yrs)"
            )
        else:
            reasons.append("Eligibility not met (expected experienced candidate)")

    elif candidate_type == "student":
        is_recent_grad = False
        if passed_out_year is not None:
            try:
                current_year = datetime.now().year
                is_recent_grad = int(passed_out_year) >= current_year - 2
            except (ValueError, TypeError):
                pass

        if experience_years <= 2 or is_recent_grad:
            score += elig_weight
            reasons.append("Eligibility met (student / recent graduate)")
        else:
            reasons.append("Eligibility not met (expected student / recent grad)")

    else:
        # Unknown candidate_type -- no points, no penalty
        reasons.append(f"Eligibility skipped (unknown type '{candidate_type}')")

    # -----------------------------------------------------------------
    # FINALIZE
    # -----------------------------------------------------------------
    final_score = min(int(score), 100)

    return final_score, "; ".join(reasons)
