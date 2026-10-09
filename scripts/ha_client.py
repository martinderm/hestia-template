#!/usr/bin/env python3
"""
ha_client.py — Python-first Home Assistant REST Client (stdlib-only).
Supports dry-run by default to ensure safe, reviewable Smart Home mutations.

Usage:
    python scripts/ha_client.py status [--json]
    python scripts/ha_client.py states [--filter-domain light] [--json]
    python scripts/ha_client.py call-service --domain light --service turn_on --entity light.desk [--execute] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


def load_env_token() -> Tuple[str, str]:
    """Reads HASS_URL and HASS_TOKEN from environment or .env file."""
    url = os.environ.get("HASS_URL", "http://homeassistant.local:8123")
    token = os.environ.get("HASS_TOKEN", "")

    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not token and os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("HASS_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("HASS_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass

    return url.rstrip("/"), token


def ha_request(url: str, endpoint: str, token: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    full_url = f"{url}/api/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None

    req = urllib.request.Request(full_url, data=encoded_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8")
            try:
                return {"success": True, "status_code": resp.status, "data": json.loads(content)}
            except Exception:
                return {"success": True, "status_code": resp.status, "text": content}
    except urllib.error.HTTPError as err:
        return {"success": False, "status_code": err.code, "error": err.reason}
    except Exception as err:
        return {"success": False, "status_code": 0, "error": str(err)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Home Assistant REST Client")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Get Home Assistant API status")
    status_parser.add_argument("--json", action="store_true")

    states_parser = subparsers.add_parser("states", help="Get entity states")
    states_parser.add_argument("--filter-domain", type=str, default="")
    states_parser.add_argument("--json", action="store_true")

    call_parser = subparsers.add_parser("call-service", help="Call service (dry-run unless --execute)")
    call_parser.add_argument("--domain", required=True, help="Domain (e.g. light)")
    call_parser.add_argument("--service", required=True, help="Service (e.g. turn_on)")
    call_parser.add_argument("--entity", required=True, help="Entity ID")
    call_parser.add_argument("--execute", action="store_true", help="Execute real mutation on HA Green")
    call_parser.add_argument("--json", action="store_true")

    config_parser = subparsers.add_parser("config", help="Get Home Assistant configuration")
    config_parser.add_argument("--json", action="store_true")

    template_parser = subparsers.add_parser("template", help="Render a Jinja2 template")
    template_parser.add_argument("template", help="Template string to render")
    template_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    base_url, token = load_env_token()

    if args.command == "status":
        if not token:
            res = {"success": False, "error": "No HASS_TOKEN found in environment or .env"}
        else:
            res = ha_request(base_url, "", token)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Status: {res}")
        return 0 if res.get("success") else 1

    elif args.command == "states":
        if not token:
            res = {"success": False, "error": "No HASS_TOKEN found in environment or .env"}
        else:
            res = ha_request(base_url, "states", token)
            if res.get("success") and args.filter_domain and isinstance(res.get("data"), list):
                res["data"] = [e for e in res["data"] if e.get("entity_id", "").startswith(f"{args.filter_domain}.")]
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"States: {len(res.get('data', []))} entities found.")
        return 0 if res.get("success") else 1

    elif args.command == "call-service":
        if not args.execute:
            res = {
                "success": True,
                "mode": "dry-run",
                "message": f"DRY-RUN: Would call {args.domain}.{args.service} on {args.entity}. Pass --execute to actuate.",
                "target": {"domain": args.domain, "service": args.service, "entity_id": args.entity}
            }
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(res["message"])
            return 0

        if not token:
            res = {"success": False, "error": "No HASS_TOKEN found in environment or .env"}
            print(json.dumps(res) if args.json else res["error"])
            return 1

        endpoint = f"services/{args.domain}/{args.service}"
        payload = {"entity_id": args.entity}
        res = ha_request(base_url, endpoint, token, method="POST", data=payload)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Executed: {res}")
        return 0 if res.get("success") else 1

    elif args.command == "config":
        if not token:
            res = {"success": False, "error": "No HASS_TOKEN found in environment or .env"}
        else:
            res = ha_request(base_url, "config", token)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Config: {res.get('data', {}).get('location_name', 'Unknown')} (HA {res.get('data', {}).get('version', 'Unknown')})")
        return 0 if res.get("success") else 1

    elif args.command == "template":
        if not token:
            res = {"success": False, "error": "No HASS_TOKEN found in environment or .env"}
        else:
            res = ha_request(base_url, "template", token, method="POST", data={"template": args.template})
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                print(res.get("text", ""))
            else:
                print(f"Error: {res.get('error')}")
        return 0 if res.get("success") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
