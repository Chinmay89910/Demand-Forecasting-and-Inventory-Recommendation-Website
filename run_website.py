"""
Run Website Launcher for RestockIQ Demand Forecasting & Inventory Optimization
Launches the unified FastAPI Web Application & REST API Server.
"""
import os
import sys
from pathlib import Path

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add the website directory to sys.path so services and modules resolve
WEBSITE_DIR = Path(__file__).resolve().parent / "website"
if str(WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(WEBSITE_DIR))

# Change current working directory to website dir so relative paths to data/templates/static resolve
os.chdir(WEBSITE_DIR)

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")

    print("=" * 70)
    print(">> RestockIQ Demand Forecasting & Inventory Optimization Website")
    print(f">> Server Address: http://localhost:{port}")
    print(f">> Interactive Web UI: http://localhost:{port}/dashboard")
    print(f">> Swagger OpenAPI Docs: http://localhost:{port}/docs")
    print(f">> Health Check Endpoint: http://localhost:{port}/health")
    print("=" * 70)

    uvicorn.run("main:app", host=host, port=port, reload=reload)
