import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fitnova.api.main import app
for route in app.routes:
    if hasattr(route, "methods") and hasattr(route, "path"):
        print(f'{sorted(route.methods)} {route.path}')
