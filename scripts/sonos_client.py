#!/usr/bin/env python3
"""
sonos_client.py — Python-first Sonos Multiroom & Topology Client (stdlib-only).
Directly queries local Sonos players via UPnP SOAP on port 1400.

Features:
- Inspect Zone Groups, Coordinators, and bonded Stereo Pairs (ChannelMapSet)
- List all physical Sonos players with IP, MAC, Hardware Gen (A100 vs A201), and Software Version
- Structured CLI JSON envelope (--json)
- Zero external dependencies (Python 3 stdlib-only)

Target players are resolved from an explicit `--ip`/API list, the optional
`SONOS_IPS` environment variable (comma-separated), or best-effort SSDP
discovery on the local network. No home-specific IPs are hardcoded.

Usage:
    python scripts/sonos_client.py topology [--ip 192.168.0.10 ...] [--json]
    python scripts/sonos_client.py players  [--ip 192.168.0.10 ...] [--json]
    SONOS_IPS=192.168.0.10,192.168.0.11 python scripts/sonos_client.py players
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


def discover_sonos_ips(timeout: float = 3.0) -> List[str]:
    """Best-effort SSDP discovery of local Sonos players via UDP multicast."""
    message = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 1\r\n"
        "ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n"
    )
    found: List[str] = []
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.sendto(message.encode("utf-8"), ("239.255.255.250", 1900))
        while True:
            try:
                _data, addr = sock.recvfrom(65507)
            except socket.timeout:
                break
            if addr[0] not in found:
                found.append(addr[0])
    except Exception:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    return found


def resolve_ips(ips: Optional[List[str]] = None) -> List[str]:
    """Resolve target IPs from explicit list, SONOS_IPS env, or SSDP discovery."""
    if ips:
        return ips
    env = os.environ.get("SONOS_IPS", "").strip()
    if env:
        return [ip.strip() for ip in env.split(",") if ip.strip()]
    return discover_sonos_ips()


def query_zone_group_state(seed_ip: str) -> Optional[str]:
    """Queries ZoneGroupState XML from a Sonos speaker via UPnP SOAP."""
    soap_body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body>'
        '<u:GetZoneGroupState xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1"/>'
        '</s:Body>'
        '</s:Envelope>'
    )
    req = urllib.request.Request(
        f"http://{seed_ip}:1400/ZoneGroupTopology/Control",
        data=soap_body.encode("utf-8"),
        headers={
            "SOAPAction": "urn:schemas-upnp-org:service:ZoneGroupTopology:1#GetZoneGroupState",
            "Content-Type": 'text/xml; charset="utf-8"',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            root = ET.fromstring(resp.read())
            zg_elem = root.find(".//ZoneGroupState")
            return zg_elem.text if zg_elem is not None else None
    except Exception:
        return None


def get_topology(seed_ips: Optional[List[str]] = None) -> Dict[str, Any]:
    """Parses full zone group topology including bonded stereo pairs."""
    ips = resolve_ips(seed_ips)
    zg_xml = None
    active_ip = None

    for ip in ips:
        zg_xml = query_zone_group_state(ip)
        if zg_xml:
            active_ip = ip
            break

    if not zg_xml:
        return {"success": False, "error": "Kein erreichbarer Sonos-Speaker gefunden."}

    try:
        root = ET.fromstring(zg_xml)
        groups = []
        for zg in root.findall(".//ZoneGroup"):
            coord_uuid = zg.attrib.get("Coordinator", "")
            group_id = zg.attrib.get("ID", "")
            members = []
            stereo_pairs = []

            for m in zg.findall(".//ZoneGroupMember"):
                uuid = m.attrib.get("UUID", "")
                name = m.attrib.get("ZoneName", "")
                channel = m.attrib.get("ChannelMapSet", "")
                is_coord = (uuid == coord_uuid)

                # Channel map analysis: e.g. "RINCON_...:LF,LF;RINCON_...:RF,RF"
                channels = []
                if channel:
                    for part in channel.split(";"):
                        if ":" in part:
                            p_uuid, p_ch = part.split(":", 1)
                            if p_uuid == uuid:
                                channels.append(p_ch)

                role = "standalone"
                if "LF,LF" in channels:
                    role = "Stereo Left (LF)"
                elif "RF,RF" in channels:
                    role = "Stereo Right (RF)"
                elif "SW" in channels:
                    role = "Subwoofer (SW)"

                members.append({
                    "name": name,
                    "uuid": uuid,
                    "is_coordinator": is_coord,
                    "channel_map": channel,
                    "role": role,
                })

            groups.append({
                "group_id": group_id,
                "coordinator_uuid": coord_uuid,
                "members_count": len(members),
                "members": members,
            })

        return {
            "success": True,
            "source_ip": active_ip,
            "groups_count": len(groups),
            "groups": groups,
        }
    except Exception as err:
        return {"success": False, "error": f"XML-Parsing-Fehler: {err}"}


def get_players_info(ips: Optional[List[str]] = None) -> Dict[str, Any]:
    """Queries /status/zp on all Sonos speakers to get hardware generations and firmware."""
    target_ips = resolve_ips(ips)
    players = []

    for ip in target_ips:
        try:
            with urllib.request.urlopen(f"http://{ip}:1400/status/zp", timeout=2) as resp:
                root = ET.fromstring(resp.read())
                info = root.find("ZPInfo")
                if info is not None:
                    name = info.findtext("ZoneName", "")
                    mac = info.findtext("MACAddress", "")
                    series = info.findtext("SeriesID", "")
                    sw = info.findtext("SoftwareVersion", "")
                    hw = info.findtext("HardwareVersion", "")
                    uid = info.findtext("LocalUID", "")

                    gen = "Gen 2" if series == "A201" else ("Gen 1 / Sub" if series == "A100" else series)

                    players.append({
                        "ip": ip,
                        "name": name,
                        "uuid": uid,
                        "mac": mac,
                        "series_id": series,
                        "generation": gen,
                        "hardware_version": hw,
                        "software_version": sw,
                        "status": "online",
                    })
        except Exception:
            players.append({
                "ip": ip,
                "status": "offline",
            })

    return {
        "success": True,
        "players_count": len(players),
        "online_count": sum(1 for p in players if p.get("status") == "online"),
        "players": players,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sonos Multiroom & Topology Client (stdlib-only)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    top_parser = subparsers.add_parser("topology", help="Show active Zone Groups & Stereo Pairs")
    top_parser.add_argument("--ip", action="append", default=None, help="Seed player IP (repeatable; default: SONOS_IPS env or SSDP discovery)")
    top_parser.add_argument("--json", action="store_true", help="Output JSON envelope")

    players_parser = subparsers.add_parser("players", help="List physical players, generations & versions")
    players_parser.add_argument("--ip", action="append", default=None, help="Player IP (repeatable; default: SONOS_IPS env or SSDP discovery)")
    players_parser.add_argument("--json", action="store_true", help="Output JSON envelope")

    args = parser.parse_args()

    if args.command == "topology":
        res = get_topology(args.ip)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            if not res.get("success"):
                print(f"[ERROR] {res.get('error')}", file=sys.stderr)
                return 1
            print(f"Sonos Topologie ({res.get('groups_count')} Gruppen aktiv):")
            for i, g in enumerate(res.get("groups", []), 1):
                print(f"\n--- Gruppe {i} (Koordinator: {g.get('coordinator_uuid')}) ---")
                for m in g.get("members", []):
                    coord_mark = " [Master]" if m.get("is_coordinator") else ""
                    print(f"  * {m.get('name')}: {m.get('role')}{coord_mark} ({m.get('uuid')})")
        return 0 if res.get("success") else 1

    elif args.command == "players":
        res = get_players_info(args.ip)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            if not res.get("success"):
                print(f"[ERROR] {res.get('error')}", file=sys.stderr)
                return 1
            print(f"Sonos Hardware-Inventar ({res.get('online_count')}/{res.get('players_count')} online):")
            for p in res.get("players", []):
                if p.get("status") == "online":
                    print(f"  * {p.get('ip'):15} | {p.get('name'):23} | {p.get('generation'):10} | MAC: {p.get('mac')} | FW: {p.get('software_version')}")
                else:
                    print(f"  * {p.get('ip'):15} | OFFLINE")
        return 0 if res.get("success") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
