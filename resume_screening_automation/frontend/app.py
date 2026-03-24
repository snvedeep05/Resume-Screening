import streamlit as st
import json
import requests
from api_client import create_job, get_jobs, get_job, generate_job_config_ai, update_job, get_headers, get_run_status
import pandas as pd
from io import BytesIO


# MUST BE FIRST
st.set_page_config(page_title="Resume Screening System", layout="wide")



APP_USERNAME = st.secrets["APP_USERNAME"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]
BACKEND_URL = st.secrets["BACKEND_URL"]
COMPANY_LOGO = st.secrets["COMPANY_LOGO"]


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

    # --- MODE SELECTOR ---
    mode = st.radio(
        "Mode",
        ["Create New Job", "Update Existing Job"],
        horizontal=True,
        key="job_config_mode"
    )

    if "job_config" not in st.session_state:
        st.session_state.job_config = None
    if "edit_job_id" not in st.session_state:
        st.session_state.edit_job_id = None

    # -----------------------------------------------
    # CREATE NEW JOB
    # -----------------------------------------------
    if mode == "Create New Job":
        job_title = st.text_input("Job Title", key="new_job_title")
        job_description = st.text_area(
            "Job Description (paste JD here)",
            height=200,
            key="new_job_desc"
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Generate Job Config via AI", key="gen_new"):
                if not job_description:
                    st.error("Please provide Job Description")
                else:
                    try:
                        job_config = generate_job_config_ai(job_description)
                        st.session_state.job_config = job_config
                        st.success("AI generated job config. Please review before saving.")
                    except Exception as e:
                        st.error(f"AI generation failed: {e}")

        if st.session_state.job_config:
            job_config_text = st.text_area(
                "Review / Edit Job Config (JSON)",
                value=json.dumps(st.session_state.job_config, indent=2),
                height=300,
                key="new_job_config_text"
            )

            with col2:
                if st.button("Save Job Config", key="save_new"):
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

    # -----------------------------------------------
    # UPDATE EXISTING JOB
    # -----------------------------------------------
    else:
        existing_jobs = get_jobs()
        if not existing_jobs:
            st.warning("No active job configs found. Create one first.")
        else:
            job_options = {
                f"{j['job_title']} (v{j['version']}) — ID {j['job_id']}": j["job_id"]
                for j in existing_jobs
            }

            selected_label = st.selectbox(
                "Select Job to Update",
                list(job_options.keys()),
                key="update_job_select"
            )
            selected_job_id = job_options[selected_label]

            # Load button — fetches current config from backend
            if st.button("Load Current Config", key="load_existing"):
                try:
                    job_data = get_job(selected_job_id)
                    st.session_state.job_config = job_data["job_config"]
                    st.session_state.edit_job_id = selected_job_id
                    st.success(f"Loaded config for: {job_data['job_title']} (v{job_data['version']})")
                except Exception as e:
                    st.error(f"Failed to load job: {e}")

            # Show editable config once loaded
            if st.session_state.job_config and st.session_state.edit_job_id == selected_job_id:
                current_title = existing_jobs[[j["job_id"] for j in existing_jobs].index(selected_job_id)]["job_title"]

                updated_title = st.text_input(
                    "Job Title",
                    value=current_title,
                    key="update_job_title"
                )

                update_method = st.radio(
                    "How do you want to update the config?",
                    ["Edit JSON directly", "Regenerate from new Job Description (AI)"],
                    horizontal=True,
                    key="update_method"
                )

                if update_method == "Edit JSON directly":
                    updated_config_text = st.text_area(
                        "Edit Job Config (JSON)",
                        value=json.dumps(st.session_state.job_config, indent=2),
                        height=350,
                        key="update_job_config_text"
                    )

                    st.info("Saving will deactivate the current version and create a new one with an incremented version number. Old results are preserved.")

                    if st.button("Save Updated Job Config", key="save_update_json"):
                        try:
                            final_config = json.loads(updated_config_text)
                            result = update_job(selected_job_id, updated_title, final_config)
                            st.success(
                                f"Updated! New Job ID: {result['job_id']} — Version: v{result['version']}"
                            )
                            st.session_state.job_config = None
                            st.session_state.edit_job_id = None
                        except json.JSONDecodeError:
                            st.error("Invalid JSON — please fix the formatting before saving")
                        except Exception as e:
                            st.error(f"Failed to update job config: {e}")

                else:
                    new_job_description = st.text_area(
                        "Paste new Job Description",
                        height=200,
                        key="update_jd_text"
                    )

                    if "update_generated_config" not in st.session_state:
                        st.session_state.update_generated_config = None

                    if st.button("Generate New Config via AI", key="gen_update"):
                        if not new_job_description:
                            st.error("Please paste a job description first")
                        else:
                            try:
                                new_config = generate_job_config_ai(new_job_description)
                                st.session_state.update_generated_config = new_config
                                st.success("AI generated new config. Review before saving.")
                            except Exception as e:
                                st.error(f"AI generation failed: {e}")

                    if st.session_state.update_generated_config:
                        reviewed_config_text = st.text_area(
                            "Review / Edit Generated Config (JSON)",
                            value=json.dumps(st.session_state.update_generated_config, indent=2),
                            height=350,
                            key="update_reviewed_config"
                        )

                        st.info("Saving will deactivate the current version and create a new one with an incremented version number. Old results are preserved.")

                        if st.button("Save as New Version", key="save_update_ai"):
                            try:
                                final_config = json.loads(reviewed_config_text)
                                result = update_job(selected_job_id, updated_title, final_config)
                                st.success(
                                    f"Updated! New Job ID: {result['job_id']} — Version: v{result['version']}"
                                )
                                st.session_state.job_config = None
                                st.session_state.edit_job_id = None
                                st.session_state.update_generated_config = None
                            except json.JSONDecodeError:
                                st.error("Invalid JSON — please fix the formatting before saving")
                            except Exception as e:
                                st.error(f"Failed to update job config: {e}")

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
    if "current_run_id" not in st.session_state:
        st.session_state.current_run_id = None

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
                    data=data,
                    headers=get_headers(),
                    timeout=30
                )

                if res.status_code == 200:
                    response = res.json()
                    st.session_state.current_run_id = response["run_id"]

                    st.success("Screening started successfully ✅")
                    st.markdown(f"**Run ID:** {response['run_id']} · **Batch size:** 10")

                else:
                    st.error("Failed to start screening")
                    st.session_state.screening_started = False

            except Exception as e:
                st.error(f"Error calling backend: {e}")
                st.session_state.screening_started = False

    # ---------- Live Progress (30s polling) ----------
    if st.session_state.current_run_id:

        @st.fragment(run_every=30)
        def show_run_progress():
            run_id = st.session_state.current_run_id
            if not run_id:
                return
            try:
                status = get_run_status(run_id)
                total      = status["total_resumes"] or 1
                processed  = status["processed_count"]
                failed     = status["failed_count"]
                run_status = status["status"]

                if run_status == "completed":
                    st.success(f"✅ Run {run_id} complete — {processed} processed · {failed} failed")
                    st.session_state.current_run_id = None
                elif run_status == "crashed":
                    st.error(f"❌ Run {run_id} crashed — {processed} processed · {failed} failed")
                    st.session_state.current_run_id = None
                else:
                    progress_val = processed / total if total > 0 else 0
                    st.progress(progress_val)
                    st.caption(f"⏳ Run {run_id} — {processed} / {total} processed · {failed} failed")
            except Exception:
                st.caption("Checking run status...")

        show_run_progress()

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
    def fetch_all_results(job_id, limit=500, offset=0):
        res = requests.get(
            f"{BACKEND_URL}/screening/results/{job_id}",
            params={"limit": limit, "offset": offset},
            headers=get_headers(),
            timeout=30
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

    # Convert passed_out_year to nullable int (avoids 2025.0 display)
    if "passed_out_year" in df.columns:
        df["passed_out_year"] = pd.to_numeric(
            df["passed_out_year"], errors="coerce"
        ).astype("Int64")

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

    col3, col4 = st.columns(2)

    with col3:
        decision_filter = st.selectbox(
            "Decision",
            ["All", "shortlisted", "rejected"],
            key="results_decision_filter"
        )

    with col4:
        year_filter = st.selectbox(
            "Passed Out Year",
            ["All", "2025 & above", "2026 & above", "2027 & above"],
            key="results_year_filter"
        )

    min_score = st.slider(
        "Minimum Score",
        0,
        100,
        0,
        key="results_min_score"
    )

    sort_order = st.selectbox(
        "Sort by",
        ["Recently Processed", "Score: High to Low", "Score: Low to High"],
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
            filtered_df["processed_at"] < pd.to_datetime(to_date) + pd.Timedelta(days=1)
        ]

    if decision_filter != "All":
        filtered_df = filtered_df[
            filtered_df["decision"] == decision_filter
        ]

    if year_filter != "All" and "passed_out_year" in filtered_df.columns:
        min_year = int(year_filter.split("&")[0].strip())
        filtered_df = filtered_df[
            filtered_df["passed_out_year"].notna() &
            (filtered_df["passed_out_year"] >= min_year)
        ]

    filtered_df = filtered_df[
        filtered_df["score"] >= min_score
    ]

    if sort_order == "Recently Processed":
        filtered_df = filtered_df.sort_values(by="processed_at", ascending=False)
    else:
        filtered_df = filtered_df.sort_values(
            by="score",
            ascending=(sort_order == "Score: Low to High")
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

    display_cols = [
        "full_name", "email", "phone",
        "job_title", "passed_out_year",
        "score", "decision", "decision_reason", "processed_at"
    ]
    display_cols = [c for c in display_cols if c in filtered_df.columns]

    st.dataframe(
        filtered_df[display_cols],
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
