import streamlit as st
import pandas as pd
from email_validator import validate_email, EmailNotValidError
from datetime import datetime, timedelta
from brevo_client import BrevoClient
from email_db_client import get_session, is_already_sent, log_email_sent
from email_utils import show_brevo_usage

st.set_page_config(page_title="Assignment Emails", page_icon="📝", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Please login first.")
    st.stop()

TEMPLATE_ASSIGNMENT = 30

st.title("📝 Assignment Emails")

show_brevo_usage()

uploaded_excel = st.file_uploader(
    "Upload Excel with interested candidates",
    type=["xlsx"],
    key="assignment_upload"
)

if uploaded_excel:

    df = pd.read_excel(uploaded_excel)

    required_cols = ["full_name", "email", "job_title"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        st.error(f"Missing required columns: {missing}")
        st.stop()

    df = df.drop_duplicates(subset=["email"])

    if df.empty:
        st.warning("Excel has no valid rows.")
        st.stop()

    st.markdown("### Candidate Preview")
    st.dataframe(df, use_container_width=True)
    st.markdown(f"Total candidates: **{len(df)}**")

    if st.button("🚀 Send Assignment Emails"):

        client        = BrevoClient()
        db            = get_session()
        deadline_date = (datetime.today() + timedelta(days=10)).strftime("%d %B %Y")

        sent              = 0
        skipped_list      = []
        already_sent_list = []
        progress          = st.progress(0)

        try:
            for i, (_, row) in enumerate(df.iterrows()):

                name      = str(row["full_name"]).strip()
                email     = str(row["email"]).strip()
                job_title = str(row.get("job_title", "")).strip()
                first_name = name.split()[0]

                try:
                    email = validate_email(email).email
                except EmailNotValidError:
                    skipped_list.append(f"{name} — {email} (invalid email)")
                    continue

                if is_already_sent(db, email, TEMPLATE_ASSIGNMENT):
                    already_sent_list.append(f"{name} — {email}")
                    continue

                success = client.send_template_email(
                    to_email=email,
                    template_id=TEMPLATE_ASSIGNMENT,
                    params={"FIRSTNAME": first_name, "DEADLINE_DATE": deadline_date},
                    to_name=name
                )

                if success:
                    log_email_sent(db, email, TEMPLATE_ASSIGNMENT, full_name=name, job_title=job_title)
                    sent += 1
                else:
                    skipped_list.append(f"{name} — {email} (send failed)")

                progress.progress((i + 1) / len(df))

        finally:
            db.close()

        st.cache_data.clear()  # refresh usage indicator
        st.success(f"✅ Done — {sent} assignment email(s) sent.")

        if already_sent_list:
            st.info(f"⏩ Already sent (skipped): {len(already_sent_list)}")
            for entry in already_sent_list:
                st.caption(f"  • {entry}")

        if skipped_list:
            st.warning(f"⏭ Skipped / Failed: {len(skipped_list)}")
            for entry in skipped_list:
                st.caption(f"  • {entry}")
