import streamlit as st
import os
import json
import requests
from api_client import create_job, get_jobs, generate_job_config_ai
import pandas as pd
from io import BytesIO
BACKEND_URL = os.getenv("BACKEND_URL")


from dotenv import load_dotenv

# MUST BE FIRST
st.set_page_config(page_title="Resume Screening System", layout="wide")

load_dotenv()

APP_USERNAME = os.getenv("APP_USERNAME")
APP_PASSWORD = os.getenv("APP_PASSWORD")
BACKEND_URL = os.getenv("BACKEND_URL")

# 👇 PUT YOUR LOGO IMAGE PATH OR URL HERE
COMPANY_LOGO = os.getenv("COMPANY_LOGO")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


def login_page():

    st.markdown(
        """
        <style>
        /* Add breathing room at the top of the login page */
        .block-container {
            padding-top: 8.5rem;
        }

        /* Company header */
        .company-header {
            display: flex;
            align-items: center;
            gap: 12px;
            position: fixed;
            top: 1.2rem;
            left: 1.8rem;
            margin-bottom: 0;
            z-index: 1000;
        }

        .company-name {
            font-size: 20px;
            font-weight: 600;
            color: #1f2937;
        }

        .login-title {
            font-size: 40px;
            font-weight: 700;
            line-height: 1.1;
            margin-bottom: 2rem;
            color: #111827;
        }

        

        /* Hide weird top header block */
        [data-testid="stHeader"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------------- COMPANY LOGO + NAME ----------------
    st.markdown(
        f"""
        <div class="company-header">
            <img src="{COMPANY_LOGO}" width="45">
            <div class="company-name">Appweave Labs</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ---------------- CENTER LOGIN ----------------
    col1, col2, col3 = st.columns([2, 1.2, 2])

    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)

        st.markdown(
            '<div class="login-title">🔐 Resume Screening</div>',
            unsafe_allow_html=True
        )

        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Login", use_container_width=True):
            if username == APP_USERNAME and password == APP_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Invalid credentials")

        st.markdown("</div>", unsafe_allow_html=True)



if not st.session_state.logged_in:
    login_page()
    st.stop()


    
st.title("📄 Resume Screening System")

tab1, tab2, tab3 = st.tabs(["🟦 Resume Screening", "🟩 Job Config Builder", "📊 Results Dashboard"])

# ======================================================
# TAB 2: JOB CONFIG BUILDER
# ======================================================
with tab2:
    st.subheader("Job Config Builder (AI Assisted)")

    job_title = st.text_input("Job Title")
    job_description = st.text_area(
        "Job Description (paste JD here)",
        height=200
    )

    if "job_config" not in st.session_state:
        st.session_state.job_config = None

    col1, col2 = st.columns(2)

    # --- AI GENERATION ---
    with col1:
        if st.button("Generate Job Config via AI"):
            if not job_description:
                st.error("Please provide Job Description")
            else:
                try:
                    job_config = generate_job_config_ai(job_description)
                    st.session_state.job_config = job_config
                    st.success("AI generated job config. Please review before saving.")
                except Exception as e:
                    st.error(f"AI generation failed: {e}")

    # --- SHOW EDITABLE JSON ONLY IF EXISTS ---
    if st.session_state.job_config:
        job_config_text = st.text_area(
            "Review / Edit Job Config (JSON)",
            value=json.dumps(st.session_state.job_config, indent=2),
            height=300
        )

        with col2:
            if st.button("Save Job Config"):
                if not job_title:
                    st.error("Job title is required")
                else:
                    try:
                        final_job_config = json.loads(job_config_text)
                        result = create_job(job_title, final_job_config)
                        st.success(f"Job config saved (ID: {result['job_id']})")
                        st.session_state.job_config = None
                    except json.JSONDecodeError:
                        st.error("Invalid JSON format")
                    except Exception as e:
                        st.error(f"Failed to save job config: {e}")

