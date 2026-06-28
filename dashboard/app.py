import sys
import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from database.db_manager_multiuser import (
    init_db, create_user, get_user, update_user_cv,
    update_user_prefs, set_auto_apply, get_jobs, get_jobs_awaiting_review,
    get_jobs_needing_manual,
)

st.set_page_config(page_title="HiredAI", page_icon="🎯", layout="wide")
init_db()

GROQ_KEY_SET = bool(os.getenv("GROQ_API_KEY"))
ADZUNA_KEYS_SET = bool(os.getenv("ADZUNA_APP_ID")) and bool(os.getenv("ADZUNA_API_KEY"))

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Fresh light gradient backdrop */
    .stApp {
        background: linear-gradient(160deg, #eef2ff 0%, #e0f2fe 45%, #ecfeff 100%);
        background-attachment: fixed;
    }
    .block-container { padding-top: 2rem; max-width: 1100px; }

    h1, h2, h3 { color: #0f172a; }
    h1 { font-weight: 800; font-size: 2.3rem; letter-spacing: -0.8px; }
    h2, h3 { font-weight: 600; }
    p, label, .stMarkdown { color: #334155; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: rgba(255,255,255,0.6);
        backdrop-filter: blur(8px);
        padding: 6px;
        border-radius: 14px;
        border: 1px solid #c7d2fe;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 8px 22px;
        font-weight: 500;
        color: #64748b;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%) !important;
        color: white !important;
        box-shadow: 0 4px 14px rgba(99,102,241,0.35);
    }

    /* Cards */
    .metric-card {
        background: rgba(255,255,255,0.8);
        backdrop-filter: blur(8px);
        border: 1px solid #c7d2fe;
        border-radius: 16px;
        padding: 22px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(99,102,241,0.08);
    }
    .metric-value {
        font-size: 2.1rem; font-weight: 800;
        background: linear-gradient(135deg, #6366f1, #06b6d4);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .metric-label { font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.6px; margin-top: 4px; }

    .job-card {
        background: rgba(255,255,255,0.85);
        backdrop-filter: blur(10px);
        border: 1px solid #c7d2fe;
        border-radius: 18px;
        padding: 22px 24px;
        margin-bottom: 8px;
        box-shadow: 0 6px 24px rgba(99,102,241,0.10);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .job-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 32px rgba(6,182,212,0.18);
    }
    .job-title { font-size: 1.1rem; font-weight: 700; margin: 0; color: #0f172a; }
    .job-meta { color: #64748b; font-size: 0.85rem; margin-top: 4px; }

    /* Score badges — cool palette */
    .score-badge {
        display: inline-flex; align-items: center;
        padding: 5px 14px; border-radius: 20px;
        font-size: 0.85rem; font-weight: 600;
    }
    .score-high { background: #ccfbf1; color: #0f766e; border: 1px solid #5eead4; }
    .score-mid  { background: #e0e7ff; color: #4338ca; border: 1px solid #a5b4fc; }
    .score-low  { background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }

    /* Buttons */
    .stButton > button {
        border-radius: 10px; font-weight: 600;
        border: 1px solid #c7d2fe;
        transition: all 0.2s;
    }
    .stButton > button:hover { border-color: #6366f1; color: #4338ca; }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%);
        border: none; color: white;
        box-shadow: 0 4px 14px rgba(99,102,241,0.35);
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(6,182,212,0.45);
        color: white;
    }
    .stDownloadButton > button { border-radius: 10px; font-weight: 500; }

    [data-testid="stFileUploader"] { border-radius: 12px; }
    .stTextArea textarea {
        border-radius: 10px; font-size: 0.9rem;
        background: rgba(255,255,255,0.9); border: 1px solid #c7d2fe;
    }

    div[data-testid="stExpander"] {
        border: 1px solid #c7d2fe; border-radius: 12px;
        background: rgba(255,255,255,0.7);
    }
    .stLinkButton > a {
        border-radius: 10px; font-weight: 500;
    }

    /* Inline tailoring notices */
    .notice {
        display: flex; align-items: flex-start; gap: 8px;
        padding: 9px 14px; border-radius: 10px;
        font-size: 0.84rem; margin: 4px 0 2px;
    }
    .notice-ok   { background: #ccfbf1; color: #0f766e; border: 1px solid #5eead4; }
    .notice-warn { background: #fef9c3; color: #854d0e; border: 1px solid #fde047; }
    .notice b { font-weight: 600; }

    footer { display: none; }
    #MainMenu { display: none; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


if "user_id" not in st.session_state:
    st.session_state.user_id = create_user()

user_id = st.session_state.user_id
user = get_user(user_id)

st.markdown("# 🎯 HiredAI")
st.markdown("<p style='color:#64748b;font-size:1.05rem;margin-top:-12px;margin-bottom:24px'>Your AI job application agent — find, tailor, and apply with one click.</p>", unsafe_allow_html=True)

if not GROQ_KEY_SET:
    st.warning("Missing GROQ_API_KEY in `.env` — CV parsing, matching and cover letters need it.")

tab_setup, tab_review, tab_history = st.tabs(["⚙️  Setup", "📋  Review queue", "📊  History"])


def score_color(score: float) -> str:
    if score >= 0.75:
        return "score-high"
    if score >= 0.55:
        return "score-mid"
    return "score-low"


def score_label(score: float) -> str:
    if score >= 0.75:
        return "Strong match"
    if score >= 0.55:
        return "Decent match"
    return "Weak match"


with tab_setup:
    col_cv, col_prefs = st.columns([1, 1], gap="large")

    with col_cv:
        st.markdown("### Upload CV")
        uploaded_cv = st.file_uploader("PDF format", type=["pdf"], label_visibility="collapsed")

        if uploaded_cv is not None:
            user_cv_dir = Path(__file__).parent.parent / "data" / "users" / user_id / "cv"
            user_cv_dir.mkdir(parents=True, exist_ok=True)
            cv_path = user_cv_dir / "my_cv.pdf"
            cv_path.write_bytes(uploaded_cv.getvalue())
            st.success(f"Saved: {uploaded_cv.name}")

            if st.button("Parse & structure CV", type="primary", disabled=not GROQ_KEY_SET):
                with st.spinner("Reading your CV..."):
                    from matching.cv_parser import extract_text_from_pdf
                    from matching.build_structured_cv import EXTRACTION_PROMPT
                    import requests

                    raw_text = extract_text_from_pdf(cv_path)

                if not raw_text.strip():
                    st.error(
                        "No text could be extracted from this PDF. If it's a scanned "
                        "image, export a text-based PDF and re-upload."
                    )
                else:
                    with st.spinner("Structuring your CV with AI..."):
                        try:
                            resp = requests.post(
                                "https://api.groq.com/openai/v1/chat/completions",
                                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                                         "Content-Type": "application/json"},
                                json={
                                    "model": "llama-3.3-70b-versatile",
                                    "messages": [{"role": "user", "content": EXTRACTION_PROMPT.format(cv_text=raw_text[:6000])}],
                                    "max_tokens": 2500,
                                    "temperature": 0.1,
                                },
                                timeout=40,
                            )
                            data = resp.json()
                        except Exception as e:
                            data = {"error": {"message": f"Network error contacting Groq: {e}"}}

                    # Groq returns an "error" object instead of "choices" on
                    # rate limits, bad keys, decommissioned models, etc.
                    if "choices" not in data:
                        err = (data.get("error") or {}).get("message") or str(data)[:300]
                        st.error(f"Groq couldn't process the CV: {err}")
                    else:
                        raw_output = data["choices"][0]["message"]["content"].strip()
                        if raw_output.startswith("```"):
                            raw_output = raw_output.split("```")[1]
                            if raw_output.startswith("json"):
                                raw_output = raw_output[4:]
                        try:
                            structured = json.loads(raw_output.strip())
                            update_user_cv(user_id, structured)
                            st.success("CV structured successfully.")
                        except json.JSONDecodeError:
                            st.error("Couldn't parse the CV — try again or check the PDF quality.")

        user = get_user(user_id)
        if user.get("cv_structured"):
            with st.expander("View structured CV"):
                st.json(json.loads(user["cv_structured"]))
        else:
            st.caption("No structured CV yet. Upload a PDF above to get started.")

    with col_prefs:
        st.markdown("### Job preferences")
        default_prefs = json.loads(user["job_prefs"]) if user.get("job_prefs") else {}

        job_titles = st.text_area(
            "Job titles (one per line)",
            value="\n".join(default_prefs.get("job_titles", ["Data Scientist", "Software Engineer"])),
            height=100,
        )
        seniority = st.multiselect(
            "Seniority / level",
            ["intern", "graduate", "entry", "junior", "mid", "senior"],
            default=default_prefs.get("seniority_levels", ["entry", "junior"]),
            help="Roles outside these levels (e.g. senior) are filtered out. "
                 "'intern' covers internships/placements; 'graduate' covers grad "
                 "schemes, trainee and early-careers roles."
        )
        work_types = st.multiselect(
            "Work type", ["remote", "hybrid", "onsite"],
            default=default_prefs.get("work_types", ["remote"]),
            help="If you pick only 'remote', onsite roles outside your region "
                 "are filtered out automatically."
        )
        locations = st.multiselect(
            "Preferred locations / countries",
            ["remote", "UK", "USA", "Canada", "Germany", "Netherlands",
             "Australia", "India", "South Africa", "Ghana", "Nigeria"],
            default=default_prefs.get("locations", ["remote"]),
            help="Used to pick which country's listings Adzuna searches and to "
                 "drop onsite roles outside these places. Adzuna has no Nigeria/Ghana "
                 "board, so from there you'll mostly get remote roles."
        )
        sponsorship_required = st.checkbox(
            "Prioritise visa sponsorship roles",
            value=default_prefs.get("sponsorship_required", False)
        )
        min_match = st.slider(
            "Minimum match score", 0.0, 1.0,
            default_prefs.get("min_match_score", 0.55), step=0.05,
            help="A realistic strong match scores ~70–90%. 0.55 is a sensible "
                 "starting point; raise it to be pickier."
        )
        auto_apply_choice = st.radio(
            "Submission mode",
            ["Review each one first (recommended)", "Apply automatically (skip review)"],
            index=0 if not user.get("auto_apply") else 1,
            help="Automatic mode submits every prepared application without "
                 "showing you the review queue. Use with caution."
        )

        if st.button("Save preferences", type="primary"):
            prefs = {
                "job_titles": [t.strip() for t in job_titles.split("\n") if t.strip()],
                "seniority_levels": seniority,
                "work_types": work_types,
                "locations": locations,
                "sponsorship_required": sponsorship_required,
                "min_match_score": min_match,
            }
            update_user_prefs(user_id, prefs)
            set_auto_apply(user_id, auto_apply_choice.startswith("Apply automatically"))
            st.success("Preferences saved.")

    st.divider()
    st.markdown("### Saved logins (stay signed in)")
    from applicator.session_manager import (
        has_saved_session, open_login_browser, clear_session, test_saved_login,
    )

    if has_saved_session(user_id):
        st.markdown(
            '<div class="notice notice-ok">✅ <span>You have a saved browser '
            'session. Sites you logged into stay signed in for future '
            'applications.</span></div>',
            unsafe_allow_html=True
        )
    else:
        st.caption(
            "Log in once to job sites in a real browser window — the agent then "
            "reuses that session so it won't be blocked by login walls. "
            "Your passwords are never stored; only the browser session is kept."
        )

    login_url = st.text_input(
        "Optional: a specific site to open (otherwise you get a menu of boards)",
        placeholder="https://himalayas.app/",
    )
    lc1, lc2 = st.columns([1, 1])
    with lc1:
        if st.button("🔐 Open browser & log in"):
            st.info("A browser window is opening. Log in, then close it when done.")
            ok, msg = open_login_browser(user_id, login_url.strip())
            (st.success if ok else st.warning)(msg)
            st.rerun()
    with lc2:
        if has_saved_session(user_id) and st.button("Forget saved logins"):
            clear_session(user_id)
            st.success("Saved logins cleared.")
            st.rerun()

    if has_saved_session(user_id):
        test_url = st.text_input(
            "Test saved login on a site",
            value=login_url.strip() or "https://himalayas.app/",
            key="test_login_url",
        )
        if st.button("🧪 Test saved login"):
            with st.spinner(f"Checking your session on {test_url}..."):
                state, detail = test_saved_login(user_id, test_url)
            if state == "logged_in":
                st.success(f"✅ Still logged in. {detail}")
            elif state == "logged_out":
                st.warning(f"⚠️ Logged out — log in again to refresh. {detail}")
            else:
                st.info(f"❓ Couldn't confirm. {detail}")

    st.divider()
    st.markdown("### Run the agent")

    run_disabled = not GROQ_KEY_SET
    if st.button("🚀 Find matching jobs now", type="primary", disabled=run_disabled):
        if not user.get("cv_structured"):
            st.error("Structure your CV first (step above).")
        elif not user.get("job_prefs"):
            st.error("Save your job preferences first.")
        else:
            from scheduler.run_agent_multiuser import run_for_user, prepare_matched_jobs

            with st.spinner("Searching for matching jobs..."):
                stats = run_for_user(user_id)

            for e in stats.get("errors", []):
                st.warning(e)

            st.info(f"Scraped **{stats['scraped']}** listings — **{stats['matched']}** matched your profile.")

            if stats.get("skipped_region"):
                st.caption(
                    f"Filtered out {stats['skipped_region']} onsite role(s) outside "
                    f"your region (you can adjust 'Work type' / 'Preferred locations')."
                )
            if stats.get("skipped_seniority"):
                st.caption(
                    f"Filtered out {stats['skipped_seniority']} role(s) outside your "
                    f"selected seniority levels."
                )

            if stats.get("max_score") is not None:
                saved_prefs = json.loads(user["job_prefs"]) if user.get("job_prefs") else {}
                threshold = saved_prefs.get("min_match_score", 0.55)
                st.caption(
                    f"Score range: highest {stats['max_score']:.0%} · average {stats['avg_score']:.0%} · "
                    f"your threshold {threshold:.0%}"
                )

            if stats["matched"] > 0:
                spinner_msg = (
                    "Tailoring CVs, writing cover letters and submitting..."
                    if user.get("auto_apply") else
                    "Tailoring CVs and writing cover letters..."
                )
                with st.spinner(spinner_msg):
                    prep = prepare_matched_jobs(user_id)

                if prep.get("auto_apply"):
                    st.success(
                        f"Auto-apply mode: {prep['prepared']} prepared, "
                        f"{prep['auto_submitted']} submitted. See the History tab "
                        f"for outcomes and reasons."
                    )
                else:
                    st.success(f"{prep['prepared']} application(s) ready in the Review queue tab.")
            else:
                st.write("No matches above your threshold. Try lowering the minimum match score.")


with tab_review:
    st.markdown("### Applications ready for review")
    st.caption("Nothing is submitted until you click Confirm.")

    pending = get_jobs_awaiting_review(user_id)

    if not pending:
        st.markdown(
            "<div style='text-align:center;padding:60px;color:#64748b'>"
            "📭 Nothing in the queue yet.<br>Run the agent from the Setup tab to find matches."
            "</div>",
            unsafe_allow_html=True
        )

    for job in pending:
        score = job.get("match_score", 0)
        score_cls = score_color(score)
        score_lbl = score_label(score)
        sponsorship_tag = " · 🛂 Visa sponsorship" if job.get("sponsorship") else ""

        st.markdown(f"""
        <div class="job-card">
            <p class="job-title">{job['title']} <span style="color:#64748b;font-weight:400">at {job['company']}</span></p>
            <p class="job-meta">{job.get('location','') or 'Location unknown'} · {job['platform']}{sponsorship_tag}</p>
        </div>
        """, unsafe_allow_html=True)

        col_score, col_link = st.columns([2, 1])
        with col_score:
            st.markdown(
                f'<span class="score-badge {score_cls}">CV match: {score:.0%} — {score_lbl}</span>',
                unsafe_allow_html=True
            )
        with col_link:
            st.link_button("View job posting →", job["url"])

        if job.get("tailored_cv_path") and Path(job["tailored_cv_path"]).exists():
            st.markdown(
                '<div class="notice notice-ok">✅ <span>Your uploaded CV will be '
                'attached to this application.</span></div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="notice notice-warn">⚠️ <span><b>No CV on file.</b> '
                'Upload your CV in the Setup tab before submitting.</span></div>',
                unsafe_allow_html=True
            )

        with st.expander("Cover letter (click to edit)"):
            edited_letter = st.text_area(
                "Cover letter",
                value=job.get("cover_letter") or "",
                height=220,
                label_visibility="collapsed",
                key=f"letter_{job['job_id']}"
            )

        if job.get("tailored_cv_path") and Path(job["tailored_cv_path"]).exists():
            cv_bytes = Path(job["tailored_cv_path"]).read_bytes()
            st.download_button(
                "⬇️ Download CV being sent",
                data=cv_bytes,
                file_name=Path(job["tailored_cv_path"]).name,
                key=f"dl_{job['job_id']}"
            )

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("✅ Confirm & submit", key=f"confirm_{job['job_id']}", type="primary"):
                from applicator.apply_manager_multiuser import submit_application
                from database.db_manager_multiuser import update_job_status, get_jobs as _get_jobs

                if edited_letter != job.get("cover_letter"):
                    update_job_status(user_id, job["job_id"], "awaiting_review",
                                     cover_letter=edited_letter,
                                     tailored_cv_path=job.get("tailored_cv_path"))

                structured_cv = json.loads(user["cv_structured"]) if user.get("cv_structured") else None

                with st.spinner("Submitting..."):
                    result = submit_application(
                        user_id, job, job.get("tailored_cv_path"),
                        structured_cv=structured_cv
                    )

                if result == "applied":
                    st.success(
                        "Form filled and submit clicked. ⚠️ This is not a guaranteed "
                        "confirmation — many sites need a final step, login, or email "
                        "verification. Any confirmation email comes from the **employer's** "
                        "system, not from HiredAI. Open the posting to verify it went through."
                    )
                elif result == "manual_review":
                    st.warning(
                        "This page wasn't a form HiredAI could submit (often the link is a "
                        "listing page, or the form needs login). Use **View job posting** "
                        "above and apply directly — it's been marked 'manual review' in History."
                    )
                else:
                    refreshed = [j for j in _get_jobs(user_id, limit=500) if j["job_id"] == job["job_id"]]
                    reason = refreshed[0].get("notes") if refreshed else None
                    st.error(f"Submission failed: {reason or 'unknown error'}")
                st.rerun()
        with c2:
            if st.button("✖ Skip", key=f"skip_{job['job_id']}"):
                from applicator.apply_manager_multiuser import skip_application
                skip_application(user_id, job)
                st.rerun()

        st.markdown("<hr style='border-color:#c7d2fe;margin:8px 0 16px'>", unsafe_allow_html=True)

    # ---- Needs manual completion ----
    manual_jobs = get_jobs_needing_manual(user_id)
    if manual_jobs:
        st.divider()
        st.markdown("### 🔧 Needs you to finish manually")
        st.caption(
            "HiredAI prepared these but couldn't auto-submit (the link wasn't a "
            "form it could complete, needed a login, or hit a captcha). Open each "
            "posting and apply directly — your cover letter and tailored CV are "
            "right here to paste/upload."
        )

        for job in manual_jobs:
            with st.container(border=True):
                top, btn = st.columns([3, 1])
                with top:
                    st.markdown(f"**{job['title']}** · {job['company']}")
                    why = job.get("notes") or "Couldn't be automated"
                    st.caption(f"Status: {job['status']} — {why}")
                with btn:
                    st.link_button("Open & apply ↗", job["url"], type="primary")

                if job.get("cover_letter"):
                    with st.expander("Copy your cover letter"):
                        st.code(job["cover_letter"], language=None)

                row_a, row_b = st.columns([1, 1])
                with row_a:
                    if job.get("tailored_cv_path") and Path(job["tailored_cv_path"]).exists():
                        st.download_button(
                            "⬇️ Your CV",
                            data=Path(job["tailored_cv_path"]).read_bytes(),
                            file_name=Path(job["tailored_cv_path"]).name,
                            key=f"mdl_{job['job_id']}"
                        )
                with row_b:
                    if st.button("✓ I applied — mark done", key=f"mark_{job['job_id']}"):
                        from database.db_manager_multiuser import update_job_status
                        update_job_status(user_id, job["job_id"], "applied",
                                         notes="Marked as applied manually by user")
                        st.rerun()


with tab_history:
    all_jobs = get_jobs(user_id, limit=500)

    if not all_jobs:
        st.markdown(
            "<div style='text-align:center;padding:60px;color:#64748b'>"
            "📂 No history yet — run the agent from the Setup tab."
            "</div>",
            unsafe_allow_html=True
        )
    else:
        import pandas as pd
        df = pd.DataFrame(all_jobs)
        counts = df["status"].value_counts()

        cols = st.columns(4)
        metrics = [
            ("Total found", len(df), ""),
            ("Applied", int(counts.get("applied", 0)), "#4ade80"),
            ("Awaiting review", int(counts.get("awaiting_review", 0)), "#fb923c"),
            ("Skipped", int(counts.get("skipped", 0)), "#64748b"),
        ]
        for col, (label, value, color) in zip(cols, metrics):
            color_style = f"color:{color}" if color else ""
            col.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value" style="{color_style}">{value}</div>'
                f'<div class="metric-label">{label}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            '<div class="notice notice-warn">ℹ️ <span><b>About tracking:</b> '
            '"Applied" means HiredAI filled the form and clicked submit. It is '
            '<b>not</b> a delivery guarantee — confirmation emails (if any) come '
            "from the employer's own system, not from HiredAI. Always verify on the "
            "job site for roles that matter.</span></div>",
            unsafe_allow_html=True
        )

        status_filter = st.multiselect(
            "Filter by status",
            sorted(df["status"].unique().tolist()),
            default=[],
            label_visibility="visible"
        )
        filtered = df[df["status"].isin(status_filter)] if status_filter else df

        history_cols = ["title", "company", "status", "match_score", "platform", "notes"]
        if "applied_at" in filtered.columns:
            history_cols.append("applied_at")
        history_cols.append("scraped_at")

        st.dataframe(
            filtered[history_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "notes": st.column_config.TextColumn("Notes / reason", width="medium"),
                "match_score": st.column_config.ProgressColumn("Match score", min_value=0, max_value=1, format="%.0f%%"),
                "applied_at": st.column_config.DatetimeColumn("Submitted at", format="MMM D, HH:mm"),
                "scraped_at": st.column_config.DatetimeColumn("Found at", format="MMM D, HH:mm"),
            }
        )

        st.divider()
        st.markdown("### Edit or withdraw an application")
        editable = df[df["status"].isin(["awaiting_review", "applied"])]
        if not editable.empty:
            choice = st.selectbox(
                "Select a job",
                editable.apply(lambda r: f"{r['title']} @ {r['company']} ({r['status']})", axis=1)
            )
            selected_row = editable.iloc[
                editable.apply(lambda r: f"{r['title']} @ {r['company']} ({r['status']})", axis=1).tolist().index(choice)
            ]
            new_status = st.selectbox(
                "Change status to", ["awaiting_review", "applied", "skipped"],
                index=["awaiting_review", "applied", "skipped"].index(selected_row["status"])
                if selected_row["status"] in ["awaiting_review", "applied", "skipped"] else 0
            )
            if st.button("Update status", type="primary"):
                from database.db_manager_multiuser import update_job_status
                update_job_status(user_id, selected_row["job_id"], new_status,
                                 notes="Manually updated by user")
                st.success("Updated.")
                st.rerun()
        else:
            st.caption("Nothing to edit yet.")
