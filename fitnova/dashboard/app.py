"""Streamlit dashboard for FitNova Call Intelligence.

Three role views: Sales Director, Team Leader, Advisor.
Handles queue polling for async process-call tasks.
Includes JWT-based login flow.
"""

import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="FitNova Call Intelligence", layout="wide", initial_sidebar_state="expanded")

# Inject custom CSS
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .stApp {
        margin-top: -3rem;
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
    }

    div[data-testid="stMetric"] {
        background: #1a1a2e;
        border: 1px solid #2a2a4a;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    div[data-testid="stMetric"] > div:first-child {
        color: #94a3b8;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] > div:nth-child(2) {
        color: #e2e8f0;
        font-size: 1.75rem;
        font-weight: 700;
        line-height: 1.2;
    }

    .kpi-card {
        background: #1a1a2e;
        border: 1px solid #2a2a4a;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .kpi-label {
        color: #94a3b8;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.25rem;
    }
    .kpi-value {
        color: #e2e8f0;
        font-size: 1.75rem;
        font-weight: 700;
        line-height: 1.2;
    }

    .severity-high {
        color: #ef4444;
        font-weight: 600;
    }
    .severity-medium {
        color: #f97316;
        font-weight: 600;
    }
    .severity-low {
        color: #f59e0b;
        font-weight: 600;
    }

    .score-badge {
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 700;
    }
    .score-badge-good {
        background: #065f46;
        color: #6ee7b7;
    }
    .score-badge-ok {
        background: #78350f;
        color: #fcd34d;
    }
    .score-badge-bad {
        background: #7f1d1d;
        color: #fca5a5;
    }

    div[data-testid="stExpander"] {
        border: 1px solid #2a2a4a;
        border-radius: 10px;
        background: #16213e;
        margin-bottom: 0.5rem;
    }
    div[data-testid="stExpander"] > div:first-child {
        border-radius: 10px 10px 0 0;
    }

    .chat-bubble-advisor {
        background: #1e3a5f;
        border-radius: 12px 12px 4px 12px;
        padding: 0.5rem 0.75rem;
        margin: 0.25rem 0;
        max-width: 85%;
        margin-left: auto;
        color: #e2e8f0;
        font-size: 0.85rem;
    }
    .chat-bubble-customer {
        background: #2d1b4e;
        border-radius: 12px 12px 12px 4px;
        padding: 0.5rem 0.75rem;
        margin: 0.25rem 0;
        max-width: 85%;
        margin-right: auto;
        color: #e2e8f0;
        font-size: 0.85rem;
    }
    .chat-bubble-unknown {
        background: #1e293b;
        border-radius: 12px;
        padding: 0.5rem 0.75rem;
        margin: 0.25rem auto;
        max-width: 85%;
        text-align: center;
        color: #94a3b8;
        font-size: 0.85rem;
        font-style: italic;
    }
    .chat-label {
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.15rem;
    }
    .chat-label-advisor {
        color: #60a5fa;
        text-align: right;
    }
    .chat-label-customer {
        color: #c084fc;
    }

    .tag-card {
        border-left: 4px solid;
        padding: 0.5rem 0.75rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
        background: #1a1a2e;
    }
    .tag-card-high {
        border-color: #ef4444;
    }
    .tag-card-medium {
        border-color: #f97316;
    }
    .tag-card-low {
        border-color: #f59e0b;
    }

    div.stButton > button {
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.8rem;
    }

    .stSpinner > div {
        border-color: #60a5fa !important;
    }

    section[data-testid="stSidebar"] {
        background: #0f172a;
        border-right: 1px solid #1e293b;
    }

    h1, h2, h3 {
        color: #f1f5f9 !important;
    }

    hr {
        border-color: #2a2a4a;
        margin: 0.5rem 0;
    }

    .call-header {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
</style>
"""

if "pending_tasks" not in st.session_state:
    st.session_state.pending_tasks = {}

_HEADERS = {"Cache-Control": "no-cache"} if st.sidebar.checkbox("Bypass cache", value=False, key="raw_cache") else {}


def _auth_headers() -> dict:
    token = st.session_state.get("token")
    h = dict(_HEADERS)
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def api_get(path: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=10)
        if r.status_code == 401:
            st.session_state.pop("token", None)
            st.session_state.pop("user", None)
            st.rerun()
        r.raise_for_status()
        data = r.json()
        data["_cached"] = r.elapsed.total_seconds() < 0.05
        return data
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(path: str, json_body: dict | None = None) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=json_body or {}, headers=_auth_headers(), timeout=30)
        if r.status_code == 401:
            st.session_state.pop("token", None)
            st.session_state.pop("user", None)
            st.rerun()
        if r.status_code == 202:
            task = r.json()
            st.session_state.pending_tasks[task["task_id"]] = {
                "external_call_id": path.split("=")[-1],
                "started_at": time.time(),
            }
            st.toast(f"Queued - task {task['task_id']}")
            return task
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post_contest(path: str, json_body: dict | None = None) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=json_body or {}, headers=_auth_headers(), timeout=10)
        if r.status_code == 401:
            st.session_state.pop("token", None)
            st.session_state.pop("user", None)
            st.rerun()
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def fmt(val) -> str:
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:.1f}"
    return str(val)


def score_badge_html(score: float | None) -> str:
    if score is None:
        return '<span class="score-badge score-badge-ok">-</span>'
    cls = "score-badge-good" if score >= 4 else ("score-badge-ok" if score >= 2.5 else "score-badge-bad")
    return f'<span class="score-badge {cls}">{score:.1f}</span>'


def poll_pending_tasks():
    done = []
    for tid, info in st.session_state.pending_tasks.items():
        r = requests.get(f"{API_BASE}/tasks/{tid}", headers=_auth_headers(), timeout=5)
        if r.status_code == 200:
            status = r.json().get("status")
            if status == "done":
                st.toast(f"Call {info['external_call_id']} processed!")
                done.append(tid)
            elif status == "failed":
                st.error(f"Call {info['external_call_id']} failed: {r.json().get('error')}")
                done.append(tid)
    for tid in done:
        del st.session_state.pending_tasks[tid]
    if done:
        st.rerun()


def render_plotly_bar(df: pd.DataFrame, x_col: str, y_col: str, title: str, color: str = "#60a5fa"):
    fig = px.bar(
        df, x=x_col, y=y_col, title=title,
        color_discrete_sequence=[color],
        text_auto=".1f",
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#94a3b8", "family": "Inter, sans-serif"},
        title={"font": {"color": "#f1f5f9", "size": 16}},
        xaxis={"showgrid": False, "title": None},
        yaxis={"showgrid": True, "gridcolor": "#1e293b", "title": None, "range": [0, 5.5]},
        height=300, margin={"t": 40, "b": 30, "l": 10, "r": 10},
        hovermode="x",
    )
    fig.update_traces(
        hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:.1f}}/5<extra></extra>",
        marker_line_width=0,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_plotly_dimension_breakdown(df: pd.DataFrame, title: str, height: int = 250):
    fig = px.bar(
        df, x="Dimension", y="Score", title=title,
        color="Score", color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
        text_auto=".1f", range_color=[1, 5],
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#94a3b8", "family": "Inter, sans-serif"},
        title={"font": {"color": "#f1f5f9", "size": 14}},
        xaxis={"showgrid": False, "title": None},
        yaxis={"showgrid": True, "gridcolor": "#1e293b", "title": None, "range": [0, 5.5]},
        height=height, margin={"t": 30, "b": 20, "l": 10, "r": 10},
        coloraxis_showscale=False,
    )
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>Score: %{y:.1f}/5<extra></extra>",
        marker_line_width=0,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def kpi_card(label: str, value: str, help_text: str = ""):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {f'<div style="color:#64748b;font-size:0.7rem;margin-top:0.25rem;">{help_text}</div>' if help_text else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_tag(tg: dict, contest_enabled: bool = False, key_prefix: str = ""):
    sev = tg.get("severity", "low")
    sev_class = f"severity-{sev}"
    icon = {"high": "HIGH", "medium": "MED", "low": "LOW"}.get(sev, "LOW")
    status = tg.get("status", "active")
    st.markdown(
        f"""
        <div class="tag-card tag-card-{sev}">
            <div>
                <span class="{sev_class}">{icon}</span>
                <strong style="color:#e2e8f0;margin-left:0.4rem;">{tg['category']}</strong>
                <span style="color:#64748b;font-size:0.75rem;margin-left:0.5rem;">({status})</span>
            </div>
            <div style="color:#94a3b8;font-size:0.8rem;margin-top:0.25rem;">
                &ldquo;{tg.get('quoted_line', '')[:120]}&rdquo;
            </div>
            <div style="color:#64748b;font-size:0.75rem;margin-top:0.15rem;">
                {tg.get('reason', '')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if contest_enabled:
        if status == "active":
            with st.form(key=f"{key_prefix}contest_{tg.get('id', 0)}"):
                comment = st.text_input("Why is this flag incorrect?", key=f"{key_prefix}inp_{tg.get('id', 0)}")
                if st.form_submit_button("Contest this flag"):
                    api_post_contest(f"/tags/{tg['id']}/contest", {"advisor_comment": comment})
                    st.success("Flag contested! Team Leader will review.")
                    st.rerun()
        elif status == "contested":
            st.info("Contested - awaiting Team Leader review.")
        else:
            st.success("Resolved.")


def render_chat_segment(seg: dict):
    sp = seg.get("speaker", "unknown")
    txt = seg.get("text", "")
    if sp == "advisor":
        st.markdown(
            f'<div class="chat-label chat-label-advisor">Advisor</div>'
            f'<div class="chat-bubble-advisor">{txt}</div>',
            unsafe_allow_html=True,
        )
    elif sp == "customer":
        st.markdown(
            f'<div class="chat-label chat-label-customer">Customer</div>'
            f'<div class="chat-bubble-customer">{txt}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div class="chat-bubble-unknown">{txt}</div>', unsafe_allow_html=True)


def render_call_card(detail: dict, show_contest: bool = False, key_prefix: str = ""):
    cid = detail.get("external_call_id", "?")
    status = detail.get("status", "?")
    processed = detail.get("processed_at", "")
    diar = detail.get("diarization_quality", "")
    scores_list = detail.get("scores", [])
    tags_list = detail.get("tags", [])
    segs = detail.get("segments", [])

    overall = round(sum(s["value"] for s in scores_list) / len(scores_list), 1) if scores_list else None
    badge = score_badge_html(overall)
    tag_summary = f"{len(tags_list)} flag{'s' if len(tags_list) != 1 else ''}" if tags_list else "clean"

    header_html = (
        f'<div class="call-header">'
        f'<span style="font-weight:600;color:#e2e8f0;">{cid}</span>'
        f'{badge}'
        f'<span style="color:#64748b;font-size:0.8rem;">{status}</span>'
        f'<span style="color:#64748b;font-size:0.8rem;">{tag_summary}</span>'
        f'</div>'
    )

    with st.expander(header_html):
        if processed or diar:
            st.caption(f"Processed: {processed}  |  Diarization: {diar}")

        if segs:
            st.markdown('<div style="margin: 0.5rem 0;">', unsafe_allow_html=True)
            for seg in segs:
                render_chat_segment(seg)
            st.markdown("</div>", unsafe_allow_html=True)

        if scores_list:
            st.subheader("Scores")
            df_scores = pd.DataFrame(scores_list)
            df_scores.columns = ["Dimension", "Score", "Justification"]
            if overall is not None:
                st.markdown(
                    f'<div style="margin-bottom:0.5rem;">Overall: {score_badge_html(overall)}</div>',
                    unsafe_allow_html=True,
                )
            st.dataframe(df_scores, width="stretch", hide_index=True)

        if tags_list:
            st.subheader("Flags")
            for tg in tags_list:
                render_tag(tg, contest_enabled=show_contest, key_prefix=key_prefix)
        else:
            st.success("No flags raised on this call.")


def apply_severity_filter(tags_list: list[dict]) -> list[dict]:
    sf = st.session_state.get("sev_filter", "all")
    if sf == "all":
        return tags_list
    return [t for t in tags_list if t.get("severity") == sf]


def render_dimension_breakdown(scores: list[dict], title: str):
    if not scores:
        st.caption("No scores yet")
        return
    df = pd.DataFrame(scores)
    df.columns = ["Dimension", "Score", "Justification"]
    overall = df["Score"].mean()
    st.markdown(
        f'<div style="margin-bottom:0.5rem;">{title}: {score_badge_html(overall)}</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(df, width="stretch", hide_index=True)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=overall,
        domain={"x": [0, 1], "y": [0, 1]},
        number={"font": {"color": "#e2e8f0", "size": 36}},
        gauge={
            "axis": {"range": [0, 5], "tickcolor": "#64748b", "tickfont": {"color": "#94a3b8"}},
            "bar": {"color": "#60a5fa", "thickness": 0.2},
            "bgcolor": "#1e293b",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 2.5], "color": "#2d1b1b"},
                {"range": [2.5, 4], "color": "#2d2b1b"},
                {"range": [4, 5], "color": "#1b2d1b"},
            ],
        },
    ))
    fig.update_layout(
        height=160, margin={"t": 5, "b": 5, "l": 5, "r": 5},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#94a3b8", "family": "Inter, sans-serif"},
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Login screen
if "token" not in st.session_state:
    st.title("FitNova Call Intelligence")
    st.markdown("Automated sales-call quality scoring.")
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    col1.markdown('<div class="kpi-card"><div class="kpi-label">Orgs</div><div class="kpi-value">1</div></div>', unsafe_allow_html=True)
    col2.markdown('<div class="kpi-card"><div class="kpi-label">Advisors</div><div class="kpi-value">6</div></div>', unsafe_allow_html=True)
    col3.markdown('<div class="kpi-card"><div class="kpi-label">Demo Calls</div><div class="kpi-value">4</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    with st.form("login"):
        email = st.text_input("Email", placeholder="director@fitnova.in")
        password = st.text_input("Password", type="password", placeholder="admin123")
        submitted = st.form_submit_button("Log in")
        if submitted:
            try:
                r = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    st.session_state.token = data["access_token"]
                    st.session_state.user = data["user"]
                    st.rerun()
                else:
                    st.error("Invalid email or password")
            except Exception as e:
                st.error(f"Could not reach API: {e}")
    st.stop()


user_info = st.session_state.get("user", {})
role = user_info.get("role", "unknown")
user_name = user_info.get("name", "User")

st.sidebar.title("FitNova IQ")
st.sidebar.markdown(f"**{user_name}** ({role.replace('_', ' ').title()})")

if st.sidebar.button("Log out"):
    st.session_state.pop("token", None)
    st.session_state.pop("user", None)
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Call Processing")

if st.session_state.pending_tasks:
    st.sidebar.warning(f"{len(st.session_state.pending_tasks)} queued task(s)")
    if st.sidebar.button("Poll queue"):
        poll_pending_tasks()

if st.sidebar.button("Process new calls"):
    source = api_get("/incoming/list")
    if source:
        ids = source.get("incoming_ids", [])
        if not ids:
            st.sidebar.info("No unprocessed calls in incoming/")
        else:
            for cid in ids:
                result = api_post(f"/calls/process?external_call_id={cid}")
                if result:
                    if result.get("status") == "queued":
                        st.sidebar.info(f"{cid}: queued (task {result['task_id']})")
                    else:
                        st.sidebar.success(f"{cid}: {result.get('status')}")

st.sidebar.divider()

st.sidebar.subheader("Filters")
st.sidebar.selectbox(
    "Severity",
    options=["all", "high", "medium", "low"],
    index=0,
    key="sev_filter",
)
st.sidebar.selectbox(
    "Date range",
    options=["all", "today", "last_7_days", "last_30_days"],
    index=0,
    key="date_filter",
)

st.sidebar.divider()
if st.sidebar.button("Clear cache"):
    requests.get(f"{API_BASE}/health", headers=_auth_headers(), timeout=5)
    st.sidebar.success("Cache cleared")
    st.rerun()


org_id = user_info.get("org_id", 1)
team_id = user_info.get("team_id")
advisor_id = user_info.get("advisor_id")

# Sales Director View
if role == "sales_director":
    st.title("Org-Wide Overview")

    org = api_get(f"/orgs/{org_id}/summary")
    if org:
        avg = org.get("averages", {})
        overall = avg.get("overall")
        teams_data = org.get("teams", [])
        total_adv = sum(len(t.get("advisors", [])) for t in teams_data)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            kpi_card("Org Score", f"{fmt(overall)}/5")
        with col2:
            kpi_card("Teams", str(len(teams_data)))
        with col3:
            kpi_card("Advisors", str(total_adv))
        with col4:
            active_high = 0
            contested = 0
            for t in teams_data:
                for a in t.get("advisors", []):
                    s = api_get(f"/advisors/{a['id']}/summary")
                    if s:
                        for c in s.get("calls", []):
                            d = api_get(f"/calls/{c['id']}")
                            if d:
                                for tg in d.get("tags", []):
                                    if tg.get("status") == "active" and tg.get("severity") == "high":
                                        active_high += 1
                                    if tg.get("status") == "contested":
                                        contested += 1
            kpi_card("High Flags", str(active_high), help_text=f"{contested} contested")

        if org.get("_cached"):
            st.caption("served from cache")

        if avg.get("overall"):
            dims = {k: v for k, v in avg.items() if k != "overall"}
            if dims:
                df = pd.DataFrame([{"Dimension": k.replace("_", " ").title(), "Score": v} for k, v in dims.items()])
                render_plotly_dimension_breakdown(df, "Dimension Breakdown (Org-Wide)", height=300)

        if teams_data:
            st.subheader("Team Averages")
            team_df = pd.DataFrame([
                {"Team": t["name"], "Avg Score": t["averages"].get("overall", 0)}
                for t in teams_data
            ])
            render_plotly_bar(team_df, "Team", "Avg Score", None)
            st.dataframe(team_df.style.bar(subset=["Avg Score"], color="#4CAF50"), width="stretch", hide_index=True)

        st.subheader("Active Tags (Org-Wide)")
        tag_rows = []
        for t in teams_data:
            for a in t.get("advisors", []):
                s = api_get(f"/advisors/{a['id']}/summary")
                if s:
                    for c in s.get("calls", []):
                        d = api_get(f"/calls/{c['id']}")
                        if d:
                            for tg in d.get("tags", []):
                                tg_filtered = apply_severity_filter([tg])
                                if tg_filtered and tg.get("status") == "active":
                                    tag_rows.append({
                                        "Call": d["external_call_id"],
                                        "Advisor": a["name"],
                                        "Tag": tg["category"],
                                        "Severity": tg["severity"],
                                        "Quote": tg.get("quoted_line", "")[:60],
                                    })
        if tag_rows:
            sev_counts = pd.DataFrame(tag_rows)["Severity"].value_counts().reset_index()
            sev_counts.columns = ["Severity", "Count"]
            color_map = {"high": "#ef4444", "medium": "#f97316", "low": "#f59e0b"}
            fig = px.bar(
                sev_counts, x="Severity", y="Count",
                color="Severity", color_discrete_map=color_map,
                text_auto=True,
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font={"color": "#94a3b8", "family": "Inter, sans-serif"},
                xaxis={"showgrid": False, "title": None},
                yaxis={"showgrid": True, "gridcolor": "#1e293b", "title": None},
                height=200, margin={"t": 10, "b": 20, "l": 10, "r": 10},
            )
            fig.update_traces(hovertemplate="<b>%{x}</b>: %{y}<extra></extra>")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            st.dataframe(pd.DataFrame(tag_rows), width="stretch", hide_index=True)
        else:
            st.success("No active flags.")

# Team Leader View
elif role == "team_leader":
    st.title("Team View")

    team = api_get(f"/teams/{team_id}/summary")
    if not team:
        st.stop()

    avg = team.get("averages", {})

    col1, col2 = st.columns(2)
    with col1:
        kpi_card("Team Score", f"{fmt(avg.get('overall'))}/5")
    with col2:
        kpi_card("Advisors", str(len(team.get("advisors", []))))

    if avg.get("overall"):
        dims = {k: v for k, v in avg.items() if k != "overall"}
        if dims:
            df = pd.DataFrame([{"Dimension": k.replace("_", " ").title(), "Score": v} for k, v in dims.items()])
            render_plotly_dimension_breakdown(df, "Dimension Breakdown", height=250)

    advisors_list = team.get("advisors", [])
    if advisors_list:
        st.subheader("Advisor Averages")
        adv_df = pd.DataFrame([
            {"Advisor": a["name"], "Avg Score": a["averages"].get("overall", 0)}
            for a in advisors_list
        ])
        render_plotly_bar(adv_df, "Advisor", "Avg Score", None)
        st.dataframe(adv_df.style.bar(subset=["Avg Score"], color="#2196F3"), width="stretch", hide_index=True)

    st.subheader("Calls & Tags")
    any_calls = False
    for a in advisors_list:
        s = api_get(f"/advisors/{a['id']}/summary")
        if not s:
            continue
        for c in s.get("calls", []):
            any_calls = True
            detail = api_get(f"/calls/{c['id']}")
            if not detail:
                continue
            tl_tags = apply_severity_filter(detail.get("tags", []))
            detail["tags"] = tl_tags
            render_call_card(detail, show_contest=False, key_prefix=f"tl_{a['id']}_{c['id']}_")
    if not any_calls:
        st.info("No calls yet. Process calls from the sidebar to see them here.")

# Advisor View
elif role == "advisor":
    st.title("Advisor View")

    summary = api_get(f"/advisors/{advisor_id}/summary")
    if not summary:
        st.stop()

    st.subheader(f"{summary['advisor']} - {summary['team']}")
    avg = summary.get("averages", {}).get("overall")
    calls_list = summary.get("calls", [])

    col1, col2 = st.columns(2)
    with col1:
        kpi_card("Avg Score", f"{fmt(avg)}/5")
    with col2:
        kpi_card("Calls Analyzed", str(len(calls_list)))

    if summary.get("averages", {}).get("overall"):
        dims = {k: v for k, v in summary["averages"].items() if k != "overall"}
        if dims:
            df = pd.DataFrame([{"Dimension": k.replace("_", " ").title(), "Score": v} for k, v in dims.items()])
            render_plotly_dimension_breakdown(df, "Performance by Dimension", height=250)

    st.subheader("Your Calls")
    if not calls_list:
        st.info("No calls yet. Process calls from the sidebar to see them here.")
    else:
        for c_data in calls_list:
            detail = api_get(f"/calls/{c_data['id']}")
            if not detail:
                continue
            adv_tags = apply_severity_filter(detail.get("tags", []))
            detail["tags"] = adv_tags
            render_call_card(detail, show_contest=True, key_prefix=f"adv_{c_data['id']}_")
