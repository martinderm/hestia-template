#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
run_health_audit.py — Comprehensive Health Audit for Home Assistant Green.
Implements the 4-step pipeline defined in pipelines/03_health-audit/CONTEXT.md:
  01_backup : Letzten Home Assistant Backup-Status prüfen -> backup-health.json
  02_mesh   : Signalstärke (LQI / RSSI) & Batterie-Zustände -> mesh-topology.json
  03_logs   : Entitäts-Verfügbarkeit, Core- & Add-on Updates -> log-findings.md
  04_report : Audit-Bericht in memory/operations/health-audit-<date>.md archivieren

Usage:
    python scripts/run_health_audit.py [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ha_client import ha_request, load_env_token


def atomic_write(filepath: Path, content: str) -> None:
    """Safely write content atomically using a temp file and os.replace."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = filepath.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(temp_dir), prefix=f"{filepath.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(filepath))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def audit_backup(states_by_id: Dict[str, Any]) -> Dict[str, Any]:
    """Step 01: Audit Home Assistant backup health."""
    mgr_state = states_by_id.get("sensor.backup_backup_manager_state", {}).get("state", "unknown")
    last_success = states_by_id.get("sensor.backup_last_successful_automatic_backup", {}).get("state", "unknown")
    last_attempt = states_by_id.get("sensor.backup_zuletzt_versuchtes_automatisches_backup", {}).get("state", "unknown")
    next_sched = states_by_id.get("sensor.backup_next_scheduled_automatic_backup", {}).get("state", "unknown")
    event_state = states_by_id.get("event.backup_automatisches_backup", {}).get("state", "unknown")

    is_healthy = mgr_state == "idle" and last_success != "unknown"

    return {
        "status": "HEALTHY" if is_healthy else "WARNING",
        "manager_state": mgr_state,
        "last_successful_backup": last_success,
        "last_attempted_backup": last_attempt,
        "next_scheduled_backup": next_sched,
        "event_timestamp": event_state,
        "score": 100 if is_healthy else 50,
        "notes": "Automatisches Backup läuft planmäßig täglich um ca. 03:00 UTC." if is_healthy else "Backup-Status unklar.",
    }


def audit_mesh_and_power(states_by_id: Dict[str, Any]) -> Dict[str, Any]:
    """Step 02: Audit wireless mesh signal strengths and battery levels."""
    rssi_sensors = {}
    battery_levels = {}
    low_batteries = {}
    critical_batteries = {}

    for eid, st in states_by_id.items():
        attrs = st.get("attributes", {})
        state_val = st.get("state")
        friendly = attrs.get("friendly_name", eid)

        # RSSI / LQI / Linkquality
        if "rssi" in eid.lower() or "lqi" in eid.lower() or "linkquality" in eid.lower():
            try:
                rssi_sensors[eid] = {
                    "value": float(state_val),
                    "unit": attrs.get("unit_of_measurement", "dBm"),
                    "name": friendly,
                }
            except (ValueError, TypeError):
                pass

        # Batteries
        is_batt = attrs.get("device_class") == "battery" or "batterie" in eid.lower() or "battery" in eid.lower()
        if is_batt:
            try:
                pct = float(state_val)
                batt_info = {
                    "percentage": pct,
                    "name": friendly,
                    "entity_id": eid,
                }
                battery_levels[eid] = batt_info
                if pct <= 5.0:
                    critical_batteries[eid] = batt_info
                elif pct <= 20.0:
                    low_batteries[eid] = batt_info
            except (ValueError, TypeError):
                pass

    # Score calculation
    # Base 100 - (15 per critical battery) - (5 per low battery)
    mesh_score = max(0, 100 - (len(critical_batteries) * 15) - (len(low_batteries) * 5))

    return {
        "status": "WARNING" if critical_batteries or low_batteries else "HEALTHY",
        "score": mesh_score,
        "rssi_sensors": rssi_sensors,
        "total_battery_devices": len(battery_levels),
        "critical_batteries": critical_batteries,
        "low_batteries": low_batteries,
        "all_batteries": sorted(battery_levels.values(), key=lambda x: x["percentage"]),
    }


def audit_logs_and_availability(states_by_id: Dict[str, Any], config_data: Dict[str, Any]) -> Dict[str, Any]:
    """Step 03: Audit entity availability and software/addon updates."""
    total_entities = len(states_by_id)
    unavailable = []
    unknown = []

    for eid, st in states_by_id.items():
        s = st.get("state")
        friendly = st.get("attributes", {}).get("friendly_name", eid)
        if s == "unavailable":
            unavailable.append({"entity_id": eid, "name": friendly})
        elif s == "unknown":
            unknown.append({"entity_id": eid, "name": friendly})

    # Updates
    pending_updates = []
    installed_updates = []
    for eid, st in states_by_id.items():
        if eid.startswith("update."):
            attrs = st.get("attributes", {})
            friendly = attrs.get("friendly_name", eid)
            installed = attrs.get("installed_version")
            latest = attrs.get("latest_version")
            if st.get("state") == "on":
                pending_updates.append({
                    "entity_id": eid,
                    "name": friendly,
                    "installed_version": installed,
                    "latest_version": latest,
                })
            else:
                installed_updates.append({
                    "entity_id": eid,
                    "name": friendly,
                    "version": installed,
                })

    # Group unavailable by likely root device
    unavailable_grouped: Dict[str, List[str]] = {}
    for item in unavailable:
        eid = item["entity_id"]
        # Prefix extraction
        prefix = eid.split(".")[1].split("_")[0] if "_" in eid else eid.split(".")[1]
        unavailable_grouped.setdefault(prefix, []).append(eid)

    # Availability score
    avail_pct = ((total_entities - len(unavailable)) / total_entities) * 100 if total_entities else 100
    log_score = int(round(avail_pct))

    return {
        "status": "WARNING" if pending_updates or len(unavailable) > 50 else "HEALTHY",
        "score": log_score,
        "total_entities": total_entities,
        "unavailable_count": len(unavailable),
        "unknown_count": len(unknown),
        "unavailable_percentage": round((len(unavailable) / total_entities) * 100, 1) if total_entities else 0,
        "pending_updates": pending_updates,
        "pending_updates_count": len(pending_updates),
        "unavailable_samples": unavailable[:20],
        "unavailable_grouped_count": {k: len(v) for k, v in sorted(unavailable_grouped.items(), key=lambda x: -len(x[1]))[:10]},
        "ha_version": config_data.get("version", "Unknown"),
        "ha_location": config_data.get("location_name", "Unknown"),
    }


def generate_log_findings_md(findings: Dict[str, Any]) -> str:
    """Generates pipelines/03_health-audit/log-findings.md."""
    lines = [
        "# Log & Availability Findings",
        "",
        f"**Audit-Zeitpunkt:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**HA Core Version:** `{findings['ha_version']}` ({findings['ha_location']})",
        f"**Entitäten Gesamt:** {findings['total_entities']}",
        f"**Nicht verfügbar (unavailable):** {findings['unavailable_count']} ({findings['unavailable_percentage']} %)",
        f"**Unbekannter Zustand (unknown):** {findings['unknown_count']}",
        "",
        "## Ausstehende Updates",
        "",
    ]

    if not findings["pending_updates"]:
        lines.append("✅ Alle Systeme, Core-Komponenten und Add-ons sind auf dem neuesten Stand.")
    else:
        lines.extend([
            "| Komponente | Installierte Version | Verfügbare Version | Entität |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for u in findings["pending_updates"]:
            lines.append(f"| {u['name']} | `{u['installed_version']}` | `{u['latest_version']}` | `{u['entity_id']}` |")
    lines.append("")

    lines.extend([
        "## Schwerpunkte nicht verfügbarer Entitäten (Offline Clusters)",
        "",
        "Häufigste Cluster (z. B. stromlos geschaltete Leuchten oder entfernte Sensoren):",
        "",
        "| Cluster / Präfix | Betroffene Entitäten | Typische Ursache |",
        "| :--- | :--- | :--- |",
    ])
    for cluster, count in findings["unavailable_grouped_count"].items():
        lines.append(f"| `{cluster}` | {count} | Wandtaster / Stromlos geschaltet |")
    lines.append("")

    return "\n".join(lines)


def generate_full_report_md(
    backup_data: Dict[str, Any],
    mesh_data: Dict[str, Any],
    log_data: Dict[str, Any],
    areas_count: int,
    devices_count: int,
) -> str:
    """Step 04: Generates memory/operations/health-audit-<date>.md."""
    today_str = datetime.date.today().isoformat()
    overall_score = int(round((backup_data["score"] * 0.3) + (mesh_data["score"] * 0.3) + (log_data["score"] * 0.4)))

    status_badge = "🟢 GUT" if overall_score >= 80 else ("🟡 WARNUNG" if overall_score >= 60 else "🔴 KRITISCH")

    lines = [
        f"# Smart Home Health Audit — {today_str}",
        "",
        f"Operativer Audit-Bericht für Home Assistant (`{log_data['ha_location']}`).",
        f"Erstellt gemäß Pipeline [`pipelines/03_health-audit/`](../../pipelines/03_health-audit/CONTEXT.md).",
        "",
        "## Executive Summary",
        "",
        f"- **Gesamt-Gesundheitsstatus:** {status_badge} (**{overall_score} / 100 Punkten**)",
        f"- **Home Assistant Version:** `{log_data['ha_version']}`",
        f"- **Erfasste Bereiche (Areas):** {areas_count} Räume",
        f"- **Erfasste physische Geräte:** {devices_count} Geräte",
        f"- **Gesamtzahl Entitäten:** {log_data['total_entities']}",
        f"- **Backup-Integrität:** {backup_data['status']} ({backup_data['score']}/100)",
        f"- **Drahtlos- & Batterie-Zustand:** {mesh_data['status']} ({mesh_data['score']}/100)",
        f"- **Entitäts-Verfügbarkeit:** {log_data['status']} ({log_data['score']}/100)",
        "",
        "---",
        "",
        "## 1. Backup-Integrität (`01_backup`)",
        "",
        f"- **Backup Manager Zustand:** `{backup_data['manager_state']}`",
        f"- **Letztes erfolgreiches Backup:** `{backup_data['last_successful_backup']}`",
        f"- **Letzter Backup-Versuch:** `{backup_data['last_attempted_backup']}`",
        f"- **Nächstes geplantes Backup:** `{backup_data['next_scheduled_backup']}`",
        f"- **Audit-Urteil:** {backup_data['notes']}",
        "",
        "---",
        "",
        "## 2. Drahtlos-Signalstärke & Batterie-Audits (`02_mesh`)",
        "",
        f"- **Überwachte Batteriegeräte:** {mesh_data['total_battery_devices']}",
        f"- **Kritische Batterien (≤ 5%):** {len(mesh_data['critical_batteries'])}",
        f"- **Niedrige Batterien (≤ 20%):** {len(mesh_data['low_batteries'])}",
        "",
    ]

    if mesh_data["critical_batteries"] or mesh_data["low_batteries"]:
        lines.extend([
            "### ⚠️ Batteriewarnungen (Handlungsbedarf)",
            "",
            "| Gerät / Entität | Batteriestand | Dringlichkeit |",
            "| :--- | :--- | :--- |",
        ])
        for eid, b in mesh_data["critical_batteries"].items():
            lines.append(f"| {b['name']} (`{eid}`) | **{b['percentage']} %** | 🔴 Sofortiger Batteriewechsel |")
        for eid, b in mesh_data["low_batteries"].items():
            lines.append(f"| {b['name']} (`{eid}`) | **{b['percentage']} %** | 🟡 Zeitnah aufladen / tauschen |")
        lines.append("")

    if mesh_data["rssi_sensors"]:
        lines.extend([
            "### RSSI Signalwerte",
            "",
            "| Sensor | Signalstärke | Bewertung |",
            "| :--- | :--- | :--- |",
        ])
        for eid, r in mesh_data["rssi_sensors"].items():
            qual = "Exzellent" if r["value"] > -60 else ("Gut" if r["value"] > -70 else "Schwach")
            lines.append(f"| {r['name']} | `{r['value']} {r['unit']}` | {qual} |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. Log-Analyse & Verfügbarkeit (`03_logs`)",
        "",
        f"- **Aktive / Verfügbare Entitäten:** {log_data['total_entities'] - log_data['unavailable_count']} von {log_data['total_entities']} ({100 - log_data['unavailable_percentage']} %)",
        f"- **Nicht verfügbare Entitäten:** {log_data['unavailable_count']} ({log_data['unavailable_percentage']} %)",
        f"- **Entitäten mit unbekanntem Zustand:** {log_data['unknown_count']}",
        "",
        "### Ausstehende Updates",
        "",
    ])

    if not log_data["pending_updates"]:
        lines.append("✅ Keine offenen Updates vorhanden.")
    else:
        lines.extend([
            "| Komponente | Aktuell | Neu | Typ |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for u in log_data["pending_updates"]:
            lines.append(f"| {u['name']} | `{u['installed_version']}` | `{u['latest_version']}` | Update verfügbar |")
    lines.append("")

    # Derive action items from the audit results (no home-specific hardcoding).
    action_items: List[Tuple[str, str, str]] = []
    for eid, b in mesh_data["critical_batteries"].items():
        action_items.append(("P1 — Hoch", "Batterie austauschen", f"{b['name']} (`{eid}`, {b['percentage']} %)"))
    for eid, b in mesh_data["low_batteries"].items():
        action_items.append(("P2 — Mittel", "Batterie vorbereiten", f"{b['name']} (`{eid}`, {b['percentage']} %)"))
    for u in log_data["pending_updates"]:
        action_items.append(("P3 — Mittel", "Software-Update einspielen", f"{u['name']} (`{u['entity_id']}`)"))
    if log_data["unavailable_count"] > 0:
        action_items.append(("P4 — Wartung", "Nicht verfügbare Entitäten prüfen", f"{log_data['unavailable_count']} Entitäten (unavailable)"))
    if backup_data["status"] != "HEALTHY":
        action_items.append(("P5 — Monitoring", "Backup-Status klären", "Backup Manager"))

    lines.extend([
        "---",
        "",
        "## 4. Topologie & Governance Befunde (ICM Form 6)",
        "",
        f"1. **Räume & System Map:** {areas_count} Räume sind in `map/areas/` erfasst.",
        f"2. **Geräte-Inventar:** {devices_count} Hardware-Geräte sind in `map/devices/` katalogisiert.",
        "3. **Invariante 1 (Area-Zuordnung):** Jede Entität gehört zu genau einer primären Area; Abweichungen sind über `scripts/inspect_unmapped_entities.py` sichtbar.",
        "4. **Invariante 2 (Namenskonvention):** Empfohlen ist `<domain>.<area>_<funktion>`; Abweichungen erzeugt das Namensaudit in `map/areas/`.",
        "",
        "---",
        "",
        "## 5. Handlungsempfehlungen (Action Items)",
        "",
    ])
    if action_items:
        lines.extend([
            "| Priorität | Maßnahme | Betroffene Komponenten |",
            "| :--- | :--- | :--- |",
        ])
        for prio, action, target in action_items:
            lines.append(f"| **{prio}** | {action} | {target} |")
    else:
        lines.append("✅ Keine unmittelbaren Maßnahmen erforderlich.")
    lines.extend([
        "",
        f"**Audit durchgeführt am:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        "**Verantwortlicher Agent:** siehe `AGENTS.md`",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Home Assistant Health Audit")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without writing files")
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

    try:
        # Fetch states
        states_res = ha_request(url, "states", token)
        if not states_res.get("success"):
            raise RuntimeError(f"Failed to fetch states: {states_res.get('error')}")
        states_list = states_res.get("data", [])
        states_by_id = {s["entity_id"]: s for s in states_list}

        # Fetch config
        config_res = ha_request(url, "config", token)
        config_data = config_res.get("data", {}) if config_res.get("success") else {}

        # 01_backup
        backup_audit = audit_backup(states_by_id)

        # 02_mesh
        mesh_audit = audit_mesh_and_power(states_by_id)

        # 03_logs
        log_audit = audit_logs_and_availability(states_by_id, config_data)

        # Area and device counts from map/
        root_dir = Path(__file__).resolve().parent.parent
        areas_dir = root_dir / "map" / "areas"
        devices_dir = root_dir / "map" / "devices"
        areas_count = len([f for f in areas_dir.glob("*.md") if f.name != "README.md"]) if areas_dir.exists() else 0
        devices_count = len([f for f in devices_dir.glob("*.md") if f.name != "README.md"]) if devices_dir.exists() else 0

        today_str = datetime.date.today().isoformat()
        pipeline_dir = root_dir / "pipelines" / "03_health-audit"
        ops_dir = root_dir / "memory" / "operations"

        written_files = []

        if not args.dry_run:
            # 1. backup-health.json
            backup_file = pipeline_dir / "backup-health.json"
            atomic_write(backup_file, json.dumps(backup_audit, indent=2, ensure_ascii=False))
            written_files.append(str(backup_file))

            # 2. mesh-topology.json
            mesh_file = pipeline_dir / "mesh-topology.json"
            atomic_write(mesh_file, json.dumps(mesh_audit, indent=2, ensure_ascii=False))
            written_files.append(str(mesh_file))

            # 3. log-findings.md
            log_file = pipeline_dir / "log-findings.md"
            atomic_write(log_file, generate_log_findings_md(log_audit))
            written_files.append(str(log_file))

            # 4. memory/operations/health-audit-<date>.md
            report_file = ops_dir / f"health-audit-{today_str}.md"
            full_report = generate_full_report_md(backup_audit, mesh_audit, log_audit, areas_count, devices_count)
            atomic_write(report_file, full_report)
            written_files.append(str(report_file))

        overall_score = int(round((backup_audit["score"] * 0.3) + (mesh_audit["score"] * 0.3) + (log_audit["score"] * 0.4)))

        result = {
            "success": True,
            "dry_run": args.dry_run,
            "overall_score": overall_score,
            "backup_score": backup_audit["score"],
            "mesh_score": mesh_audit["score"],
            "availability_score": log_audit["score"],
            "total_entities": len(states_list),
            "unavailable_entities": log_audit["unavailable_count"],
            "critical_batteries_count": len(mesh_audit["critical_batteries"]),
            "pending_updates_count": log_audit["pending_updates_count"],
            "written_files": written_files,
        }

        if args.json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Health Audit completed (Score: {overall_score}/100)")
            print(f"  - Backup: {backup_audit['status']} ({backup_audit['score']}/100)")
            print(f"  - Mesh & Batteries: {mesh_audit['status']} ({mesh_audit['score']}/100)")
            print(f"  - Availability: {log_audit['status']} ({log_audit['score']}/100)")
            if not args.dry_run:
                print(f"  - Written artifacts: {len(written_files)}")
                for wf in written_files:
                    print(f"    * {wf}")

        return 0
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
