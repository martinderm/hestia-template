#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
deploy_dashboard.py — Deploys a custom Lovelace dashboard to Home Assistant via WebSocket API.
Pure Python (stdlib-only, zero dependencies).

Usage:
    python scripts/deploy_dashboard.py [--url-path smart-home] [--title "Smart Home"] [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ha_client import load_env_token


class HAWebSocketClient:
    """Minimal stdlib RFC-6455 WebSocket client for Home Assistant."""

    def __init__(self, base_url: str, token: str, timeout: float = 10.0):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._msg_id = 1

    def connect(self) -> None:
        parsed = urllib.parse.urlparse(self.base_url)
        is_ssl = parsed.scheme in ("https", "wss")
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if is_ssl else 8123)

        raw_sock = socket.create_connection((host, port), timeout=self.timeout)
        if is_ssl:
            context = ssl.create_default_context()
            self.sock = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            self.sock = raw_sock

        self.sock.settimeout(self.timeout)

        # 1. HTTP Upgrade Handshake
        sec_key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = "/api/websocket"
        headers = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {sec_key}",
            "Sec-WebSocket-Version: 13",
            "",
            "",
        ]
        request_data = "\r\n".join(headers).encode("ascii")
        self.sock.sendall(request_data)

        # Read handshake response
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connection closed during WebSocket handshake")
            response += chunk

        status_line = response.split(b"\r\n")[0].decode("ascii", errors="replace")
        if "101" not in status_line:
            raise ConnectionError(f"WebSocket handshake failed: {status_line}")

        # 2. Authenticate
        auth_req = self._recv_json()
        if auth_req.get("type") != "auth_required":
            raise ConnectionError(f"Expected auth_required, got: {auth_req}")

        self._send_json({"type": "auth", "access_token": self.token})
        auth_res = self._recv_json()
        if auth_res.get("type") != "auth_ok":
            raise ConnectionError(f"Authentication failed: {auth_res}")

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def call(self, msg_type: str, **kwargs: Any) -> Dict[str, Any]:
        """Send command and wait for response with matching id."""
        cur_id = self._msg_id
        self._msg_id += 1

        payload = {"id": cur_id, "type": msg_type, **kwargs}
        self._send_json(payload)

        while True:
            res = self._recv_json()
            if res.get("id") == cur_id:
                return res

    def _send_json(self, data: Dict[str, Any]) -> None:
        raw_text = json.dumps(data, ensure_ascii=False).encode("utf-8")
        frame = bytearray()
        # FIN (0x80) + Text opcode (0x01)
        frame.append(0x81)

        length = len(raw_text)
        # Client frames MUST be masked (0x80)
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(0x80 | 127)
            frame.extend(length.to_bytes(8, "big"))

        mask_key = os.urandom(4)
        frame.extend(mask_key)

        masked_payload = bytearray(length)
        for i in range(length):
            masked_payload[i] = raw_text[i] ^ mask_key[i % 4]
        frame.extend(masked_payload)

        self.sock.sendall(frame)

    def _recv_exact(self, num_bytes: int) -> bytes:
        data = bytearray()
        while len(data) < num_bytes:
            chunk = self.sock.recv(num_bytes - len(data))
            if not chunk:
                raise ConnectionError("Socket closed prematurely")
            data.extend(chunk)
        return bytes(data)

    def _recv_json(self) -> Dict[str, Any]:
        # Read frame header
        header = self._recv_exact(2)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F

        if length == 126:
            length = int.from_bytes(self._recv_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(self._recv_exact(8), "big")

        mask_key = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length)

        if mask_key:
            unmasked = bytearray(length)
            for i in range(length):
                unmasked[i] = payload[i] ^ mask_key[i % 4]
            payload = bytes(unmasked)

        # Ping frame -> reply with pong
        if opcode == 0x09:
            pong_frame = bytearray([0x8A, 0x00])
            self.sock.sendall(pong_frame)
            return self._recv_json()

        text = payload.decode("utf-8")
        return json.loads(text)


