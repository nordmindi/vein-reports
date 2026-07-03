# TradingAgents Service API - Postman Collection

This directory contains a Postman collection for testing the TradingAgents service API.

## Overview

The Postman collection includes requests for all API endpoints:
- Health check
- Report job creation (with various configurations)
- Job status polling
- PDF report download
- Full-state JSON download
- Dashboard, validation, and evidence artifact downloads
- VEIN `context_bundle` report creation

## Setup Instructions

1. **Import the Collection**
   - Open Postman
   - Click "Import" in the top left
   - Select the `TradingAgents-Service-API.postman_collection.json` file

2. **Configure Environment Variables**
   - Click on the collection name "TradingAgents Service API"
   - Go to the "Variables" tab
   - Set the following variables:
     - `base_url`: Your service URL (e.g., http://localhost:8000 or your cloud deployment URL)
     - `api_key`: Your service API key
     - `job_id`: This will be automatically populated when you create a job

3. **Run the Requests**
   - Start with the "Health" request to verify the service is running
   - Use "Create Report Job" to submit a new analysis request
   - Use "Get Report Job Status" to check the progress
   - Once completed, use "Download Report PDF" to get the report

## Collection Structure

### Health
- `GET /health` - Check if the service is running

### Report Job Creation
- `POST /v1/reports` - Create a full report job with all options
- `POST /v1/reports` - Create a minimal report job
- `POST /v1/reports` - Create a report job with all analyst types
- `POST /v1/reports` - Create a report job with VEIN supply-chain context
- `POST /v1/reports` - Error case: Invalid ticker
- `POST /v1/reports` - Error case: Invalid date format
- `POST /v1/reports` - Error case: Future date

### Job Status
- `GET /v1/reports/{job_id}` - Get job status
- `GET /v1/reports/invalid-job-id` - Error case: Invalid job ID

### PDF Download
- `GET /v1/reports/{job_id}/pdf` - Download completed report PDF
- `GET /v1/reports/invalid-job-id/pdf` - Error case: Invalid job ID for PDF download

### JSON Artifacts
- `GET /v1/reports/{job_id}/json` - Download full final-state JSON
- `GET /v1/reports/{job_id}/dashboard` - Download the canonical public recommendation/action artifact
- `GET /v1/reports/{job_id}/validation` - Download validation status and blocking issues
- `GET /v1/reports/{job_id}/evidence` - Download the decision evidence bundle

## Testing Workflow

1. **Verify Service Health**
   - Run the "Health" request to ensure the service is running

2. **Create a Report Job**
   - Run one of the "Create Report Job" requests
   - The job ID will be automatically stored in the collection variables

3. **Monitor Job Progress**
   - Run "Get Report Job Status" repeatedly until the status is "completed" or "failed"

4. **Download the Report**
   - Once the job is completed, run "Download Report PDF" to get the report
   - Run the JSON artifact requests when testing downstream dashboard integration

## Error Testing

The collection includes requests that test various error conditions:
- Invalid ticker symbols
- Invalid date formats
- Future dates (not allowed)
- Invalid job IDs

These requests help verify that the service properly validates input and handles errors gracefully.

## Example Usage

### Successful Workflow
1. Run "Create Report Job" 
2. Note the job_id returned in the response
3. Run "Get Report Job Status" with that job_id
4. Repeat step 3 until status is "completed"
5. Run "Download Report PDF" to get the report
6. Run "Download Dashboard JSON" to verify the public recommendation/action state

### Testing Error Cases
1. Run "Create Report Job - Invalid Ticker"
2. Verify you get a 422 (Unprocessable Entity) response
3. Try other error cases to ensure proper validation

## Tips

- Always set your `api_key` variable before running requests
- Use the "Save Responses" feature in Postman to compare responses over time
- The collection variables automatically store the job_id from successful job creation requests
- For production testing, update the `base_url` to your production endpoint
