#!/usr/bin/env python3
"""Script for local HACS validation."""

import json
import os
import sys


def validate_hacs():
    """Execute simple HACS compliance check."""
    errors = []

    # 1. Check for hacs.json
    if not os.path.exists("hacs.json"):
        errors.append("Missing hacs.json in root directory.")
    else:
        try:
            with open("hacs.json", encoding="utf-8") as f:
                hacs = json.load(f)
                if "name" not in hacs:
                    errors.append("hacs.json: 'name' is missing.")
        except Exception as e:
            errors.append(f"hacs.json: Invalid JSON: {e}")

    # 2. Check for manifest.json
    manifest_path = "custom_components/tado_hijack/manifest.json"
    if not os.path.exists(manifest_path):
        errors.append(f"Missing {manifest_path}")
    else:
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
                required = ["domain", "name", "documentation", "version", "codeowners"]
                errors.extend(
                    f"manifest.json: '{key}' is missing."
                    for key in required
                    if key not in manifest
                )
        except Exception as e:
            errors.append(f"manifest.json: Invalid JSON: {e}")

    if errors:
        for err in errors:
            sys.stderr.write(f"HACS VALIDATION ERROR: {err}\n")
        return False

    return True


if __name__ == "__main__" and not validate_hacs():
    sys.exit(1)
