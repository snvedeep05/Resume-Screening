import io
import streamlit as st
import pandas as pd
from email_validator import validate_email, EmailNotValidError  # used at parse time
from datetime import datetime, timedelta
from brevo_client import BrevoClient
from email_db_client import get_session, is_already_sent, log_email_sent
from email_utils import show_brevo_usage, fetch_brevo_stats, BREVO_DAILY_LIMIT

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

    # ── Validate emails at parse time ─────────────────────────────────────────
    def _try_validate(email):
        try:
            return validate_email(str(email).strip()).email
        except EmailNotValidError:
            return None

    df["email"] = df["email"].apply(_try_validate)
    invalid_df  = df[df["email"].isna()].copy()
    df          = df[df["email"].notna()].copy()

    if not invalid_df.empty:
        st.warning(f"⚠️ {len(invalid_df)} row(s) have invalid emails and will be skipped:")
        st.dataframe(invalid_df[["full_name", "email"]].assign(email="(invalid)"), use_container_width=True)

    if df.empty:
        st.error("No valid email addresses found in the uploaded file.")
        st.stop()

    st.markdown("### Candidate Preview")
    st.dataframe(df, use_container_width=True)
    st.markdown(f"Total candidates: **{len(df)}**")

    if st.button("🚀 Send Assignment Emails"):

        stats           = fetch_brevo_stats()
        quota_remaining = max(BREVO_DAILY_LIMIT - stats["requests"], 0)

        if quota_remaining == 0:
            st.error("🚫 Brevo daily limit reached (0 emails remaining). Try again after midnight UTC.")
            st.stop()

        client        = BrevoClient()
        db            = get_session()
        deadline_date = (datetime.today() + timedelta(days=10)).strftime("%d %B %Y")

        sent              = 0
        skipped_list      = []
        already_sent_list = []
        pending_rows      = []
        sent_rows         = []
        progress          = st.progress(0)

        try:
            for i, (_, row) in enumerate(df.iterrows()):

                name       = str(row["full_name"]).strip()
                email      = str(row["email"]).strip()
                job_title  = str(row.get("job_title", "")).strip()
                first_name = name.split()[0]

                if is_already_sent(db, email, TEMPLATE_ASSIGNMENT):
                    already_sent_list.append(f"{name} — {email}")
                    progress.progress((i + 1) / len(df))
                    continue

                if quota_remaining <= 0:
                    pending_rows.append({"full_name": name, "email": email, "job_title": job_title})
                    progress.progress((i + 1) / len(df))
                    continue

                success = client.send_template_email(
                    to_email=email,
                    template_id=TEMPLATE_ASSIGNMENT,
                    params={"FIRSTNAME": first_name, "DEADLINE_DATE": deadline_date},
                    to_name=name
                )

                if success:
                    log_email_sent(db, email, TEMPLATE_ASSIGNMENT, full_name=name, job_title=job_title)
                    sent_rows.append({"full_name": name, "email": email, "job_title": job_title})
                    sent += 1
                    quota_remaining -= 1
                else:
                    skipped_list.append(f"{name} — {email} (send failed)")

                progress.progress((i + 1) / len(df))

        finally:
            db.close()

        st.cache_data.clear()  # refresh usage indicator
        st.success(f"✅ Done — {sent} assignment email(s) sent.")

        if sent_rows:
            sent_df   = pd.DataFrame(sent_rows)
            buf       = io.BytesIO()
            sent_df.to_excel(buf, index=False)
            base_name = uploaded_excel.name.replace(".xlsx", "")
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            st.download_button(
                label="⬇️ Download Sent Emails List",
                data=buf.getvalue(),
                file_name=f"sent_{base_name}_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if pending_rows:
            st.warning(f"⚠️ Daily limit reached — {len(pending_rows)} email(s) not sent. Download below and send tomorrow.")
            pending_df = pd.DataFrame(pending_rows)
            buf        = io.BytesIO()
            pending_df.to_excel(buf, index=False)
            base_name  = uploaded_excel.name.replace(".xlsx", "")
            st.download_button(
                label="⬇️ Download Pending Emails",
                data=buf.getvalue(),
                file_name=f"pending_{base_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if already_sent_list:
            st.info(f"⏩ Already sent (skipped): {len(already_sent_list)}")
            for entry in already_sent_list:
                st.caption(f"  • {entry}")

        if skipped_list:
            st.warning(f"⏭ Skipped / Failed: {len(skipped_list)}")
            for entry in skipped_list:
                st.caption(f"  • {entry}")
