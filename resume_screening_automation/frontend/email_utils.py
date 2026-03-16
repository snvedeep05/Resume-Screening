import streamlit as st
from brevo_client import BrevoClient

BREVO_DAILY_LIMIT = 300


@st.cache_data(ttl=60)
def fetch_brevo_stats() -> dict:
    return BrevoClient().get_daily_stats()


def show_brevo_usage():
    stats = fetch_brevo_stats()

    used      = stats["requests"]
    remaining = max(BREVO_DAILY_LIMIT - used, 0)
    bounces   = stats["hard_bounces"] + stats["soft_bounces"]
    pct       = min(used / BREVO_DAILY_LIMIT, 1.0)

    if pct >= 0.9:
        icon = "🔴"
    elif pct >= 0.67:
        icon = "🟡"
    else:
        icon = "🟢"

    st.markdown(f"#### {icon} Brevo Daily Usage")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sent Today",  f"{used} / {BREVO_DAILY_LIMIT}")
    c2.metric("Remaining",   remaining)
    c3.metric("Delivered",   stats["delivered"])
    c4.metric("Bounced",     bounces)

    st.progress(pct)
    st.divider()
