# Maps template_id → the pipeline stage that email represents.
# Used when seeding the pipeline to determine a candidate's starting stage
# based on what emails have already been sent (email_logs history).
# Order matters: check in reverse pipeline order so we land on the most advanced stage.

TEMPLATE_TO_STAGE = {
    36: "rejected",           # Rejection email
    30: "assignment_sent",    # Assignment email
    28: "shortlisting_sent",  # Shortlisting email
}

# All pipeline stages in order (for display + filtering)
STAGE_ORDER = [
    "new",
    "shortlisting_sent",
    "assignment_sent",
    "assignment_submitted",
    "interview_sent",
    "selected",
    "offer_sent",
    "joined",
    "rejected",
]

STAGE_LABELS = {
    "new":                 "New",
    "shortlisting_sent":   "Shortlisting Sent",
    "assignment_sent":     "Assignment Sent",
    "assignment_submitted":"Assignment Submitted",
    "interview_sent":      "Interview Invited",
    "selected":            "Selected",
    "offer_sent":          "Offer Sent",
    "joined":              "Joined",
    "rejected":            "Rejected",
}

# Brevo template IDs
TEMPLATE_SHORTLISTED = 28
TEMPLATE_REJECTED    = 36
TEMPLATE_ASSIGNMENT  = 30
TEMPLATE_INTERVIEW   = 29   # inactive — needs activating in Brevo
TEMPLATE_SELECTED    = 32   # inactive — needs activating in Brevo

# Templates that are ready to use
ACTIVE_TEMPLATES = {TEMPLATE_SHORTLISTED, TEMPLATE_REJECTED, TEMPLATE_ASSIGNMENT}
