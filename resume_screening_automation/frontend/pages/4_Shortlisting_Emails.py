import streamlit as st
import pandas as pd
from email_validator import validate_email, EmailNotValidError
from brevo_client import BrevoClient
from email_db_client import get_session, is_already_sent, log_email_sent
from email_utils import show_brevo_usage

st.set_page_config(page_title="Shortlisting Emails", page_icon="📧", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Please login first.")
    st.stop()

TEMPLATE_SHORTLISTED = 28
TEMPLATE_REJECTED    = 36

st.title("📧 Shortlisting / Rejection Emails")

show_brevo_usage()

uploaded_excel = st.file_uploader(
    "Upload reviewed Excel file",
    type=["xlsx"],
    key="shortlist_upload"
)

if uploaded_excel:

    df = pd.read_excel(uploaded_excel)

    required_cols = ["full_name", "email", "decision", "job_title"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        st.error(f"Missing required columns: {missing}")
        st.stop()

    df = df.rename(columns={
        "full_name": "Name",
        "email":     "Email",
        "decision":  "Decision",
        "job_title": "Job_Title"
    })

    df = df.drop_duplicates(subset=["Email"])

    if df.empty:
        st.warning("Uploaded Excel has no rows to process.")
        st.stop()

    st.dataframe(df, use_container_width=True)

    st.markdown("### Decision Summary")
    counts = df["Decision"].value_counts()

    c1, c2 = st.columns(2)
    c1.metric("Shortlisted", counts.get("shortlisted", 0))
    c2.metric("Rejected",    counts.get("rejected", 0))

    if st.button("🚀 Send Emails"):

        client = BrevoClient()
        db     = get_session()

        sent             = 0
        skipped_list     = []
        already_sent_list = []
        progress         = st.progress(0)

        try:
            for i, (_, row) in enumerate(df.iterrows()):

                name      = str(row["Name"]).strip()
                email     = str(row["Email"]).strip()
                decision  = str(row["Decision"]).strip().lower()
                job_title = str(row["Job_Title"]).strip()

                try:
                    email = validate_email(email).email
                except EmailNotValidError:
                    skipped_list.append(f"{name} — {email} (invalid email)")
                    continue

                if decision == "shortlisted":
                    template_id = TEMPLATE_SHORTLISTED
                elif decision == "rejected":
                    template_id = TEMPLATE_REJECTED
                else:
                    skipped_list.append(f"{name} — {email} (unknown decision: {decision})")
                    continue

                if is_already_sent(db, email, template_id):
                    already_sent_list.append(f"{name} — {email}")
                    continue

                success = client.send_template_email(
                    to_email=email,
                    template_id=template_id,
                    params={"FIRSTNAME": name, "JOB_TITLE": job_title},
                    to_name=name
                )

                if success:
                    log_email_sent(db, email, template_id, full_name=name, job_title=job_title)
                    sent += 1
                else:
                    skipped_list.append(f"{name} — {email} (send failed)")

                progress.progress((i + 1) / len(df))

        finally:
            db.close()

        st.cache_data.clear()  # refresh usage indicator
        st.success(f"✅ Done — {sent} email(s) sent.")

        if already_sent_list:
            st.info(f"⏩ Already sent (skipped): {len(already_sent_list)}")
            for entry in already_sent_list:
                st.caption(f"  • {entry}")

        if skipped_list:
            st.warning(f"⏭ Skipped / Failed: {len(skipped_list)}")
            for entry in skipped_list:
                st.caption(f"  • {entry}")
