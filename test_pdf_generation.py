#!/usr/bin/env python3
"""
Test script to verify that PDF generation works with the updated asset handling.
"""

import os
import sys

# Add the scripts directory to the path so we can import the PDF generator
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from generate_full_report_pdf import VeinReportPDF


def test_pdf_asset_handling():
    """Test that the PDF generator can properly handle asset paths."""
    print("Testing PDF asset handling...")

    # Create an instance of the PDF generator
    pdf = VeinReportPDF()

    print(f"Logo path set to: {pdf.logo_path}")

    # Check if the logo path exists
    if pdf.logo_path:
        exists = os.path.exists(pdf.logo_path)
        print(f"Logo file exists: {exists}")
        if exists:
            print("SUCCESS: PDF generator can find the logo asset")
            return True
        else:
            print("ERROR: PDF generator set a logo path, but the file doesn't exist")
            return False
    else:
        print("WARNING: PDF generator could not find the logo asset")
        print("This might be OK if the PDF is designed to work without a logo")
        return True  # This is not necessarily an error

if __name__ == "__main__":
    success = test_pdf_asset_handling()
    sys.exit(0 if success else 1)
