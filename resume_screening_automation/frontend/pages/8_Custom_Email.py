import streamlit as st
import pandas as pd
from email_validator import validate_email, EmailNotValidError

from brevo_client import BrevoClient
from email_db_client import get_session, log_custom_email, get_custom_email_logs
from email_utils import show_brevo_usage, fetch_brevo_stats, BREVO_DAILY_LIMIT

st.set_page_config(page_title="Custom Email Sender", page_icon="✉️", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Please login first.")
    st.stop()

st.title("✉️ Custom Email Sender")
show_brevo_usage()
st.divider()

# ── Template loading ───────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def load_templates():
    client = BrevoClient()
    return client.get_templates()

@st.cache_data(ttl=120, show_spinner=False)
def load_params(template_id: int):
    client = BrevoClient()
    return client.get_template_params(template_id)

col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.subheader("Step 1 — Select Template")
with col_refresh:
    if st.button("🔄 Refresh Templates", key="refresh_templates"):
        st.cache_data.clear()
        st.rerun()

templates = load_templates()

if not templates:
    st.error("Could not load templates from Brevo. Check your API key.")
    st.stop()

template_map = {
    f"{'✅' if t['is_active'] else '⬜'} #{t['id']} — {t['name']}": t
    for t in templates
}

selected_label    = st.selectbox("Template", list(template_map.keys()), key="custom_template")
selected_template = template_map[selected_label]
template_id       = selected_template["id"]
template_name     = selected_template["name"]

if not selected_template["is_active"]:
    st.warning(f"⚠️ Template #{template_id} is inactive in Brevo. Activate it before sending.")

st.divider()

# ── Step 2: Candidate details ──────────────────────────────────────────────────

params_found = load_params(template_id)

st.subheader("Step 2 — Candidate Details")

if params_found:
    st.caption(f"Placeholders detected in this template: `{'`, `'.join(params_found)}`")
else:
    st.caption("No `params.*` placeholders detected in this template.")

col1, col2 = st.columns(2)

with col1:
    full_name = st.text_input("Full Name *", key="custom_name",
                              help="Used for FIRSTNAME placeholder and the log")
    email     = st.text_input("Email *", key="custom_email")
    job_title = st.text_input("Job Title", key="custom_job_title",
                              help="Used for JOB_TITLE placeholder and the log")

with col2:
    reason = st.text_input("Reason / Note", key="custom_reason",
                           placeholder="e.g. Referred by manager, Special candidate")

STANDARD_PARAMS = {"FIRSTNAME", "JOB_TITLE", "FIRST_NAME", "NAME"}
extra_params = [p for p in params_found if p.upper() not in STANDARD_PARAMS]

extra_values = {}
if extra_params:
    st.markdown("**Additional template fields:**")
    extra_cols = st.columns(min(len(extra_params), 3))
    for i, param in enumerate(extra_params):
        with extra_cols[i % 3]:
            extra_values[param] = st.text_input(
                param.replace("_", " ").title(),
                key=f"extra_{param}",
            )

st.divider()

# ── Step 3: Send ───────────────────────────────────────────────────────────────

st.subheader("Step 3 — Send")

# Validate inputs inline (no st.stop — just flag errors and skip confirm)
errors = []
if not full_name.strip():
    errors.append("Full Name is required.")
if not email.strip():
    errors.append("Email is required.")
else:
    try:
        validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError as e:
        errors.append(f"Invalid email address: {e}")

for err in errors:
    st.error(err)

send_allowed = len(errors) == 0 and selected_template["is_active"]

if st.button("📤 Send Email", key="custom_send_btn", disabled=not send_allowed):
    # Check Brevo daily quota before even showing confirmation
    stats           = fetch_brevo_stats()
    quota_remaining = max(BREVO_DAILY_LIMIT - stats["requests"], 0)
    if quota_remaining <= 0:
        st.error("🚫 Brevo daily limit reached. Come back after midnight UTC.")
    else:
        st.session_state["custom_confirm"] = {
            "full_name":    full_name.strip(),
            "email":        email.strip(),
            "job_title":    job_title.strip(),
            "reason":       reason.strip(),
            "extra_values": dict(extra_values),
            "template_id":  template_id,
            "template_name": template_name,
            "params_found": list(params_found),
        }

if st.session_state.get("custom_confirm"):
    pending = st.session_state["custom_confirm"]
    st.warning(
        f"⚠️ About to send **{pending['template_name']}** to **{pending['email']}**. "
        f"Click **Confirm & Send** to proceed."
    )
    col_confirm, col_cancel = st.columns([1, 5])
    confirm = col_confirm.button("✅ Confirm & Send", key="custom_confirm_btn")
    cancel  = col_cancel.button("✖ Cancel",          key="custom_cancel_btn")

    if cancel:
        del st.session_state["custom_confirm"]
        st.rerun()

    if confirm:
        p          = st.session_state.pop("custom_confirm")
        first_name = p["full_name"].split()[0] if p["full_name"] else ""

        send_params = {}
        for param in p["params_found"]:
            upper = param.upper()
            if upper in ("FIRSTNAME", "FIRST_NAME"):
                send_params[param] = first_name
            elif upper == "JOB_TITLE":
                send_params[param] = p["job_title"]
            elif upper == "NAME":
                send_params[param] = p["full_name"]
            else:
                send_params[param] = p["extra_values"].get(param, "")

        client  = BrevoClient()
        success = client.send_template_email(
            to_email=p["email"],
            template_id=p["template_id"],
            params=send_params,
            to_name=p["full_name"],
        )

        if success:
            db = get_session()
            try:
                log_custom_email(
                    db,
                    email=p["email"],
                    template_id=p["template_id"],
                    template_name=p["template_name"],
                    full_name=p["full_name"],
                    job_title=p["job_title"] or None,
                    reason=p["reason"] or None,
                )
            finally:
                db.close()

            # Clear form fields so they reset on next render
            for key in ["custom_name", "custom_email", "custom_job_title", "custom_reason"]:
                st.session_state.pop(key, None)
            for param in p["params_found"]:
                st.session_state.pop(f"extra_{param}", None)

            st.success(f"✅ Email sent to **{p['email']}** using **{p['template_name']}**.")
        else:
            st.error("❌ Failed to send email. Check Brevo API key or template settings.")

        st.rerun()

st.divider()

# ── Sent Log ───────────────────────────────────────────────────────────────────

st.subheader("Sent Log")

db = get_session()
try:
    logs = get_custom_email_logs(db)
finally:
    db.close()

if not logs:
    st.info("No custom emails sent yet.")
else:
    df = pd.DataFrame(logs)
    df["sent_at"] = pd.to_datetime(df["sent_at"])

    # ── Filters ────────────────────────────────────────────────────────────────
    filter_col1, filter_col2 = st.columns([2, 2])

    with filter_col1:
        template_options = ["All"] + sorted(df["template_name"].dropna().unique().tolist())
        filter_template  = st.selectbox("Filter by Template", template_options, key="log_filter_template")

    with filter_col2:
        filter_search = st.text_input("Search by Name or Email", key="log_search",
                                      placeholder="Type to filter...")

    filtered = df.copy()
    if filter_template != "All":
        filtered = filtered[filtered["template_name"] == filter_template]
    if filter_search.strip():
        q = filter_search.strip().lower()
        filtered = filtered[
            filtered["full_name"].str.lower().str.contains(q, na=False) |
            filtered["email"].str.lower().str.contains(q, na=False)
        ]

    st.caption(f"Showing {len(filtered)} of {len(df)} records")

    filtered_display = filtered.copy()
    filtered_display["sent_at"] = filtered_display["sent_at"].dt.strftime("%d %b %Y %H:%M")
    filtered_display = filtered_display.rename(columns={
        "full_name":     "Name",
        "email":         "Email",
        "job_title":     "Job Title",
        "template_name": "Template",
        "reason":        "Reason",
        "sent_at":       "Sent At",
    })

    st.dataframe(
        filtered_display[["Name", "Email", "Job Title", "Template", "Reason", "Sent At"]],
        use_container_width=True,
        hide_index=True,
    )

    # CSV export
    csv = filtered_display[["Name", "Email", "Job Title", "Template", "Reason", "Sent At"]].to_csv(index=False)
    st.download_button(
        "⬇️ Download as CSV",
        data=csv,
        file_name="custom_email_log.csv",
        mime="text/csv",
        key="log_download",
    )
