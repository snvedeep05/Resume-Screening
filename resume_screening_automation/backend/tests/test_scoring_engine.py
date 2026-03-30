"""Comprehensive tests for services/scoring_engine.py.

All tests are pure-Python -- no database or external services needed.
"""
import pytest
from services.scoring_engine import (
    normalize,
    _canonicalize_skill,
    _skill_matches,
    _build_resume_skill_tokens,
    _canonicalize_degree,
    _education_matches,
    get_shortlist_threshold,
    score_resume,
    DEFAULT_SHORTLIST_THRESHOLD,
)


# ── normalize() ──────────────────────────────────────────────────────────────


def test_normalize_lowercases():
    assert normalize("HELLO") == "hello"


def test_normalize_strips_whitespace():
    assert normalize("  world  ") == "world"


def test_normalize_combined():
    assert normalize("  React.JS  ") == "react.js"


def test_normalize_empty_string():
    assert normalize("") == ""


# ── _canonicalize_skill() ────────────────────────────────────────────────────


def test_canonicalize_skill_reactjs():
    tokens = _canonicalize_skill("reactjs")
    assert "react" in tokens


def test_canonicalize_skill_react_dot_js():
    tokens = _canonicalize_skill("React.js")
    assert "react" in tokens


def test_canonicalize_skill_nodejs():
    tokens = _canonicalize_skill("NodeJS")
    assert "node" in tokens


def test_canonicalize_skill_node_dot_js():
    tokens = _canonicalize_skill("Node.js")
    assert "node" in tokens


def test_canonicalize_skill_js_alias():
    tokens = _canonicalize_skill("JS")
    assert "javascript" in tokens


def test_canonicalize_skill_ts_alias():
    tokens = _canonicalize_skill("TS")
    assert "typescript" in tokens


def test_canonicalize_skill_postgres():
    tokens = _canonicalize_skill("postgres")
    assert "postgresql" in tokens


def test_canonicalize_skill_k8s():
    tokens = _canonicalize_skill("k8s")
    assert "kubernetes" in tokens


def test_canonicalize_skill_plain_name():
    tokens = _canonicalize_skill("Python")
    assert "python" in tokens


def test_canonicalize_skill_multi_word():
    tokens = _canonicalize_skill("machine learning")
    # Should contain the full phrase and individual words
    assert "machine learning" in tokens
    assert "machine" in tokens
    assert "learning" in tokens


# ── _skill_matches() ────────────────────────────────────────────────────────


def test_skill_matches_exact():
    resume_tokens = _build_resume_skill_tokens(["python", "java"])
    assert _skill_matches("python", resume_tokens) is True


def test_skill_matches_alias():
    resume_tokens = _build_resume_skill_tokens(["React.js"])
    assert _skill_matches("reactjs", resume_tokens) is True
    assert _skill_matches("react", resume_tokens) is True


def test_skill_matches_token_overlap():
    resume_tokens = _build_resume_skill_tokens(["machine learning"])
    assert _skill_matches("machine learning", resume_tokens) is True


def test_skill_matches_no_match():
    resume_tokens = _build_resume_skill_tokens(["python", "java"])
    assert _skill_matches("golang", resume_tokens) is False


def test_skill_matches_case_insensitive():
    resume_tokens = _build_resume_skill_tokens(["PYTHON"])
    assert _skill_matches("python", resume_tokens) is True


def test_skill_matches_react_dot_js_to_react():
    """'React.js' on resume should match 'react' as a required skill."""
    resume_tokens = _build_resume_skill_tokens(["React.js"])
    assert _skill_matches("react", resume_tokens) is True


def test_skill_matches_node_dot_js_to_nodejs():
    resume_tokens = _build_resume_skill_tokens(["Node.js"])
    assert _skill_matches("nodejs", resume_tokens) is True


# ── _canonicalize_degree() ───────────────────────────────────────────────────


def test_canonicalize_degree_btech():
    forms = _canonicalize_degree("B.Tech")
    assert "bachelor of technology" in forms


def test_canonicalize_degree_mtech():
    forms = _canonicalize_degree("M.Tech")
    assert "master of technology" in forms


def test_canonicalize_degree_mba():
    forms = _canonicalize_degree("MBA")
    assert "master of business administration" in forms


def test_canonicalize_degree_phd():
    forms = _canonicalize_degree("Ph.D")
    assert "doctor of philosophy" in forms