# ======================================================
# TAB 1: RESUME SCREENING
# ======================================================
with tab1:
    st.header("Resume Screening")

    # ---------- Load Jobs ----------
    jobs = get_jobs()
    if not jobs:
        st.warning("No job configs available. Please create one first.")
        st.stop()

    job_options = {job["job_title"]: job["job_id"] for job in jobs}
    selected_job = st.selectbox("Select Job", job_options.keys())
    selected_job_id = job_options[selected_job]

    # ---------- File Upload ----------
    zip_file = st.file_uploader(
        "Upload ZIP of resumes",
        type=["zip"]
    )

    # ---------- Session State ----------
    if "screening_started" not in st.session_state:
        st.session_state.screening_started = False

    # ---------- Start Screening ----------
    if st.button(
        "Start Screening",
        #disabled=st.session_state.screening_started
    ):
        if not zip_file:
            st.error("Please upload a ZIP file")
        else:
            st.session_state.screening_started = True

            files = {
                "zip_file": (
                    zip_file.name,
                    zip_file.getvalue(),
                    "application/zip"
                )
            }
            data = {
                "job_id": selected_job_id,
                "batch_size": 10
            }

            try:
                res = requests.post(
                    f"{BACKEND_URL}/screening/start",
                    files=files,
                    data=data
                )

                if res.status_code == 200:
                    response = res.json()

                    st.success("Screening started successfully ✅")

                    st.markdown(
                        f"""
                        **Run ID:** {response["run_id"]}  
                        **Batch size:** 10  

                        📌 *Resumes are now being processed in the background.*  
                        📌 *Live batch & resume updates are visible in the backend terminal.*
                        """
                    )

                else:
                    st.error("Failed to start screening")
                    st.session_state.screening_started = False

            except Exception as e:
                st.error(f"Error calling backend: {e}")
                st.session_state.screening_started = False

with tab3:
    st.header("📊 Results Dashboard")

    # Refresh Button
    if st.button("🔄 Refresh Results"):
        st.cache_data.clear()
        st.rerun()
        
    jobs = get_jobs()
    if not jobs:
        st.warning("No jobs available.")
        st.stop()

    job_options = {job["job_title"]: job["job_id"] for job in jobs}

    selected_job = st.selectbox(
        "Select Job",
        job_options.keys(),
        key="results_job_select"
    )
    selected_job_id = job_options[selected_job]

    # ----------------------------
    # FETCH DATA (ONCE PER JOB)
    # ----------------------------

    @st.cache_data(ttl=300)
    def fetch_all_results(job_id):
        res = requests.get(
            f"{BACKEND_URL}/screening/results/{job_id}"
        )
        if res.status_code != 200:
            return pd.DataFrame()
        return pd.DataFrame(res.json())

    df = fetch_all_results(selected_job_id)

    if df.empty:
        st.info("No results found for this job.")
        st.stop()

    # Convert datetime safely
    if "processed_at" in df.columns:
        df["processed_at"] = pd.to_datetime(df["processed_at"])

    # ----------------------------
    # FILTERS
    # ----------------------------

    st.subheader("Filters")

    col1, col2 = st.columns(2)

    with col1:
        from_date = st.date_input(
            "From Date",
            key="results_from_date"
        )

    with col2:
        to_date = st.date_input(
            "To Date",
            key="results_to_date"
        )

    decision_filter = st.selectbox(
        "Decision",
        ["All", "shortlisted", "rejected"],
        key="results_decision_filter"
    )

    min_score = st.slider(
        "Minimum Score",
        0,
        100,
        0,
        key="results_min_score"
    )

    sort_order = st.selectbox(
        "Sort by Score",
        ["Descending", "Ascending"],
        key="results_sort_order"
    )

    # ----------------------------
    # LOCAL FILTERING
    # ----------------------------

    filtered_df = df.copy()

    if from_date:
        filtered_df = filtered_df[
            filtered_df["processed_at"] >= pd.to_datetime(from_date)
        ]

    if to_date:
        filtered_df = filtered_df[
            filtered_df["processed_at"] <= pd.to_datetime(to_date)
        ]

    if decision_filter != "All":
        filtered_df = filtered_df[
            filtered_df["decision"] == decision_filter
        ]

    filtered_df = filtered_df[
        filtered_df["score"] >= min_score
    ]

    filtered_df = filtered_df.sort_values(
        by="score",
        ascending=(sort_order == "Ascending")
    )

    # ----------------------------
    # SUMMARY METRICS
    # ----------------------------

    st.subheader("Summary")

    total_count = len(filtered_df)
    shortlisted_count = len(
        filtered_df[filtered_df["decision"] == "shortlisted"]
    )
    rejected_count = len(
        filtered_df[filtered_df["decision"] == "rejected"]
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Total", total_count)
    col2.metric("Shortlisted", shortlisted_count)
    col3.metric("Rejected", rejected_count)

    # ----------------------------
    # DISPLAY TABLE
    # ----------------------------

    st.subheader("Results")

    st.dataframe(
        filtered_df,
        use_container_width=True
    )

    # ----------------------------
    # DOWNLOAD EXCEL
    # ----------------------------

    

    output = BytesIO()
    filtered_df.to_excel(output, index=False)
    output.seek(0)

    st.download_button(
        "📥 Download Excel",
        data=output,
        file_name="filtered_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="results_download_button"
    )
    
    json_data = filtered_df.to_dict(orient="records")

    st.download_button(
        "📥 Download JSON",
        data=json.dumps(json_data, indent=2, default=str),
        file_name="filtered_results.json",
        mime="application/json",
        key="results_download_json"
    )
