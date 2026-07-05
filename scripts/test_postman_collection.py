#!/usr/bin/env python3
"""
Test script to verify the Postman collection structure and content.
"""

import json
from pathlib import Path


def validate_postman_collection():
    """Validate the Postman collection structure and content."""

    # Define the expected file paths
    collection_path = Path("postman/TradingAgents-Service-API.postman_collection.json")
    environment_path = Path("postman/TradingAgents-Service-API.postman_environment.json")

    # Check if files exist
    if not collection_path.exists():
        print(f"Error: Collection file not found at {collection_path}")
        return False

    if not environment_path.exists():
        print(f"Error: Environment file not found at {environment_path}")
        return False

    # Load and validate collection
    try:
        with open(collection_path) as f:
            collection = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in collection file: {e}")
        return False

    # Validate collection structure
    required_fields = ['info', 'item', 'variable']
    for field in required_fields:
        if field not in collection:
            print(f"Error: Missing required field '{field}' in collection")
            return False

    # Check info section
    info = collection['info']
    if info.get('name') != 'TradingAgents Service API':
        print("Warning: Collection name doesn't match expected value")

    # Check for required items
    items = collection['item']
    required_items = [
        'Health',
        'Create Report Job',
        'Create Report Job - Minimal',
        'Create Report Job - All Analysts',
        'Create Report Job - Invalid Ticker',
        'Create Report Job - Invalid Date',
        'Create Report Job - Future Date',
        'Get Report Job Status',
        'Get Report Job Status - Invalid Job ID',
        'Download Report PDF',
        'Download Report PDF - Invalid Job ID'
    ]

    item_names = [item['name'] for item in items]
    missing_items = [item for item in required_items if item not in item_names]

    if missing_items:
        print(f"Warning: Missing items in collection: {missing_items}")

    # Load and validate environment
    try:
        with open(environment_path) as f:
            environment = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in environment file: {e}")
        return False

    # Validate environment structure
    if environment.get('name') != 'TradingAgents Service API - Development':
        print("Warning: Environment name doesn't match expected value")

    # Check required variables
    variables = {var['key']: var['value'] for var in environment.get('values', [])}
    required_vars = ['base_url', 'api_key', 'job_id']

    missing_vars = [var for var in required_vars if var not in variables]
    if missing_vars:
        print(f"Error: Missing required variables in environment: {missing_vars}")
        return False

    print("Postman collection validation passed!")
    print(f"  - Collection file: {collection_path}")
    print(f"  - Environment file: {environment_path}")
    print(f"  - Total API endpoints: {len(items)}")
    print(f"  - Variables: {', '.join(required_vars)}")

    return True

def main():
    """Main function to run the validation."""
    print("Validating Postman collection...")
    if validate_postman_collection():
        print("\n✓ All validations passed!")
        print("\nTo use the Postman collection:")
        print("1. Open Postman")
        print("2. Click 'Import' and select the collection JSON file")
        print("3. Import the environment JSON file")
        print("4. Configure the api_key variable with your service API key")
        print("5. Start testing the API endpoints!")
    else:
        print("\n✗ Validation failed!")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