def parse_yaml_file(filepath: Path) -> Dict[str, Any]:
    """Parse YAML file into dict. Uses PyYAML if available."""
    try:
        import yaml
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to parse YAML '{filepath}': {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Lovelace dashboard to Home Assistant")
    parser.add_argument("--url-path", default="smart-home", help="Dashboard URL slug (e.g. smart-home)")
    parser.add_argument("--title", default="Smart Home", help="Dashboard title")
    parser.add_argument("--icon", default="mdi:home-automation", help="Sidebar icon")
    parser.add_argument("--source", default="dashboards/lovelace_complete.yaml", help="Source YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without modifying HA")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON envelope")
    args = parser.parse_args()

    url, token = load_env_token()
    if not token:
        err = "No HASS_TOKEN found in environment or .env"
        if args.json_output:
            print(json.dumps({"success": False, "error": err}))
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    source_path = Path(__file__).resolve().parent.parent / args.source
    if not source_path.exists():
        err = f"Source YAML file '{source_path}' does not exist."
        if args.json_output:
            print(json.dumps({"success": False, "error": err}))
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        config_obj = parse_yaml_file(source_path)
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"success": False, "error": str(exc)}))
        else:
            print(f"Error parsing source YAML: {exc}", file=sys.stderr)
        return 1

    ws = HAWebSocketClient(url, token)
    try:
        ws.connect()

        # 1. List existing custom dashboards
        list_res = ws.call("lovelace/dashboards/list")
        if not list_res.get("success"):
            raise RuntimeError(f"Failed to list dashboards: {list_res.get('error')}")

        existing_dashboards = list_res.get("result", [])
        dashboard_exists = any(d.get("url_path") == args.url_path for d in existing_dashboards)

        result_data = {
            "action": "deploy_dashboard",
            "url_path": args.url_path,
            "title": args.title,
            "existing_dashboards": [d.get("url_path") for d in existing_dashboards],
            "already_existed": dashboard_exists,
            "dry_run": args.dry_run,
        }

        if args.dry_run:
            result_data["success"] = True
            result_data["message"] = f"DRY-RUN: Would create/update dashboard '{args.url_path}' with {len(config_obj.get('views', []))} views."
            if args.json_output:
                print(json.dumps(result_data, indent=2, ensure_ascii=False))
            else:
                print(result_data["message"])
            return 0

        # 2. Create dashboard if it does not exist
        if not dashboard_exists:
            create_res = ws.call(
                "lovelace/dashboards/create",
                url_path=args.url_path,
                title=args.title,
                icon=args.icon,
                show_in_sidebar=True,
                require_admin=False,
            )
            if not create_res.get("success"):
                raise RuntimeError(f"Failed to create dashboard '{args.url_path}': {create_res.get('error')}")
            result_data["created"] = True
        else:
            result_data["created"] = False

        # 3. Save Lovelace configuration for the dashboard
        save_res = ws.call(
            "lovelace/config/save",
            url_path=args.url_path,
            config=config_obj,
        )
        if not save_res.get("success"):
            raise RuntimeError(f"Failed to save lovelace config for '{args.url_path}': {save_res.get('error')}")

        result_data["success"] = True
        result_data["views_count"] = len(config_obj.get("views", []))
        result_data["dashboard_url"] = f"{url}/{args.url_path}"

        if args.json_output:
            print(json.dumps(result_data, indent=2, ensure_ascii=False))
        else:
            print(f"Erfolg: Dashboard '{args.title}' wurde erfolgreich angelegt!")
            print(f"  - URL: {result_data['dashboard_url']}")
            print(f"  - URL-Slug: {args.url_path}")
            print(f"  - Reiter / Views: {result_data['views_count']} Tabs (Home, Klima, Licht, Audio, Sicherheit, Health)")
            print(f"  - Seitenleiste: Sichtbar (Icon: {args.icon})")

        return 0

    except Exception as exc:
        if args.json_output:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