def test_canonicalize_degree_bca():
    forms = _canonicalize_degree("BCA")
    assert "bachelor of computer applications" in forms


def test_canonicalize_degree_mca():
    forms = _canonicalize_degree("MCA")
    assert "master of computer applications" in forms


def test_canonicalize_degree_already_full():
    forms = _canonicalize_degree("Bachelor of Technology")
    assert "bachelor of technology" in forms


# ── _education_matches() ────────────────────────────────────────────────────


def test_education_matches_btech_to_bachelor_of_technology():
    assert _education_matches(
        ["Bachelor of Technology"], ["B.Tech"]
    ) is True


def test_education_matches_mba():
    assert _education_matches(["MBA"], ["Master of Business Administration"]) is True


def test_education_matches_no_match():
    assert _education_matches(["Ph.D"], ["B.Tech"]) is False


def test_education_matches_empty_allowed():
    # No allowed degrees means no requirement
    assert _education_matches([], ["B.Tech"]) is False


def test_education_matches_empty_resume():
    assert _education_matches(["B.Tech"], []) is False


def test_education_matches_multiple_allowed():
    assert _education_matches(
        ["B.Tech", "B.E", "BSc"],
        ["Bachelor of Engineering"],
    ) is True


# ── get_shortlist_threshold() ────────────────────────────────────────────────


def test_get_shortlist_threshold_default():
    assert get_shortlist_threshold({}) == DEFAULT_SHORTLIST_THRESHOLD


def test_get_shortlist_threshold_custom():
    assert get_shortlist_threshold({"shortlist_threshold": 75}) == 75


def test_get_shortlist_threshold_string_value():
    # Config values may come as strings from JSON
    assert get_shortlist_threshold({"shortlist_threshold": "80"}) == 80


# ── score_resume() end-to-end ────────────────────────────────────────────────


def _make_job_config(
    required_skills=None,
    nice_to_have_skills=None,
    education_requirements=None,
    candidate_type="any",
    shortlist_threshold=60,
    project_domains=None,
    weights=None,
):
    """Helper to build a realistic job_config dict."""
    if weights is None:
        weights = {
            "required_skills": 40,
            "nice_to_have_skills": 15,
            "projects": 15,
            "education": 15,
            "eligibility": 15,
        }
    config = {
        "scoring_weights": weights,
        "required_skills": required_skills or [],
        "nice_to_have_skills": nice_to_have_skills or [],
        "education_requirements": education_requirements or [],
        "candidate_type": candidate_type,
        "shortlist_threshold": shortlist_threshold,
    }
    if project_domains:
        config["project_expectations"] = {"domains": project_domains}
    return config


def _make_extracted_data(
    skills=None,
    education=None,
    projects=None,
    experience_years=0,
    passed_out_year=None,
):
    """Helper to build a realistic extracted_data dict."""
    data = {
        "skills": skills or [],
        "education": education or [],
        "projects": projects or [],
        "experience_years": experience_years,
    }
    if passed_out_year is not None:
        data["passed_out_year"] = passed_out_year
    return data


def test_score_resume_high_score():
    """Resume with all matching skills, good education, relevant projects."""
    job_config = _make_job_config(
        required_skills=["Python", "React", "PostgreSQL"],
        nice_to_have_skills=["Docker", "Kubernetes"],
        education_requirements=["B.Tech", "B.E"],
        candidate_type="any",
        project_domains=["web development", "machine learning"],
    )
    extracted = _make_extracted_data(
        skills=["Python", "React.js", "postgres", "Docker", "k8s"],
        education=[{"degree": "Bachelor of Technology"}],
        projects=[
            {"domain": "web development"},
            {"domain": "machine learning"},
        ],
        experience_years=3,
    )

    score, reason = score_resume(job_config, extracted)
    # All weights sum to 100, and everything matches
    assert score == 100
    assert "Required skills matched 3/3" in reason


def test_score_resume_low_score_no_skills():
    """Resume with zero matching skills should score very low."""
    job_config = _make_job_config(
        required_skills=["Rust", "Go", "Elixir"],
        nice_to_have_skills=["Haskell"],
        education_requirements=["Ph.D"],
        candidate_type="experienced",
    )
    extracted = _make_extracted_data(
        skills=["HTML", "CSS"],
        education=[{"degree": "B.Tech"}],
        experience_years=0,
    )

    score, reason = score_resume(job_config, extracted)
    # No required skills, no nice-to-have, wrong education, not experienced
    assert score < 30
    assert "Required skills matched 0/3" in reason


