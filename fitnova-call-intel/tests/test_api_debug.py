"""Debug API calls."""
import httpx, json

BASE = "http://127.0.0.1:8000"

r = httpx.post(f"{BASE}/auth/login", json={"email": "director@fitnova.in", "password": "admin123"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Try the call by internal ID
r = httpx.get(f"{BASE}/calls/18", headers=headers)
print(f"GET /calls/18: {r.status_code}")
if r.status_code == 422:
    print(r.text[:500])

# Try DEMO-SALES by external ID
r = httpx.get(f"{BASE}/calls/DEMO-SALES", headers=headers)
print(f"GET /calls/DEMO-SALES: {r.status_code}")
if r.status_code == 422:
    print(r.text[:500])

# List calls
r = httpx.get(f"{BASE}/calls", headers=headers)
print(f"GET /calls: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if isinstance(data, list):
        print(f"  List of {len(data)} calls")
        for c in data[:3]:
            print(f"    {c}")
    else:
        print(json.dumps(data, indent=2)[:500])
else:
    print(r.text[:500])
