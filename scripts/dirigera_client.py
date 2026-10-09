#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
dirigera_client.py — Python-first IKEA DIRIGERA Hub Client (stdlib-only).
Interacts directly with the IKEA DIRIGERA Hub API (port 8443).

Features:
- OAuth2 PKCE pairing flow (pair with physical action button)
- Read status, home hierarchy, and device inventory
- Structured JSON output (--json)
- Dry-run by default for any state mutations

Usage:
    python scripts/dirigera_client.py pair [--ip <hub-ip>]
    python scripts/dirigera_client.py status [--json]
    python scripts/dirigera_client.py devices [--filter-type light] [--json]
    python scripts/dirigera_client.py dump [--json]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import secrets
import socket
import ssl
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple



def get_ssl_context() -> ssl.SSLContext:
    """DIRIGERA uses a self-signed SSL certificate on port 8443."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def load_config() -> Tuple[str, str]:
    """Reads DIRIGERA_IP and DIRIGERA_TOKEN from environment or .env file."""
    ip = os.environ.get("DIRIGERA_IP", "")
    token = os.environ.get("DIRIGERA_TOKEN", "")

    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DIRIGERA_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val and not token:
                            token = val
                    elif line.startswith("DIRIGERA_IP="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            ip = val
        except Exception:
            pass
    return ip, token



def save_token_to_env(token: str) -> bool:
    """Safely saves DIRIGERA_TOKEN to .env file."""
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_file):
        return False
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("DIRIGERA_TOKEN="):
                new_lines.append(f"DIRIGERA_TOKEN={token}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"DIRIGERA_TOKEN={token}\n")
        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True
    except Exception:
        return False


def dirigera_request(
    ip: str,
    endpoint: str,
    token: Optional[str] = None,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Sends HTTPS request to DIRIGERA hub on port 8443."""
    url = f"https://{ip}:8443/{endpoint.lstrip('/')}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    ctx = get_ssl_context()

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            try:
                parsed = json.loads(content)
                return {"success": True, "status_code": resp.status, "data": parsed}
            except Exception:
                return {"success": True, "status_code": resp.status, "text": content}
    except urllib.error.HTTPError as err:
        try:
            err_body = err.read().decode("utf-8")
            parsed_err = json.loads(err_body)
            return {"success": False, "status_code": err.code, "error": parsed_err}
        except Exception:
            return {"success": False, "status_code": err.code, "error": err.reason}
    except Exception as err:
        return {"success": False, "status_code": 0, "error": str(err)}


