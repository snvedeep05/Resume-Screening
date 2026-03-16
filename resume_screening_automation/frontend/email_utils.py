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
        dot_color = "#ef4444"
        label     = "Critical"
    elif pct >= 0.67:
        dot_color = "#f59e0b"
        label     = "Moderate"
    else:
        dot_color = "#22c55e"
        label     = "Healthy"

    bar_filled = int(pct * 20)
    bar_str    = "█" * bar_filled + "░" * (20 - bar_filled)

    st.markdown(
        f"""
        <div style="
            background:#f9fafb;
            border:1px solid #e5e7eb;
            border-radius:10px;
            padding:10px 18px;
            display:flex;
            align-items:center;
            gap:20px;
            flex-wrap:wrap;
            margin-bottom:6px;
        ">
            <span style="font-size:13px; font-weight:600; color:#111827;">
                📬 Brevo&nbsp;<span style="color:{dot_color};">●</span>&nbsp;{label}
            </span>
            <span style="font-family:monospace; font-size:13px; color:#374151;">
                {bar_str}&nbsp;<b>{used}/{BREVO_DAILY_LIMIT}</b>
            </span>
            <span style="font-size:13px; color:#6b7280;">🟩 {remaining} left</span>
            <span style="font-size:13px; color:#6b7280;">✅ {stats["delivered"]} delivered</span>
            <span style="font-size:13px; color:#6b7280;">⚠️ {bounces} bounced</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

    with st.expander("🔍 Debug: Brevo API raw response"):
        st.code(stats.get("debug_plans", "N/A"))