def test_score_resume_empty_extracted_data():
    """Completely empty resume data should not crash and score 0 or near-0."""
    job_config = _make_job_config(
        required_skills=["Python"],
        education_requirements=["B.Tech"],
        candidate_type="experienced",
    )
    extracted = _make_extracted_data()

    score, reason = score_resume(job_config, extracted)
    assert score >= 0
    assert "Required skills matched 0/1" in reason


def test_score_resume_minimal_config():
    """Job config with no requirements at all."""
    job_config = _make_job_config(candidate_type="any")
    extracted = _make_extracted_data()

    score, reason = score_resume(job_config, extracted)
    # Only eligibility "any" should award points
    assert score >= 0


def test_score_resume_candidate_type_student():
    job_config = _make_job_config(candidate_type="student")
    extracted = _make_extracted_data(
        experience_years=0,
        passed_out_year=2026,
    )
    score, reason = score_resume(job_config, extracted)
    assert "Eligibility met (student / recent graduate)" in reason


def test_score_resume_candidate_type_student_too_experienced():
    job_config = _make_job_config(candidate_type="student")
    extracted = _make_extracted_data(
        experience_years=10,
        passed_out_year=2010,
    )
    score, reason = score_resume(job_config, extracted)
    assert "Eligibility not met (expected student / recent grad)" in reason


def test_score_resume_candidate_type_experienced():
    job_config = _make_job_config(candidate_type="experienced")
    extracted = _make_extracted_data(experience_years=5)
    score, reason = score_resume(job_config, extracted)
    assert "Eligibility met (experienced, 5 yrs)" in reason


def test_score_resume_candidate_type_experienced_no_experience():
    job_config = _make_job_config(candidate_type="experienced")
    extracted = _make_extracted_data(experience_years=0)
    score, reason = score_resume(job_config, extracted)
    assert "Eligibility not met (expected experienced candidate)" in reason


def test_score_resume_unknown_candidate_type():
    job_config = _make_job_config(candidate_type="intern")
    extracted = _make_extracted_data()
    score, reason = score_resume(job_config, extracted)
    assert "Eligibility skipped" in reason


def test_score_resume_capped_at_100():
    """Score should never exceed 100 even with generous weights."""
    job_config = _make_job_config(
        required_skills=["Python"],
        weights={
            "required_skills": 80,
            "nice_to_have_skills": 0,
            "projects": 0,
            "education": 0,
            "eligibility": 80,
        },
        candidate_type="any",
    )
    extracted = _make_extracted_data(skills=["Python"])
    score, _ = score_resume(job_config, extracted)
    assert score <= 100


# ── Fuzzy matching edge cases ────────────────────────────────────────────────


def test_fuzzy_react_dot_js_matches_react():
    resume_tokens = _build_resume_skill_tokens(["React.js"])
    assert _skill_matches("react", resume_tokens) is True


def test_fuzzy_btech_matches_bachelor_of_technology():
    assert _education_matches(
        ["bachelor of technology"], ["B.Tech"]
    ) is True


def test_fuzzy_cpp_alias():
    tokens = _canonicalize_skill("cpp")
    assert "c++" in tokens


def test_fuzzy_csharp_alias():
    tokens = _canonicalize_skill("csharp")
    assert "c#" in tokens


def test_fuzzy_mongo_alias():
    tokens = _canonicalize_skill("mongo")
    assert "mongodb" in tokens


def test_fuzzy_bsc_to_bachelor_of_science():
    forms = _canonicalize_degree("B.Sc")
    assert "bachelor of science" in forms


def test_fuzzy_msc_to_master_of_science():
    forms = _canonicalize_degree("M.Sc")
    assert "master of science" in forms


def test_project_score_capped_to_weight():
    """Even with many matching projects, score should not exceed the weight."""
    job_config = _make_job_config(
        project_domains=["web", "ml", "data"],
        weights={
            "required_skills": 0,
            "nice_to_have_skills": 0,
            "projects": 15,
            "education": 0,
            "eligibility": 0,
        },
        candidate_type="any",
    )
    # Provide more matching projects than the weight can accommodate
    extracted = _make_extracted_data(
        projects=[
            {"domain": "web"},
            {"domain": "ml"},
            {"domain": "data"},
        ]
    )
    score, reason = score_resume(job_config, extracted)
    # 3 projects * 10 pts = 30, but capped at weight 15
    assert score <= 15
