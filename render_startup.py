"""Minimal Render startup - adds subdirectory to path, starts uvicorn, auto-seeds DB."""
import os
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent / "fitnova-call-intel"
sys.path.insert(0, str(BASE))
os.chdir(str(BASE))


def _background_seed():
    import time
    time.sleep(5)
    try:
        import urllib.request as _u
        _u.urlopen(_u.Request("http://127.0.0.1:8000/startup/seed", data=b"{}", method="POST"), timeout=120)
    except Exception:
        pass


threading.Thread(target=_background_seed, daemon=True).start()

import uvicorn
port = int(os.getenv("PORT", "8000"))
uvicorn.run("fitnova.api.main:app", host="0.0.0.0", port=port, log_level="info")
