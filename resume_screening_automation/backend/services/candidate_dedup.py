"""
Candidate deduplication by email and phone.
Links resume results to a canonical candidate record.
"""
from db.models import Candidate


def get_or_create_candidate(db, extracted_data: dict) -> int | None:
    """
    Find or create a candidate based on email (primary) or phone (fallback).
    Returns candidate_id or None if no identifiers found.
    """
    personal = extracted_data.get("personal_details", {})
    email = personal.get("email")
    phone = personal.get("phone")
    full_name = personal.get("full_name")

    if not email and not phone:
        return None

    # Try email first (strongest identifier)
    if email:
        candidate = db.query(Candidate).filter_by(email=email).first()
        if candidate:
            # Update name if we have a better one
            if full_name and not candidate.full_name:
                candidate.full_name = full_name
            if phone and not candidate.phone:
                candidate.phone = phone
            db.flush()
            return candidate.candidate_id

    # Try phone if no email match
    if phone and not email:
        candidate = db.query(Candidate).filter_by(phone=phone).first()
        if candidate:
            if full_name and not candidate.full_name:
                candidate.full_name = full_name
            db.flush()
            return candidate.candidate_id

    # Create new candidate
    candidate = Candidate(
        email=email,
        phone=phone,
        full_name=full_name
    )
    db.add(candidate)
    db.flush()
    return candidate.candidate_id