def pair_hub(ip: str, client_name: str = "", max_wait_sec: int = 90) -> Dict[str, Any]:
    """
    Executes OAuth2 PKCE pairing flow against IKEA DIRIGERA Hub.
    Requires user to press the Action Button on the physical DIRIGERA hub.
    """
    name = client_name or socket.gethostname()
    alphabet = f"_-~.{string.ascii_letters}{string.digits}"
    code_verifier = "".join(random.choice(alphabet) for _ in range(128))

    sha256_hash = hashlib.sha256()
    sha256_hash.update(code_verifier.encode("utf-8"))
    digest = sha256_hash.digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("us-ascii")

    # Step 1: Request authorization code (GET request with query params)
    params = urllib.parse.urlencode({
        "audience": "homesmart.local",
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    auth_url = f"https://{ip}:8443/v1/oauth/authorize?{params}"
    ctx = get_ssl_context()

    req = urllib.request.Request(auth_url, method="GET")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            code = data.get("code")
    except Exception as err:
        return {
            "success": False,
            "stage": "authorize",
            "error": f"Authorization request failed: {err}",
        }

    if not code:
        return {
            "success": False,
            "stage": "authorize",
            "error": "No code returned by DIRIGERA",
        }

    print(f"\n[DIRIGERA] >>> Auth-Code erhalten! Bitte jetzt die Taste am DIRIGERA Hub drücken! <<<", file=sys.stderr)

    # Step 2: Poll token endpoint until user presses the button
    token_url = f"https://{ip}:8443/v1/oauth/token"
    token_data = urllib.parse.urlencode({
        "code": code,
        "name": name,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }).encode("utf-8")

    token_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    start_time = time.time()
    last_print = 0
    while time.time() - start_time < max_wait_sec:
        time.sleep(2)
        elapsed = int(time.time() - start_time)
        remaining = max_wait_sec - elapsed
        if elapsed - last_print >= 5:
            print(f"[DIRIGERA] Warte auf Tastendruck... (noch {remaining}s verbleibend)", file=sys.stderr)
            last_print = elapsed

        token_req = urllib.request.Request(token_url, data=token_data, headers=token_headers, method="POST")
        try:
            with urllib.request.urlopen(token_req, context=ctx, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                access_token = data.get("access_token")
                if access_token:
                    saved = save_token_to_env(access_token)
                    env_msg = " in .env gespeichert" if saved else " (bitte manuell in .env als DIRIGERA_TOKEN eintragen)"
                    return {
                        "success": True,
                        "access_token": access_token,
                        "ip": ip,
                        "saved_to_env": saved,
                        "message": f"Erfolgreich mit DIRIGERA gekoppelt! Token wurde{env_msg}.",
                    }
        except urllib.error.HTTPError as err:
            # 400, 401, 403 are expected while waiting for physical button press
            if err.code not in (400, 401, 403):
                return {
                    "success": False,
                    "stage": "token_poll",
                    "error": f"HTTP {err.code}: {err.reason}",
                }
        except Exception as err:
            pass

    return {
        "success": False,
        "stage": "timeout",
        "error": f"Zeitüberschreitung ({max_wait_sec}s): Die Taste am DIRIGERA Hub wurde nicht rechtzeitig gedrückt.",
    }



def main() -> int:
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--ip", type=str, default="", help="DIRIGERA IP address (default from .env)")

    parser = argparse.ArgumentParser(description="IKEA DIRIGERA Hub Client (stdlib-only)", parents=[parent_parser])
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Pair command
    pair_parser = subparsers.add_parser("pair", parents=[parent_parser], help="Pair with DIRIGERA hub using action button")
    pair_parser.add_argument("--name", default="smart-home-agent", help="Client name")
    pair_parser.add_argument("--timeout", type=int, default=90, help="Wait timeout in seconds (default: 90)")
    pair_parser.add_argument("--json", action="store_true", help="Output JSON envelope")

    # Status command
    status_parser = subparsers.add_parser("status", parents=[parent_parser], help="Get DIRIGERA status and gateway info")
    status_parser.add_argument("--json", action="store_true", help="Output JSON envelope")

    # Devices command
    devices_parser = subparsers.add_parser("devices", parents=[parent_parser], help="List all connected IKEA devices")
    devices_parser.add_argument("--filter-type", default="", help="Filter by device type (e.g. light, sensor)")
    devices_parser.add_argument("--json", action="store_true", help="Output JSON envelope")

    # Dump command
    dump_parser = subparsers.add_parser("dump", parents=[parent_parser], help="Dump entire DIRIGERA home state")
    dump_parser.add_argument("--json", action="store_true", help="Output JSON envelope")


    args = parser.parse_args()

    default_ip, default_token = load_config()
    hub_ip = args.ip if args.ip else default_ip
    token = default_token

    if args.command == "pair":
        res = pair_hub(hub_ip, client_name=args.name, max_wait_sec=args.timeout)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                print(f"[OK] {res.get('message')}")
                print(f"Token: {res.get('access_token')}")
            else:
                print(f"[ERROR] {res.get('error')}", file=sys.stderr)
        return 0 if res.get("success") else 1

    if not token:
        err = {
            "success": False,
            "error": "Kein DIRIGERA_TOKEN gefunden. Bitte zuerst 'python scripts/dirigera_client.py pair' ausführen oder DIRIGERA_TOKEN in .env eintragen.",
        }
        if getattr(args, "json", False):
            print(json.dumps(err, indent=2))
        else:
            print(f"[ERROR] {err['error']}", file=sys.stderr)
        return 1

    if args.command == "status":
        # /v1/home contains gateway information and overall counts
        res = dirigera_request(hub_ip, "v1/home", token=token)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                home = res.get("data", {})
                print(f"DIRIGERA Hub ({hub_ip}): Erreichbar")
                if isinstance(home, dict):
                    rooms = len(home.get("rooms", []))
                    devices = len(home.get("devices", []))
                    scenes = len(home.get("scenes", []))
                    print(f"Räume: {rooms} | Geräte: {devices} | Szenen: {scenes}")
            else:
                print(f"Fehler: {res.get('error')}", file=sys.stderr)
        return 0 if res.get("success") else 1

    elif args.command == "devices":
        res = dirigera_request(hub_ip, "v1/devices", token=token)
        if res.get("success") and args.filter_type and isinstance(res.get("data"), list):
            res["data"] = [
                d for d in res["data"]
                if d.get("deviceType", "").lower() == args.filter_type.lower()
                or d.get("type", "").lower() == args.filter_type.lower()
            ]
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                devices = res.get("data", [])
                print(f"{len(devices)} Geräte gefunden:")
                for d in devices:
                    dev_id = d.get("id", "unknown")
                    attrs = d.get("attributes", {})
                    name = attrs.get("customName") or attrs.get("model") or "Unbenannt"
                    dev_type = d.get("deviceType") or d.get("type")
                    firmware = attrs.get("firmwareVersion", "N/A")
                    battery = attrs.get("batteryPercentage")
                    batt_str = f" | Batterie: {battery}%" if battery is not None else ""
                    print(f"- [{dev_type}] {name} (FW: {firmware}{batt_str}) [ID: {dev_id}]")
            else:
                print(f"Fehler: {res.get('error')}", file=sys.stderr)
        return 0 if res.get("success") else 1

    elif args.command == "dump":
        res = dirigera_request(hub_ip, "v1/home", token=token)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(json.dumps(res.get("data", res), indent=2))
        return 0 if res.get("success") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
