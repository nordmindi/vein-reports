#!/usr/bin/env python3
"""
Run the TradingAgents service API.

This script starts the FastAPI service that allows external applications
to request trading analysis reports for different tickers and instruments.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import uvicorn


def main():
    """Run the TradingAgents service API."""
    # Set default environment variables if not provided
    # Railway.com sets PORT environment variable
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("SERVICE_PORT", "8000")))
    workers = int(os.getenv("WORKERS", os.getenv("TRADINGAGENTS_SERVICE_WORKERS", "1")))
    reports_dir = Path(
        os.getenv("TRADINGAGENTS_SERVICE_REPORTS_DIR", "reports/api")
    ).resolve()

    print(f"Starting Vein Reports service on {host}:{port}")
    print(f"Workers: {workers}")
    print(f"Reports dir: {reports_dir}")

    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "_jobs").mkdir(parents=True, exist_ok=True)
        probe = reports_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        print(
            f"ERROR: Reports directory is not writable: {reports_dir} ({exc})",
            file=sys.stderr,
        )
        print(
            "Fix: mount a volume and set TRADINGAGENTS_SERVICE_REPORTS_DIR to a path "
            "writable by the container user (recommended: /home/app/reports/api), "
            "or rely on scripts/docker-entrypoint-service.sh to chown the mount.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    # Run the FastAPI application
    uvicorn.run(
        "tradingagents.service.api:app",
        host=host,
        port=port,
        workers=workers,
        reload=False
    )

if __name__ == "__main__":
    main()
