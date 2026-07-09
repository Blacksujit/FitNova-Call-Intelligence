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

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="FitNova Call Intelligence", layout="wide")

# ── Session state ──────────────────────────────────────────────────────
if "pending_tasks" not in st.session_state:
    st.session_state.pending_tasks = {}

_HEADERS = {"Cache-Control": "no-cache"} if st.sidebar.checkbox("Bypass cache", value=False, key="raw_cache") else {}


# ── Auth helpers ───────────────────────────────────────────────────────

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
            st.toast(f"⏳ Queued — task {task['task_id']}")
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


def poll_pending_tasks():
    done = []
    for tid, info in st.session_state.pending_tasks.items():
        r = requests.get(f"{API_BASE}/tasks/{tid}", headers=_auth_headers(), timeout=5)
        if r.status_code == 200:
            status = r.json().get("status")
            if status == "done":
                st.toast(f"✅ Call {info['external_call_id']} processed!")
                done.append(tid)
            elif status == "failed":
                st.error(f"❌ Call {info['external_call_id']} failed: {r.json().get('error')}")
                done.append(tid)
    for tid in done:
        del st.session_state.pending_tasks[tid]
    if done:
        st.rerun()


# ── Login screen ───────────────────────────────────────────────────────

if "token" not in st.session_state:
    st.title("FitNova Call Intelligence")
    st.markdown("Please log in to continue.")
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


# ── Sidebar ────────────────────────────────────────────────────────────

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
    st.sidebar.warning(f"⏳ {len(st.session_state.pending_tasks)} queued task(s)")
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
                        st.sidebar.info(f"⏳ {cid}: queued (task {result['task_id']})")
                    else:
                        st.sidebar.success(f"{cid}: {result.get('status')}")

st.sidebar.divider()
if st.sidebar.button("Clear cache"):
    try:
        requests.get(f"{API_BASE}/health", headers=_auth_headers(), timeout=5)
        st.sidebar.success("Cache cleared")
        st.rerun()
    except Exception:
        st.sidebar.error("Could not reach API")


# ── Views ──────────────────────────────────────────────────────────────

org_id = user_info.get("org_id", 1)
team_id = user_info.get("team_id")
advisor_id = user_info.get("advisor_id")

if role == "sales_director":
    st.title("Org-Wide Overview")

    org = api_get(f"/orgs/{org_id}/summary")
    if org:
        avg = org.get("averages", {})
        overall = fmt(avg.get("overall"))
        c1, c2, c3 = st.columns(3)
        c1.metric("Org Average Score", f"{overall}/5")
        if org.get("_cached"):
            st.caption("⚡ served from cache")

        team_names = []
        team_avgs = []
        for t in org.get("teams", []):
            team_names.append(t["name"])
            team_avgs.append(t["averages"].get("overall", 0))

        if team_names:
            st.subheader("Team Averages")
            df = pd.DataFrame({"Team": team_names, "Avg Score": team_avgs})
            st.bar_chart(df.set_index("Team"))

        st.subheader("Active Tags (Org-Wide)")
        tags_data = []
        for t in org.get("teams", []):
            for a in t.get("advisors", []):
                summary = api_get(f"/advisors/{a['id']}/summary")
                if summary:
                    for c in summary.get("calls", []):
                        detail = api_get(f"/calls/{c['id']}")
                        if detail:
                            for tg in detail.get("tags", []):
                                if tg.get("status") == "active":
                                    tags_data.append({
                                        "Call": detail["external_call_id"],
                                        "Tag": tg["category"],
                                        "Severity": tg["severity"],
                                        "Quote": tg.get("quoted_line", "")[:60],
                                    })
        if tags_data:
            st.dataframe(pd.DataFrame(tags_data), use_container_width=True, hide_index=True)


elif role == "team_leader":
    st.title("Team View")

    team = api_get(f"/teams/{team_id}/summary")
    if not team:
        st.stop()

    st.subheader(f"{team['team']} — Advisor Averages")
    adv_names = []
    adv_scores = []
    for a in team.get("advisors", []):
        adv_names.append(a["name"])
        adv_scores.append(a["averages"].get("overall", 0))

    if adv_names:
        df = pd.DataFrame({"Advisor": adv_names, "Avg Score": adv_scores})
        st.bar_chart(df.set_index("Advisor"))

    st.subheader("Calls")
    for a in team.get("advisors", []):
        summary = api_get(f"/advisors/{a['id']}/summary")
        if not summary:
            continue
        for c in summary.get("calls", []):
            detail = api_get(f"/calls/{c['id']}")
            if not detail:
                continue
            tags = detail.get("tags", [])
            label = f"{detail['external_call_id']} ({detail['status']}) — {len(tags)} tags"
            with st.expander(label):
                for tg in tags:
                    sev = "🔴" if tg["severity"] == "high" else ("🟡" if tg["severity"] == "medium" else "🟢")
                    st.error(f"{sev} **{tg['category']}**: {tg['reason']}")
                    st.caption(f"*\"{tg.get('quoted_line', '')[:80]}...\"*")
                    if tg.get("status") == "active":
                        if st.button("Mark Reviewed", key=f"tag_{tg['id']}"):
                            api_post_contest(f"/tags/{tg['id']}/contest", {"advisor_comment": "Reviewed by Team Leader"})
                            st.rerun()


elif role == "advisor":
    st.title("Advisor View")

    summary = api_get(f"/advisors/{advisor_id}/summary")
    if not summary:
        st.stop()

    st.subheader(f"{summary['advisor']} ({summary['team']})")
    avg = summary.get("averages", {}).get("overall")
    st.metric("Average Score", f"{fmt(avg)}/5")

    for c in summary.get("calls", []):
        detail = api_get(f"/calls/{c['id']}")
        if not detail:
            continue
        tags = detail.get("tags", [])
        label = f"{detail['external_call_id']} — {detail['status']} — {len(tags)} flags"
        with st.expander(label):
            for seg in detail.get("segments", []):
                sp = seg["speaker"]
                txt = seg["text"]
                if sp == "advisor":
                    st.markdown(f"**Advisor**: {txt}")
                else:
                    st.markdown(f"*Customer*: {txt}")

            for tg in tags:
                sev = "🔴" if tg["severity"] == "high" else "🟡"
                st.error(f"{sev} **{tg['category']}**: {tg['reason']}")
                st.caption(f"*\"{tg.get('quoted_line', '')[:80]}...\"*")

                if tg.get("status") == "active":
                    with st.form(key=f"contest_{tg.get('id', 0)}"):
                        comment = st.text_input("Why is this flag incorrect?", key=f"inp_{tg.get('id', 0)}")
                        if st.form_submit_button("Contest this flag"):
                            api_post_contest(f"/tags/{tg['id']}/contest", {"advisor_comment": comment})
                            st.success("Flag contested! Team Leader will review.")
                            st.rerun()
                elif tg.get("status") == "contested":
                    st.info("⏳ Contested — awaiting Team Leader review.")
                else:
                    st.success("✅ Resolved.")
