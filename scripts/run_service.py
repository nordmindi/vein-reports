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

    print(f"Starting TradingAgents service on {host}:{port}")
    print(f"Workers: {workers}")

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
