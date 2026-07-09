"""Test API endpoints work."""
import os, sys, subprocess, time, httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PATH"] += os.pathsep + os.environ.get("TEMP", "")

# Start server
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "fitnova.api.main:app", "--host", "0.0.0.0", "--port", "8889", "--log-level", "error"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(3)

BASE = "http://localhost:8889"
passed = 0
failed = 0

def check(label, status, expected=200):
    global passed, failed
    ok = status == expected
    print(f"  {'PASS' if ok else 'FAIL'} {label}: got {status}, expected {expected}")
    if ok: passed += 1
    else: failed += 1

try:
    # 1. Health
    r = httpx.get(f"{BASE}/health", timeout=5)
    check("GET /health", r.status_code, 200)
    if r.status_code == 200:
        print(f"    body: {r.json()}")

    # 2. Login
    r = httpx.post(f"{BASE}/auth/login", json={"email": "priya@fitnova.in", "password": "advisor123"}, timeout=5)
    check("POST /auth/login", r.status_code, 200)
    token = r.json().get("access_token", "") if r.status_code == 200 else ""

    if token:
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Org summary (FitNova has org_id=1)
        r = httpx.get(f"{BASE}/orgs/1/summary", headers=headers, timeout=5)
        check("GET /orgs/1/summary", r.status_code, 200)
        if r.status_code == 200:
            data = r.json()
            print(f"    org={data.get('org')}, teams={len(data.get('teams',[]))}")
            print(f"    avg_scores={data.get('avg_scores')}")

        # 4. Call detail by internal ID (MAIN-001 = id 14)
        r = httpx.get(f"{BASE}/calls/14", headers=headers, timeout=5)
        check("GET /calls/14", r.status_code, 200)
        if r.status_code == 200:
            data = r.json()
            print(f"    external_call_id={data.get('external_call_id')}")
            print(f"    segments={len(data.get('segments',[]))}, scores={len(data.get('scores',[]))}, tags={len(data.get('tags',[]))}")
            if data.get('segments'):
                print(f"    first seg: [{data['segments'][0]['start_ms']}ms] {data['segments'][0]['text'][:60]}")

        # 5. Team summary (Alpha Pod has team_id=1)
        r = httpx.get(f"{BASE}/teams/1/summary", headers=headers, timeout=5)
        check("GET /teams/1/summary", r.status_code, 200)
        if r.status_code == 200:
            data = r.json()
            print(f"    team={data.get('team')}, advisors={len(data.get('advisors',[]))}")

    # 6. 401 without auth
    r = httpx.get(f"{BASE}/calls/MAIN-001", timeout=5)
    check("GET /calls/MAIN-001 (no auth)", r.status_code, 401)

finally:
    proc.terminate()
    proc.wait()

print(f"\nResults: {passed} passed, {failed} failed out of {passed+failed}")
