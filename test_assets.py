#!/usr/bin/env python3
"""
Test script to verify that assets are properly included and accessible
in both development and production environments.
"""

import os
import sys
from pathlib import Path


def test_asset_paths():
    """Test that the assets folder and logo can be found in various environments."""
    print("Testing asset paths...")

    # Current working directory (development)
    dev_path = os.path.join(os.getcwd(), "assets", "vein-logo-text.webp")
    print(f"Development path: {dev_path}")
    print(f"Exists in dev: {os.path.exists(dev_path)}")

    # Package directory (production)
    package_path = os.path.join(os.path.dirname(__file__), "assets", "vein-logo-text.webp")
    print(f"Package path: {package_path}")
    print(f"Exists in package: {os.path.exists(package_path)}")

    # Try to find relative to scripts directory
    scripts_path = os.path.join(os.path.dirname(__file__), "scripts", "..", "assets", "vein-logo-text.webp")
    print(f"Scripts relative path: {scripts_path}")
    print(f"Exists relative to scripts: {os.path.exists(scripts_path)}")

    # Using pathlib
    package_root = Path(__file__).parent
    asset_path = package_root / "assets" / "vein-logo-text.webp"
    print(f"Pathlib path: {asset_path}")
    print(f"Exists via pathlib: {asset_path.exists()}")

    # Check if any path works
    possible_paths = [dev_path, package_path, scripts_path, str(asset_path)]
    found = False
    for path in possible_paths:
        if os.path.exists(path):
            print(f"SUCCESS: Found asset at {path}")
            found = True
            break

    if not found:
        print("ERROR: Could not find asset in any expected location")
        return False

    return True

if __name__ == "__main__":
    success = test_asset_paths()
    sys.exit(0 if success else 1)
