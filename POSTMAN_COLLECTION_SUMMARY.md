# TradingAgents Service API - Postman Collection Summary

This document summarizes the Postman collection created for testing the TradingAgents service API.

## Overview

The Postman collection provides a comprehensive set of requests for testing all aspects of the TradingAgents service API, including:
- Health checks
- Report job creation with equity ticker or thematic target
- Job status polling
- PDF report download
- JSON artifact downloads (dashboard, validation, evidence)
- Error case testing

## Collection Structure

### Files Created
1. `postman/TradingAgents-Service-API.postman_collection.json` - Main collection file
2. `postman/TradingAgents-Service-API.postman_environment.json` - Environment template
3. `postman/README.md` - Documentation for using the collection
4. `scripts/test_postman_collection.py` - Validation script

### API Endpoints Covered

#### Health Check
- `GET /health` - Service health verification

#### Report Job Creation
- `POST /v1/reports` - Full configuration job creation
- `POST /v1/reports` - Minimal job creation
- `POST /v1/reports` - All analysts job creation
- `POST /v1/reports` - VEIN context bundle job
- `POST /v1/reports` - Sector target (`mining`)
- `POST /v1/reports` - Commodity target (`gold`)
- `POST /v1/reports` - Missing ticker and target error case
- `POST /v1/reports` - Ticker and target together error case
- `POST /v1/reports` - Invalid ticker error case
- `POST /v1/reports` - Invalid date format error case
- `POST /v1/reports` - Future date error case

#### Job Status
- `GET /v1/reports/{job_id}` - Job status polling
- `GET /v1/reports/invalid-job-id` - Invalid job ID error case

#### PDF Download
- `GET /v1/reports/{job_id}/pdf` - PDF report download
- `GET /v1/reports/invalid-job-id/pdf` - Invalid job ID error case

## Features

### Automated Testing
- Test scripts for validation responses
- Automatic job_id capture and storage
- Error case verification

### Environment Management
- Pre-configured environment variables
- Easy variable substitution
- Development environment template

### Comprehensive Coverage
- All main API endpoints
- Error cases and edge conditions
- Multiple configuration options

## Usage

### Importing the Collection
1. Open Postman
2. Click "Import" 
3. Select `postman/TradingAgents-Service-API.postman_collection.json`
4. Import `postman/TradingAgents-Service-API.postman_environment.json`

### Configuration
1. Edit the environment variables:
   - `base_url`: Your service URL
   - `api_key`: Your service API key
   - `job_id`: Auto-populated by requests

### Testing Workflow
1. Run "Health" request to verify service availability
2. Create a report job using one of the creation requests
3. Poll job status until completion
4. Download the PDF report

### Error Testing
The collection includes specific requests for testing error handling:
- Invalid input validation
- Non-existent job IDs
- Date validation
- Required field validation

## Validation

The collection has been validated with the test script `scripts/test_postman_collection.py`, which confirms:
- Correct JSON structure
- Required fields presence
- Complete endpoint coverage
- Proper environment configuration

## Integration

The Postman collection integrates with:
- The TradingAgents service API
- The deployment documentation
- The overall service testing strategy

This provides a complete testing solution for developers and API users to verify the TradingAgents service functionality.