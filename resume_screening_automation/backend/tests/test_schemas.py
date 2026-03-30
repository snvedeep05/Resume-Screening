"""Tests for schemas.py (Pydantic models).

All tests are pure-Python -- no database or external services needed.
"""
import pytest
from pydantic import ValidationError
from schemas import JobCreateRequest, DecisionUpdateRequest, AIGenerateRequest


# ── JobCreateRequest ─────────────────────────────────────────────────────────


def test_job_create_request_valid():
    req = JobCreateRequest(job_title="Backend Engineer", job_config={"key": "val"})
    assert req.job_title == "Backend Engineer"
    assert req.job_config == {"key": "val"}


def test_job_create_request_default_config():
    req = JobCreateRequest(job_title="Frontend Developer")
    assert req.job_config == {}


def test_job_create_request_missing_title():
    with pytest.raises(ValidationError):
        JobCreateRequest(job_config={"key": "val"})


def test_job_create_request_empty_title_is_valid_string():
    # Pydantic accepts an empty string for str fields by default
    req = JobCreateRequest(job_title="")
    assert req.job_title == ""


# ── DecisionUpdateRequest ───────────────────────────────────────────────────


def test_decision_update_shortlisted():
    req = DecisionUpdateRequest(decision="shortlisted")
    assert req.decision == "shortlisted"


def test_decision_update_rejected():
    req = DecisionUpdateRequest(decision="rejected")
    assert req.decision == "rejected"


def test_decision_update_invalid_value():
    with pytest.raises(ValidationError):
        DecisionUpdateRequest(decision="maybe")


def test_decision_update_missing_decision():
    with pytest.raises(ValidationError):
        DecisionUpdateRequest()


def test_decision_update_case_sensitive():
    """The pattern is exact -- 'Shortlisted' (capital S) should fail."""
    with pytest.raises(ValidationError):
        DecisionUpdateRequest(decision="Shortlisted")


# ── AIGenerateRequest ───────────────────────────────────────────────────────


def test_ai_generate_request_valid():
    req = AIGenerateRequest(job_description="We need a Python developer.")
    assert req.job_description == "We need a Python developer."


def test_ai_generate_request_missing_description():
    with pytest.raises(ValidationError):
        AIGenerateRequest()
