#!/usr/bin/env python3
"""
Example client for the TradingAgents service API.

This script demonstrates how to interact with the TradingAgents service
from another application.
"""

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

    def submit_report(self, ticker, analysis_date=None, analysts=None, **kwargs):
        """
        Submit a report generation job.

        Args:
            ticker (str): Stock ticker symbol
            analysis_date (str, optional): Analysis date (YYYY-MM-DD)
            analysts (list, optional): List of analysts to use
            **kwargs: Additional configuration options

        Returns:
            dict: Job submission response
        """
        payload = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "selected_analysts": analysts or ["market", "social", "news", "fundamentals"],
            **kwargs
        }

        response = requests.post(
            f"{self.base_url}/v1/reports",
            json=payload,
            headers=self.headers
        )

        if response.status_code == 202:
            return response.json()
        else:
            response.raise_for_status()

    def get_report_json(self, job_id):
        """Download the full final-state JSON for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/json",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_report_dashboard(self, job_id):
        """Download dashboard.json for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/dashboard",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_validation_report(self, job_id):
        """Download validation_report.json for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/validation",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_decision_evidence(self, job_id):
        """Download decision_evidence_bundle.json for a completed report."""
        response = requests.get(
            f"{self.base_url}/v1/reports/{job_id}/evidence",
            headers=self.headers
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
            headers=self.headers
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
            headers=self.headers
        )

        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            return True
        elif response.status_code == 409:
            # Job not completed yet
            return False
        else:
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
            elif status['status'] == 'failed':
                raise Exception(f"Job failed: {status.get('error', 'Unknown error')}")
            else:
                print(f"Job status: {status['status']}")
                time.sleep(poll_interval)

        raise Exception("Job timeout exceeded")


def main():
    """Example usage of the TradingAgents client."""
    # Configuration
    base_url = os.getenv("TRADINGAGENTS_SERVICE_URL", "http://localhost:8000")
    api_key = os.getenv("TRADINGAGENTS_SERVICE_API_KEY", "change-me-in-production")

    # Create client
    client = TradingAgentsClient(base_url, api_key)

    # Submit a report job
    print("Submitting report job...")
    job = client.submit_report(
        ticker="NVDA",
        analysis_date="2026-05-07",
        analysts=["market", "social", "news", "fundamentals"],
        report_tier="pro",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1
    )
    print(f"Job submitted: {job['job_id']}")

    # Wait for completion
    print("Waiting for job completion...")
    try:
        client.wait_for_completion(job['job_id'])
        print("Job completed successfully!")

        # Download the PDF
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
