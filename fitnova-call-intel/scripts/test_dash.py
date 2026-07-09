"""Start Streamlit dashboard and verify it loads."""
import subprocess, time, httpx, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PATH"] += os.pathsep + os.environ.get("TEMP", "")

proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "fitnova/dashboard/app.py",
     "--server.port", "8503", "--server.headless", "true"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(10)

try:
    r = httpx.get("http://localhost:8503", timeout=5)
    print(f"Dashboard status: {r.status_code}")
    print(f"Page size: {len(r.text)} bytes")
    import re
    titles = re.findall(r'<title>(.*?)</title>', r.text)
    print(f"  Title: {titles}")
    for kw in ["FitNova", "streamlit", "dashboard"]:
        print(f'  contains "{kw}": {kw.lower() in r.text.lower()}')
finally:
    proc.terminate()
    proc.wait()
print("Done.")
