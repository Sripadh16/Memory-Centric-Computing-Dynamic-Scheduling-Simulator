"""
Root launcher for interactive memory-centric architecture dashboard.
Runs FastAPI backend via Uvicorn.
Usage:
    python run_dashboard.py
"""

import sys
import os

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(__file__)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if __name__ == "__main__":
    from dashboard.server import run_server
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(host="127.0.0.1", port=port)
