#!/usr/bin/env python3
"""
Example client for the TradingAgents service API.

This script demonstrates how to interact with the TradingAgents service
from another application.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TradingAgentsClient:
    """Client for the TradingAgents service API."""

    def __init__(self, base_url, api_key):
        """
        Initialize the client.

        Args:
            base_url (str): Base URL of the TradingAgents service
            api_key (str): API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}

    def submit_report(
        self,
        ticker=None,
        *,
        target=None,
        analysis_date=None,
        analysts=None,
        **kwargs,
    ):
        """
        Submit a report generation job.

        Args:
            ticker (str, optional): Equity ticker symbol
            target (dict, optional): Thematic target ``{type, value}`` for sector/commodity reports
            analysis_date (str, optional): Analysis date (YYYY-MM-DD)
            analysts (list, optional): List of analysts to use
            **kwargs: Additional configuration options

        Returns:
            dict: Job submission response
        """
        payload = {
            "analysis_date": analysis_date,
            "selected_analysts": analysts or ["market", "social", "news", "fundamentals"],
            **kwargs,
        }
        if target is not None:
            payload["target"] = target
        elif ticker is not None:
            payload["ticker"] = ticker
        else:
            raise ValueError("provide either ticker or target")

        response = requests.post(
            f"{self.base_url}/v1/reports",
            json=payload,
            headers=self.headers,
        )

        if response.status_code == 202:
            return response.json()
        response.raise_for_status()

    def get_report_json(self, job_id):
        """Download the full final-state JSON for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/json",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def get_report_dashboard(self, job_id):
        """Download dashboard.json for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/dashboard",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def get_validation_report(self, job_id):
        """Download validation_report.json for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/validation",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def get_decision_evidence(self, job_id):
        """Download decision_evidence_bundle.json for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/evidence",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def get_report_status(self, job_id):
        """
        Get the status of a report job.

        Args:
            job_id (str): Job ID

        Returns:
            dict: Job status response
        """
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def download_pdf(self, job_id, filename):
        """
        Download the PDF report for a completed job.

        Args:
            job_id (str): Job ID
            filename (str): Output filename

        Returns:
            bool: True if successful
        """
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/pdf",
            headers=self.headers,
        )

        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            return True
        if response.status_code == 409:
            return False
        response.raise_for_status()

    def wait_for_completion(self, job_id, timeout=300, poll_interval=10):
        """
        Wait for a job to complete.

        Args:
            job_id (str): Job ID
            timeout (int): Timeout in seconds
            poll_interval (int): Poll interval in seconds

        Returns:
            dict: Final job status
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_report_status(job_id)

            if status['status'] == 'completed':
                return status
            if status['status'] == 'failed':
                raise Exception(f"Job failed: {status.get('error', 'Unknown error')}")
            print(f"Job status: {status['status']}")
            time.sleep(poll_interval)

        raise Exception("Job timeout exceeded")


def _parse_target(value: str) -> dict:
    """Parse ``sector:mining`` or ``commodity:gold`` into API target payload."""
    if ":" not in value:
        raise ValueError("target must be type:value, e.g. sector:mining")
    target_type, target_value = value.split(":", 1)
    return {"type": target_type.strip().lower(), "value": target_value.strip().lower()}


def main():
    """Example usage of the TradingAgents client."""
    parser = argparse.ArgumentParser(description="TradingAgents service client example")
    parser.add_argument("--ticker", help="Equity ticker, e.g. NVDA")
    parser.add_argument(
        "--target",
        help="Thematic target as type:value, e.g. sector:mining or commodity:gold",
    )
    parser.add_argument("--analysis-date", default="2026-07-31")
    parser.add_argument(
        "--analysts",
        default="market,social,news",
        help="Comma-separated analysts",
    )
    args = parser.parse_args()

    if not args.ticker and not args.target:
        parser.error("provide --ticker or --target")
    if args.ticker and args.target:
        parser.error("provide either --ticker or --target, not both")

    base_url = os.getenv("TRADINGAGENTS_SERVICE_URL", "http://localhost:8000")
    api_key = os.getenv("TRADINGAGENTS_SERVICE_API_KEY", "change-me-in-production")

    client = TradingAgentsClient(base_url, api_key)
    analysts = [item.strip() for item in args.analysts.split(",") if item.strip()]

    print("Submitting report job...")
    submit_kwargs = {
        "analysis_date": args.analysis_date,
        "analysts": analysts,
        "report_tier": "pro",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    }
    if args.target:
        submit_kwargs["target"] = _parse_target(args.target)
    else:
        submit_kwargs["ticker"] = args.ticker

    job = client.submit_report(**submit_kwargs)
    print(f"Job submitted: {job['job_id']}")

    print("Waiting for job completion...")
    try:
        status = client.wait_for_completion(job['job_id'])
        print(f"Job completed: subject={status.get('ticker')}")

        pdf_filename = f"report_{job['job_id']}.pdf"
        if client.download_pdf(job['job_id'], pdf_filename):
            print(f"PDF downloaded to: {pdf_filename}")
        else:
            print("Failed to download PDF")

        dashboard = client.get_report_dashboard(job["job_id"])
        print(f"Published recommendation: {dashboard.get('recommendation')}")
        print(f"Published action: {dashboard.get('action')}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
