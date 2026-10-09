#!/usr/bin/env python3
"""
lint_ha_yaml.py — Validates Home Assistant YAML definitions (automations, scripts, scenes).
Stdlib-only with basic syntax and structure checks.

Usage:
    python scripts/lint_ha_yaml.py --file path/to/automation.yaml [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List


def lint_yaml_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "file": file_path, "errors": ["File does not exist."]}

    errors: List[str] = []
    warnings: List[str] = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as err:
        return {"success": False, "file": file_path, "errors": [f"Cannot read file: {err}"]}

    # Basic structural check
    has_trigger = False
    has_action = False

    for idx, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip()
        # Tab check
        if "\t" in line:
            errors.append(f"Line {idx}: Tabs found. Home Assistant YAML must use spaces only.")

        stripped = line.strip()
        if stripped.startswith("trigger:"):
            has_trigger = True
        elif stripped.startswith("action:") or stripped.startswith("actions:"):
            has_action = True

    # If it's suspected to be an automation
    if "automation" in os.path.basename(file_path).lower():
        if not has_trigger:
            warnings.append("No 'trigger:' block detected in automation file.")
        if not has_action:
            warnings.append("No 'action:' or 'actions:' block detected in automation file.")

    return {
        "success": len(errors) == 0,
        "file": file_path,
        "line_count": len(lines),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Home Assistant YAML Linter")
    parser.add_argument("--file", required=True, help="Path to YAML file")
    parser.add_argument("--json", action="store_true", help="Output JSON envelope")
    args = parser.parse_args()

    result = lint_yaml_file(args.file)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["success"]:
            print(f"PASS: {args.file} ({result['line_count']} lines)")
            for w in result["warnings"]:
                print(f"  WARNING: {w}")
        else:
            print(f"FAIL: {args.file}")
            for e in result["errors"]:
                print(f"  ERROR: {e}")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
