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


def score_resume(job_config: dict, extracted_data: dict) -> tuple[int, str]:
    score = 0
    reasons = []

    weights = job_config.get("scoring_weights", {})

    # -------------------------------------------------
    # 1️⃣ REQUIRED SKILLS
    # -------------------------------------------------
    required_skills = {
        normalize(s) for s in job_config.get("required_skills", [])
    }
    resume_skills = {
        normalize(s) for s in extracted_data.get("skills") or []
    }

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
        normalize(s) for s in job_config.get("nice_to_have_skills", [])
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
        project_domain = normalize(project.get("domain", ""))

        if project_domain in job_domains:
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
        normalize(d)
        for d in job_config.get("education_requirements", [])
    }
    resume_degrees = {
        normalize(e.get("degree", ""))
        for e in extracted_data.get("education") or []
    }

    if allowed_degrees & resume_degrees:
        edu_score = weights.get("education", 0)
        score += edu_score
        reasons.append("Education requirement met")

    # -------------------------------------------------
    # 5️⃣ ELIGIBILITY
    # -------------------------------------------------
    candidate_type   = job_config.get("candidate_type", "any")
    required_exp     = job_config.get("required_experience_years")
    resume_exp       = extracted_data.get("experience_years") or 0
    elig_weight      = weights.get("eligibility", 0)
    disqualified     = False
    disqualify_reason = None

    if candidate_type == "student" and resume_exp > 0:
        disqualified      = True
        disqualify_reason = f"Not a student (resume shows {resume_exp} yrs experience)"

    elif candidate_type == "experienced" or required_exp is not None:
        min_exp = required_exp if required_exp is not None else 1
        if resume_exp < min_exp:
            disqualified      = True
            disqualify_reason = f"Insufficient experience: {resume_exp} yrs (required {min_exp} yrs)"

    if disqualified:
        reasons.insert(0, disqualify_reason)
    else:
        score += elig_weight
        reasons.append("Eligibility requirement met")

    # -------------------------------------------------
    # FINALIZE
    # -------------------------------------------------
    final_score = min(int(score), 100)

    return final_score, "; ".join(reasons)
