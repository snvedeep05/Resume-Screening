import streamlit as st
import pandas as pd
import altair as alt
from email_db_client import get_session, get_all_logs
from email_utils import show_brevo_usage

st.set_page_config(page_title="Email Dashboard", page_icon="📊", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Please login first.")
    st.stop()

TEMPLATE_LABELS = {
    28: "Shortlisted",
    36: "Rejected",
    30: "Assignment",
}

st.title("📊 Email Sent Dashboard")

show_brevo_usage()

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

db = get_session()
try:
    logs = get_all_logs(db)
finally:
    db.close()

if not logs:
    st.info("No emails have been sent yet.")
    st.stop()

df_logs = pd.DataFrame(logs)
df_logs["email_type"] = df_logs["template_id"].map(TEMPLATE_LABELS).fillna("Unknown")
df_logs["sent_at"]    = pd.to_datetime(df_logs["sent_at"])

# ── Metrics ───────────────────────────────────────────────────────────────────
total      = len(df_logs)
shortlisted = (df_logs["template_id"] == 28).sum()
rejected    = (df_logs["template_id"] == 36).sum()
assignment  = (df_logs["template_id"] == 30).sum()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sent",   total)
c2.metric("Shortlisted",  int(shortlisted))
c3.metric("Rejected",     int(rejected))
c4.metric("Assignment",   int(assignment))

st.divider()

# ── Bar chart — Shortlisted vs Rejected per date ──────────────────────────────
st.markdown("### Emails Sent by Date")
chart_df = df_logs[df_logs["email_type"].isin(["Shortlisted", "Rejected"])].copy()
chart_df["date"] = chart_df["sent_at"].dt.strftime("%d %b %Y")
grouped = chart_df.groupby(["date", "email_type"]).size().reset_index(name="Count")

chart = alt.Chart(grouped).mark_bar(size=35).encode(
    x=alt.X("date:N", title="Date", sort=None),
    xOffset=alt.XOffset("email_type:N"),
    y=alt.Y("Count:Q", title="Count"),
    color=alt.Color(
        "email_type:N",
        scale=alt.Scale(domain=["Shortlisted", "Rejected"], range=["#4f86f7", "#ef4444"]),
        legend=alt.Legend(title="Type")
    )
).properties(height=300)

st.altair_chart(chart, use_container_width=True)

st.divider()

# ── Log table ─────────────────────────────────────────────────────────────────
st.markdown("### Sent Email Log")

filter_type = st.selectbox(
    "Filter by email type",
    options=["All"] + list(TEMPLATE_LABELS.values()),
    key="dashboard_filter"
)

df_view = df_logs.copy()
if filter_type != "All":
    df_view = df_view[df_view["email_type"] == filter_type]

df_view = df_view[["full_name", "email", "email_type", "job_title", "resume_file", "sent_at"]].rename(columns={
    "full_name":   "Name",
    "email":       "Email",
    "email_type":  "Type",
    "job_title":   "Job Title",
    "resume_file": "Resume File",
    "sent_at":     "Sent At",
})

st.dataframe(df_view, use_container_width=True)

csv = df_view.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇️ Download CSV",
    data=csv,
    file_name="email_log_export.csv",
    mime="text/csv"
)
