import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mangum import Mangum
from fitnova.api.main import app

handler = Mangum(app, lifespan="off")
