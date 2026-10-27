import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))

for p in [backend_dir, parent_dir]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from app.main import app
