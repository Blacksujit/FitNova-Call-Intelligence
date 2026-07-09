"""Test the live API with DEMO-SALES."""
import httpx, json

BASE = "http://127.0.0.1:8000"

# Login
r = httpx.post(f"{BASE}/auth/login", json={"email": "director@fitnova.in", "password": "admin123"})
assert r.status_code == 200, f"Login failed: {r.status_code}"
token = r.json()["access_token"]
print(f"Logged in as director")

headers = {"Authorization": f"Bearer {token}"}

# Get DEMO-SALES
r = httpx.get(f"{BASE}/calls/DEMO-SALES", headers=headers)
print(f"GET /calls/DEMO-SALES: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  ID: {d['id']}")
    print(f"  Status: {d['status']}")
    print(f"  Scores ({len(d['scores'])}):")
    for s in d["scores"]:
        print(f"    {s['dimension']}: {s['value']}")
    print(f"  Tags ({len(d['tags'])}):")
    for t in d["tags"]:
        print(f"    [{t['severity']}] {t['category']}: {t['quoted_line'][:60]}")

# List all calls
r = httpx.get(f"{BASE}/calls", headers=headers)
print(f"\nGET /calls: {r.status_code}, {len(r.json())} calls")
