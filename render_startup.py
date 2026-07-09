"""Minimal Render startup - adds subdirectory to path and starts uvicorn."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent / "fitnova-call-intel"
sys.path.insert(0, str(BASE))
os.chdir(str(BASE))

import uvicorn
port = int(os.getenv("PORT", "8000"))
uvicorn.run("fitnova.api.main:app", host="0.0.0.0", port=port, log_level="info")
