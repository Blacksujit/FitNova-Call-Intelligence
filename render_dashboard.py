"""Render web service entry point for the Streamlit dashboard."""

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent / "fitnova-call-intel"
os.chdir(BASE)
sys.path.insert(0, str(BASE))

port = int(os.getenv("PORT", "8501"))
os.execvp("streamlit", [
    "streamlit", "run", str(BASE / "fitnova" / "dashboard" / "app.py"),
    "--server.port", str(port),
    "--server.headless", "true",
    "--server.address", "0.0.0.0",
])
