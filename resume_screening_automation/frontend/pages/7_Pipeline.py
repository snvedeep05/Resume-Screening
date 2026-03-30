import re
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from api_client import get_jobs
from brevo_client import BrevoClient
from db_stage_map import (
    ACTIVE_TEMPLATES,
    STAGE_LABELS,
    STAGE_ORDER,
    TEMPLATE_ASSIGNMENT,
    TEMPLATE_INTERVIEW,
    TEMPLATE_REJECTED,
    TEMPLATE_SELECTED,
    TEMPLATE_SHORTLISTED,
)
from email_db_client import (
    bulk_update_stages,
    cancel_queued_emails,
    enqueue_email,
    get_pending_queue,
    get_pipeline_candidates,
    get_session,
    is_already_sent,
    log_email_sent,
    mark_queue_failed,
    mark_queue_sent,
    update_pipeline_stage,
)
from email_utils import BREVO_DAILY_LIMIT, fetch_brevo_stats, show_brevo_usage

st.set_page_config(page_title="Candidate Pipeline", page_icon="🔁", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Please login first.")
    st.stop()

# ── Stage action config ────────────────────────────────────────────────────────
# Defines what action is available from each stage and what stage follows.

ACTIONS = {
    "new": {
        "label":        "📧 Send Shortlisting Email",
        "template_id":  TEMPLATE_SHORTLISTED,
        "next_stage":   "shortlisting_sent",
        "params_fn":    lambda row: {"FIRSTNAME": row["first_name"], "JOB_TITLE": row["job_title"]},
    },
    "shortlisting_sent": {
        "label":        "📝 Send Assignment Email",
        "template_id":  TEMPLATE_ASSIGNMENT,
        "next_stage":   "assignment_sent",
        "params_fn":    lambda row: {
            "FIRSTNAME":     row["first_name"],
            "DEADLINE_DATE": (datetime.today() + timedelta(days=10)).strftime("%d %B %Y"),
        },
    },
    "assignment_sent": {
        "label":        "✅ Mark Assignment Submitted",
        "template_id":  None,   # no email — HR marks manually
        "next_stage":   "assignment_submitted",
        "params_fn":    None,
    },
    "assignment_submitted": {
        "label":        "📅 Send Interview Invite",
        "template_id":  TEMPLATE_INTERVIEW,   # inactive — disabled until activated
        "next_stage":   "interview_sent",
        "params_fn":    lambda row: {"FIRSTNAME": row["first_name"], "JOB_TITLE": row["job_title"]},
    },
    "interview_sent": {
        "label":        "🏆 Mark as Selected",
        "template_id":  None,
        "next_stage":   "selected",
        "params_fn":    None,
    },
    "selected": {
        "label":        "📄 Send Offer Letter",
        "template_id":  TEMPLATE_SELECTED,    # inactive — disabled until activated
        "next_stage":   "offer_sent",
        "params_fn":    lambda row: {"FIRSTNAME": row["first_name"], "JOB_TITLE": row["job_title"]},
    },
    "offer_sent": {
        "label":        "🎉 Mark as Joined",
        "template_id":  None,
        "next_stage":   "joined",
        "params_fn":    None,
    },
}

REJECT_ACTION = {
    "label":       "❌ Reject Selected",
    "template_id": TEMPLATE_REJECTED,
    "next_stage":  "rejected",
    "params_fn":   lambda row: {"FIRSTNAME": row["first_name"], "JOB_TITLE": row["job_title"]},
}

TERMINAL_STAGES = {"joined", "rejected"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def days_since(ts) -> int:
    if ts is None:
        return 0
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return (datetime.utcnow() - ts.replace(tzinfo=None)).days


def staleness_icon(days: int) -> str:
    if days >= 7:
        return "🔴"
    if days >= 3:
        return "🟡"
    return ""


def parse_pasted_emails(text: str) -> set:
    """Extract email addresses from a blob of pasted text."""
    pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    return {m.lower() for m in re.findall(pattern, text)}


def process_queue(db, client: BrevoClient, job_id: int, job_title: str, quota: int) -> tuple:
    """Send pending queued emails up to quota. Returns (sent, failed, remaining_quota)."""
    sent = failed = 0
    items = get_pending_queue(db, job_id=job_id)
    for item in items:
        if quota <= 0:
            break
        success = client.send_template_email(
            to_email=item["email"],
            template_id=item["template_id"],
            params=item["params"] or {},
            to_name=item["full_name"],
        )
        if success:
            mark_queue_sent(db, item["queue_id"])
            log_email_sent(
                db, item["email"], item["template_id"],
                full_name=item["full_name"], job_title=job_title, job_id=job_id,
            )
            if item["stage_after_send"] and item["pipeline_id"]:
                update_pipeline_stage(db, item["pipeline_id"], item["stage_after_send"])
            sent += 1
            quota -= 1
        else:
            mark_queue_failed(db, item["queue_id"])
            failed += 1
    return sent, failed, quota


# ── Page ───────────────────────────────────────────────────────────────────────

st.title("🔁 Candidate Pipeline")
show_brevo_usage()

# ── Job selector ──────────────────────────────────────────────────────────────

jobs = get_jobs()
if not jobs:
    st.warning("No job configs found. Create one first.")
    st.stop()

job_options   = {j["job_title"]: j["job_id"] for j in jobs}
selected_job  = st.selectbox("Select Job", list(job_options.keys()), key="pipeline_job")
selected_job_id = job_options[selected_job]

# ── Process pending queue first ────────────────────────────────────────────────

stats           = fetch_brevo_stats()
quota_remaining = max(BREVO_DAILY_LIMIT - stats["requests"], 0)

db = get_session()
try:
    pending_count = len(get_pending_queue(db, job_id=selected_job_id))
finally:
    db.close()

if pending_count > 0:
    with st.expander(f"📬 {pending_count} queued email(s) from previous day — click to send now", expanded=True):
        if quota_remaining == 0:
            st.error("🚫 Brevo daily limit reached. Come back after midnight UTC.")
        else:
            st.info(f"Quota available: **{quota_remaining}**. Will send up to that many queued emails.")
            if st.button("▶️ Send Queued Emails Now", key="send_queue"):
                client = BrevoClient()
                db = get_session()
                try:
                    sent, failed, quota_remaining = process_queue(
                        db, client, selected_job_id, selected_job, quota_remaining
                    )
                finally:
                    db.close()
                st.cache_data.clear()
                st.success(f"✅ Sent {sent} queued email(s). Failed: {failed}.")
                st.rerun()

st.divider()

# ── Load candidates ────────────────────────────────────────────────────────────

if st.button("🔄 Refresh", key="pipeline_refresh"):
    st.rerun()

db = get_session()
try:
    candidates = get_pipeline_candidates(db, job_id=selected_job_id)
finally:
    db.close()

if not candidates:
    st.info("No candidates in the pipeline for this job yet. Go to Results Dashboard → Add Shortlisted to Pipeline.")
    st.stop()

df = pd.DataFrame(candidates)
df["stage_updated_at"] = pd.to_datetime(df["stage_updated_at"], errors="coerce")
df["added_at"]         = pd.to_datetime(df["added_at"],         errors="coerce")
df["days_in_stage"]    = df["stage_updated_at"].apply(
    lambda ts: days_since(ts) if pd.notna(ts) else 0
)
df["stale"]            = df["days_in_stage"].apply(staleness_icon)
df["stage_label"]      = df["stage"].map(STAGE_LABELS).fillna(df["stage"])

# Stage filter
stage_counts = df["stage"].value_counts().to_dict()
stage_options = ["All"] + [s for s in STAGE_ORDER if s in stage_counts]
stage_labels_with_count = []
for s in stage_options:
    if s == "All":
        stage_labels_with_count.append(f"All ({len(df)})")
    else:
        stage_labels_with_count.append(f"{STAGE_LABELS.get(s, s)} ({stage_counts.get(s, 0)})")

col_filter, col_search = st.columns([2, 3])

with col_filter:
    selected_stage_label = st.selectbox(
        "Filter by Stage",
        stage_labels_with_count,
        key="stage_filter"
    )
    selected_stage = stage_options[stage_labels_with_count.index(selected_stage_label)]

with col_search:
    paste_text = st.text_area(
        "Paste emails to auto-select (from inbox, one per line or comma-separated)",
        height=68,
        key="paste_emails",
        placeholder="john@example.com, jane@example.com",
    )

# Apply stage filter
view_df = df if selected_stage == "All" else df[df["stage"] == selected_stage].copy()

# Auto-select from pasted emails
pasted_emails = parse_pasted_emails(paste_text) if paste_text.strip() else set()

# Build display table
view_df = view_df.copy()
view_df["Select"] = view_df["email"].str.lower().isin(pasted_emails) if pasted_emails else False

display_cols = ["Select", "full_name", "email", "phone", "score", "stage_label", "days_in_stage"]
display_cols = [c for c in display_cols if c in view_df.columns]

# Key changes with the active stage filter so the table (and Select All checkbox) resets cleanly
table_key = f"pipeline_table_{selected_stage_label}"

edited = st.data_editor(
    view_df[display_cols].reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Select":        st.column_config.CheckboxColumn("☐",           width="small"),
        "full_name":     st.column_config.TextColumn("Name",            disabled=True),
        "email":         st.column_config.TextColumn("Email",           disabled=True),
        "phone":         st.column_config.TextColumn("Phone",           disabled=True),
        "score":         st.column_config.NumberColumn("Score",         disabled=True, width="small"),
        "stage_label":   st.column_config.TextColumn("Stage",           disabled=True),
        "days_in_stage": st.column_config.NumberColumn("Days in Stage", disabled=True, width="small"),
    },
    key=table_key,
)

# Map selections back to pipeline rows
selected_mask    = edited["Select"].fillna(False)
selected_indices = view_df.reset_index(drop=True)[selected_mask].index.tolist()
selected_rows    = view_df.reset_index(drop=True).loc[selected_indices]
selected_ids     = selected_rows["pipeline_id"].tolist()
selected_count   = len(selected_ids)

if selected_count:
    st.markdown(f"**{selected_count}** candidate(s) selected")

# ── Pipeline Summary (always visible) ─────────────────────────────────────────

st.divider()
st.subheader("Pipeline Summary")
summary_cols = st.columns(len(STAGE_ORDER))
for col, stage in zip(summary_cols, STAGE_ORDER):
    col.metric(STAGE_LABELS.get(stage, stage), stage_counts.get(stage, 0))

st.divider()

# ── Action buttons ─────────────────────────────────────────────────────────────

st.subheader("Actions")

if selected_count == 0:
    st.info("Select candidates above using the checkboxes or paste their emails.")
    st.stop()

# Determine the current stage of selected candidates (must all be same stage for forward actions)
selected_stages = selected_rows["stage"].unique().tolist()
uniform_stage   = selected_stages[0] if len(selected_stages) == 1 else None

col_forward, col_reject = st.columns([3, 1])

with col_forward:
    if uniform_stage and uniform_stage not in TERMINAL_STAGES and uniform_stage in ACTIONS:
        action = ACTIONS[uniform_stage]
        template_id = action["template_id"]
        is_active   = template_id is None or template_id in ACTIVE_TEMPLATES

        if not is_active:
            st.warning(
                f"⚠️ Template #{template_id} is not yet active in Brevo. "
                f"Activate it first, then this action will be enabled."
            )

        if st.button(action["label"], disabled=not is_active, key="forward_action"):
            st.session_state["confirm_action"] = {
                "type":        "forward",
                "action":      action,
                "stage":       uniform_stage,
                "selected_ids": selected_ids,
                "selected_rows": selected_rows.to_dict("records"),
            }
    elif uniform_stage in TERMINAL_STAGES:
        st.info(f"Selected candidates are already at a terminal stage: **{STAGE_LABELS.get(uniform_stage, uniform_stage)}**.")
    elif not uniform_stage:
        st.warning("Selected candidates are at different stages. Select candidates at the same stage to use the forward action.")

with col_reject:
    reject_eligible = [
        r for r in selected_rows.to_dict("records") if r["stage"] not in TERMINAL_STAGES
    ]
    if reject_eligible:
        if st.button(REJECT_ACTION["label"], key="reject_action", type="secondary"):
            st.session_state["confirm_action"] = {
                "type":         "reject",
                "action":       REJECT_ACTION,
                "selected_ids": [r["pipeline_id"] for r in reject_eligible],
                "selected_rows": reject_eligible,
            }

# ── Confirmation dialog ────────────────────────────────────────────────────────

if "confirm_action" in st.session_state:
    pending = st.session_state["confirm_action"]
    action  = pending["action"]
    rows    = pending["selected_rows"]
    ids     = pending["selected_ids"]

    st.divider()

    if action["template_id"]:
        st.info(
            f"**{action['label']}** will be sent to **{len(ids)}** candidate(s). "
            f"Template: #{action['template_id']}."
        )
    else:
        st.info(
            f"**{action['label']}** will mark **{len(ids)}** candidate(s) as "
            f"**{STAGE_LABELS.get(action['next_stage'], action['next_stage'])}** — no email."
        )

    col_confirm, col_cancel = st.columns([1, 4])
    confirm = col_confirm.button("✅ Confirm", key="confirm_btn")
    cancel  = col_cancel.button("✖ Cancel",  key="cancel_btn")

    if cancel:
        del st.session_state["confirm_action"]
        st.rerun()

    if confirm:
        del st.session_state["confirm_action"]

        template_id = action["template_id"]
        next_stage  = action["next_stage"]
        params_fn   = action["params_fn"]

        if template_id is None:
            # No email — just update stages
            db = get_session()
            try:
                bulk_update_stages(db, ids, next_stage)
            finally:
                db.close()

            st.session_state["last_action"] = {
                "ids":          ids,
                "prev_stages":  {r["pipeline_id"]: r["stage"] for r in rows},
                "queued_ids":   [],
                "until":        datetime.utcnow() + timedelta(minutes=5),
                "label":        action["label"],
            }
            st.success(f"✅ {len(ids)} candidate(s) marked as {STAGE_LABELS.get(next_stage, next_stage)}.")
            st.rerun()

        else:
            # Email action
            if quota_remaining == 0:
                st.error("🚫 Brevo daily limit reached. All emails will be queued for tomorrow.")

            client    = BrevoClient()
            db        = get_session()
            sent      = 0
            queued    = 0
            skipped   = 0
            failed    = 0
            queued_ids = []

            try:
                for row in rows:
                    pid        = row["pipeline_id"]
                    email      = str(row["email"]).strip()
                    full_name  = str(row.get("full_name") or "").strip()
                    first_name = full_name.split()[0] if full_name else email.split("@")[0]

                    row_params = {
                        "first_name": first_name,
                        "job_title":  selected_job,
                    }

                    params = params_fn(row_params) if params_fn else {}

                    if is_already_sent(db, email, template_id, job_id=selected_job_id):
                        skipped += 1
                        continue

                    if quota_remaining <= 0:
                        qid = enqueue_email(
                            db,
                            pipeline_id=pid,
                            email=email,
                            full_name=full_name,
                            template_id=template_id,
                            params=params,
                            job_id=selected_job_id,
                            stage_after_send=next_stage,
                        )
                        queued_ids.append(qid)
                        queued += 1
                        continue

                    success = client.send_template_email(
                        to_email=email,
                        template_id=template_id,
                        params=params,
                        to_name=full_name,
                    )

                    if success:
                        log_email_sent(
                            db, email, template_id,
                            full_name=full_name, job_title=selected_job,
                            job_id=selected_job_id,
                        )
                        update_pipeline_stage(db, pid, next_stage)
                        sent += 1
                        quota_remaining -= 1
                    else:
                        failed += 1

            finally:
                db.close()

            st.session_state["last_action"] = {
                "ids":          ids,
                "prev_stages":  {r["pipeline_id"]: r["stage"] for r in rows},
                "queued_ids":   queued_ids,
                "until":        datetime.utcnow() + timedelta(minutes=5),
                "label":        action["label"],
            }

            st.cache_data.clear()
            parts = []
            if sent:    parts.append(f"✅ {sent} sent")
            if queued:  parts.append(f"📬 {queued} queued for tomorrow")
            if skipped: parts.append(f"⏩ {skipped} already sent (skipped)")
            if failed:  parts.append(f"❌ {failed} failed")
            st.success(" · ".join(parts) if parts else "Nothing to do.")
            st.rerun()

# ── Undo banner ────────────────────────────────────────────────────────────────

if "last_action" in st.session_state:
    la   = st.session_state["last_action"]
    secs = int((la["until"] - datetime.utcnow()).total_seconds())

    if secs > 0:
        st.divider()
        st.info(f"⏪ Last action: **{la['label']}** — undo available for {secs}s")

        if st.button("↩ Undo Last Action", key="undo_btn"):
            db = get_session()
            try:
                # Restore each candidate to their previous stage
                for pid, prev_stage in la["prev_stages"].items():
                    update_pipeline_stage(db, int(pid), prev_stage)
                # Cancel any queued emails
                cancel_queued_emails(db, la["ids"])
            finally:
                db.close()
            del st.session_state["last_action"]
            st.success("↩ Action undone. Stages reverted and queued emails cancelled.")
            st.rerun()
    else:
        del st.session_state["last_action"]

