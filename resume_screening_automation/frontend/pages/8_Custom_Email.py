import streamlit as st
import pandas as pd

from brevo_client import BrevoClient
from email_db_client import get_session, log_custom_email, get_custom_email_logs
from email_utils import show_brevo_usage

st.set_page_config(page_title="Custom Email Sender", page_icon="✉️", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Please login first.")
    st.stop()

st.title("✉️ Custom Email Sender")
show_brevo_usage()
st.divider()

# ── Step 1: Load templates ─────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def load_templates():
    client = BrevoClient()
    return client.get_templates()

@st.cache_data(ttl=120, show_spinner=False)
def load_params(template_id: int):
    client = BrevoClient()
    return client.get_template_params(template_id)

templates = load_templates()

if not templates:
    st.error("Could not load templates from Brevo. Check your API key.")
    st.stop()

# Build label → template map
template_map = {
    f"{'✅' if t['is_active'] else '⬜'} #{t['id']} — {t['name']}": t
    for t in templates
}

st.subheader("Step 1 — Select Template")
selected_label = st.selectbox("Template", list(template_map.keys()), key="custom_template")
selected_template = template_map[selected_label]
template_id   = selected_template["id"]
template_name = selected_template["name"]

if not selected_template["is_active"]:
    st.warning(f"⚠️ Template #{template_id} is inactive in Brevo. Activate it before sending.")

st.divider()

# ── Step 2: Detected params + candidate details ────────────────────────────────

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
    email     = st.text_input("Email *",     key="custom_email")
    job_title = st.text_input("Job Title",   key="custom_job_title",
                              help="Used for JOB_TITLE placeholder and the log")

with col2:
    reason    = st.text_input("Reason / Note",  key="custom_reason",
                              placeholder="e.g. Referred by manager, Special candidate")

# Dynamic fields for any remaining params (exclude FIRSTNAME / JOB_TITLE — covered above)
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

# ── Send button ────────────────────────────────────────────────────────────────

st.subheader("Step 3 — Send")

if st.button("📤 Send Email", key="custom_send_btn",
             disabled=not selected_template["is_active"]):

    # Validate required fields
    if not full_name.strip():
        st.error("Full Name is required.")
        st.stop()
    if not email.strip():
        st.error("Email is required.")
        st.stop()

    st.session_state["custom_confirm"] = True

if st.session_state.get("custom_confirm"):
    st.warning(
        f"⚠️ About to send **{template_name}** to **{email.strip()}**. "
        f"Click **Confirm & Send** to proceed."
    )
    col_confirm, col_cancel = st.columns([1, 5])
    confirm = col_confirm.button("✅ Confirm & Send", key="custom_confirm_btn")
    cancel  = col_cancel.button("✖ Cancel",          key="custom_cancel_btn")

    if cancel:
        del st.session_state["custom_confirm"]
        st.rerun()

    if confirm:
        del st.session_state["custom_confirm"]

        # Build params dict for Brevo
        first_name = full_name.strip().split()[0] if full_name.strip() else ""
        send_params = {}

        for param in params_found:
            upper = param.upper()
            if upper in ("FIRSTNAME", "FIRST_NAME"):
                send_params[param] = first_name
            elif upper in ("JOB_TITLE",):
                send_params[param] = job_title.strip()
            elif upper == "NAME":
                send_params[param] = full_name.strip()
            else:
                send_params[param] = extra_values.get(param, "")

        client  = BrevoClient()
        success = client.send_template_email(
            to_email=email.strip(),
            template_id=template_id,
            params=send_params,
            to_name=full_name.strip(),
        )

        if success:
            db = get_session()
            try:
                log_custom_email(
                    db,
                    email=email.strip(),
                    template_id=template_id,
                    template_name=template_name,
                    full_name=full_name.strip(),
                    job_title=job_title.strip() if job_title else None,
                    reason=reason.strip() if reason else None,
                )
            finally:
                db.close()
            st.success(f"✅ Email sent to **{email.strip()}** using **{template_name}**.")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("❌ Failed to send email. Check Brevo API key or template settings.")

st.divider()

# ── Log table ──────────────────────────────────────────────────────────────────

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
    df["sent_at"] = pd.to_datetime(df["sent_at"]).dt.strftime("%d %b %Y %H:%M")
    df = df.rename(columns={
        "full_name":     "Name",
        "email":         "Email",
        "job_title":     "Job Title",
        "template_name": "Template",
        "reason":        "Reason",
        "sent_at":       "Sent At",
    })

    st.dataframe(
        df[["Name", "Email", "Job Title", "Template", "Reason", "Sent At"]],
        use_container_width=True,
        hide_index=True,
    )
