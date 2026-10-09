#!/usr/bin/env python3
"""
build_system_map.py — Generate and synchronize Smart Home System Map (ICM Form 6).
Fetches topology from Home Assistant via REST API and generates:
- map/areas/<area_id>.md (10 rooms with entity mappings & naming audits)
- map/areas/README.md (Index of all areas)
- map/devices/<device_id>.md (Hardware inventory with model, manufacturer, entities)
- map/devices/README.md (Hardware inventory catalog)
- Updates map/CONTEXT.md with topology summary

Usage:
    python scripts/build_system_map.py [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Set

# Ensure scripts dir is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ha_client import ha_request, load_env_token

_AREA_ALIASES_CACHE: Optional[Dict[str, List[str]]] = None


def _load_area_aliases() -> Dict[str, List[str]]:
    """Optional per-home alias map: memory/canonical/area-aliases.json.

    Format: {"<area_stem>": ["alias1", "alias2"], ...}
    Used to recognise local naming variants of area prefixes.
    """
    global _AREA_ALIASES_CACHE
    if _AREA_ALIASES_CACHE is None:
        _AREA_ALIASES_CACHE = {}
        alias_file = Path(__file__).resolve().parent.parent / "memory" / "canonical" / "area-aliases.json"
        if alias_file.exists():
            try:
                data = json.loads(alias_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _AREA_ALIASES_CACHE = {
                        str(k).lower().replace("-", "_"): [str(a) for a in v]
                        for k, v in data.items()
                        if isinstance(v, list)
                    }
            except Exception:
                _AREA_ALIASES_CACHE = {}
    return _AREA_ALIASES_CACHE


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


def extract_ha_val(res: Dict[str, Any]) -> Any:
    """Extract data or parsed JSON from ha_request response."""
    if not res.get("success"):
        return None
    if "data" in res:
        return res["data"]
    text = res.get("text", "")
    try:
        return json.loads(text)
    except Exception:
        return text


def fetch_all_topology(url: str, token: str) -> Dict[str, Any]:
    """Queries Home Assistant for areas, entities, and devices."""
    # 1. Fetch areas
    areas_res = ha_request(url, "template", token, method="POST", data={"template": "{{ areas() | to_json }}"})
    if not areas_res.get("success"):
        raise RuntimeError(f"Failed to fetch areas: {areas_res.get('error')}")
    area_ids = extract_ha_val(areas_res)
    if isinstance(area_ids, str):
        area_ids = json.loads(area_ids)

    # 2. Fetch full entity states
    states_res = ha_request(url, "states", token)
    if not states_res.get("success"):
        raise RuntimeError(f"Failed to fetch states: {states_res.get('error')}")
    states_list = states_res.get("data", [])
    states_by_id = {s["entity_id"]: s for s in states_list}

    # 3. For each area, get name, entities, devices
    areas_data = {}
    all_device_ids: Set[str] = set()

    for area_id in area_ids:
        # Get area name
        name_res = ha_request(url, "template", token, method="POST", data={"template": f'{{{{ area_name("{area_id}") }}}}'})
        area_name_val = extract_ha_val(name_res)
        area_name = str(area_name_val).strip() if area_name_val else area_id

        # Get area entities
        ents_res = ha_request(url, "template", token, method="POST", data={"template": f'{{{{ area_entities("{area_id}") | to_json }}}}'})
        area_entities = extract_ha_val(ents_res) or []
        if isinstance(area_entities, str):
            try:
                area_entities = json.loads(area_entities)
            except Exception:
                area_entities = []

        # Get area devices
        devs_res = ha_request(url, "template", token, method="POST", data={"template": f'{{{{ area_devices("{area_id}") | to_json }}}}'})
        area_devices = extract_ha_val(devs_res) or []
        if isinstance(area_devices, str):
            try:
                area_devices = json.loads(area_devices)
            except Exception:
                area_devices = []

        for d in area_devices:
            all_device_ids.add(d)

        areas_data[area_id] = {
            "area_id": area_id,
            "name": area_name,
            "entities": sorted(area_entities),
            "devices": sorted(area_devices),
        }

    # 4. Also check device_id for all states in batches of 100
    all_entity_ids = list(states_by_id.keys())
    batch_size = 100
    for i in range(0, len(all_entity_ids), batch_size):
        chunk = all_entity_ids[i:i + batch_size]
        tmpl = f"""
        {{% set res = namespace(items=[]) %}}
        {{% for eid in {json.dumps(chunk)} %}}
          {{% set did = device_id(eid) %}}
          {{% if did %}}
            {{% set res.items = res.items + [[eid, did]] %}}
          {{% endif %}}
        {{% endfor %}}
        {{{{ res.items | to_json }}}}
        """
        b_res = ha_request(url, "template", token, method="POST", data={"template": tmpl})
        items = extract_ha_val(b_res)
        if isinstance(items, list):
            for pair in items:
                if isinstance(pair, list) and len(pair) == 2:
                    eid, did = pair
                    if did:
                        all_device_ids.add(did)

    # 5. Query device details in batches of 25 devices
    devices_data = {}
    all_dev_list = sorted(all_device_ids)
    dev_batch_size = 25
    for i in range(0, len(all_dev_list), dev_batch_size):
        chunk_devs = all_dev_list[i:i + dev_batch_size]
        dev_tmpl = f"""
        {{% set res = namespace(items=[]) %}}
        {{% for did in {json.dumps(chunk_devs)} %}}
          {{% set item = {{
            "device_id": did,
            "name": device_attr(did, "name"),
            "name_by_user": device_attr(did, "name_by_user"),
            "manufacturer": device_attr(did, "manufacturer"),
            "model": device_attr(did, "model"),
            "sw_version": device_attr(did, "sw_version"),
            "hw_version": device_attr(did, "hw_version"),
            "area_id": device_attr(did, "area_id"),
            "disabled_by": device_attr(did, "disabled_by"),
            "entry_type": device_attr(did, "entry_type"),
            "entities": device_entities(did)
          }} %}}
          {{% set res.items = res.items + [item] %}}
        {{% endfor %}}
        {{{{ res.items | to_json }}}}
        """
        d_res = ha_request(url, "template", token, method="POST", data={"template": dev_tmpl})
        items = extract_ha_val(d_res)
        if isinstance(items, list):
            for dev_item in items:
                if isinstance(dev_item, dict) and "device_id" in dev_item:
                    did = dev_item["device_id"]
                    if isinstance(dev_item.get("entities"), list):
                        dev_item["entities"] = sorted(dev_item["entities"])
                    devices_data[did] = dev_item

    # Build entity_to_device mapping from device entities
    entity_to_device: Dict[str, str] = {}
    for did, d in devices_data.items():
        for eid in d.get("entities", []):
            entity_to_device[eid] = did

    return {
        "areas": areas_data,
        "devices": devices_data,
        "entity_to_device": entity_to_device,
        "states_count": len(states_list),
        "states_by_id": states_by_id,
    }


def audit_naming_convention(entity_id: str, area_id: str) -> tuple[str, str]:
    """Check if entity_id conforms to <domain>.<area>_<funktion>."""
    parts = entity_id.split(".", 1)
    if len(parts) != 2:
        return "⚠️ Abweichend", "Ungültiges Entity-Format"
    domain, name = parts
    # Check if area prefix or a configured local alias matches
    area_stem = area_id.lower().replace("-", "_")
    area_aliases = [area_stem]
    area_aliases.extend(_load_area_aliases().get(area_stem, []))

    if any(name.lower().startswith(alias) for alias in area_aliases):
        return "✅ Konform", f"Entspricht `{domain}.{area_id}_*`"
    return "⚠️ Abweichend", f"Enthält kein Area-Präfix `{area_id}_`"


def generate_area_markdown(area: Dict[str, Any], devices: Dict[str, Any], states_by_id: Dict[str, Any], entity_to_device: Dict[str, str]) -> str:
    """Generates map/areas/<area_id>.md."""
    aid = area["area_id"]
    name = area["name"]
    area_devs = area["devices"]
    area_ents = area["entities"]

    lines = [
        f"# Area: {name} (`{aid}`)",
        "",
        f"Kanonischer physischer Raum im Smart Home.",
        "",
        "## Stammdaten",
        "",
        f"- **Area ID:** `{aid}`",
        f"- **Anzeigename:** {name}",
        f"- **Geräte (Hardware):** {len(area_devs)}",
        f"- **Entitäten gesamt:** {len(area_ents)}",
        f"- **Stand der Erfassung:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Hardware-Inventar (Geräte)",
        "",
    ]

    if not area_devs:
        lines.append("*Keine Hardware-Geräte direkt diesem Raum zugeordnet.*")
        lines.append("")
    else:
        lines.extend([
            "| Gerät | Hersteller | Modell | Firmware | Gerätedatei |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for did in area_devs:
            d = devices.get(did, {})
            d_name = d.get("name_by_user") or d.get("name") or did
            mfg = d.get("manufacturer") or "Unbekannt"
            model = d.get("model") or "Unbekannt"
            sw = d.get("sw_version") or "-"
            lines.append(f"| [{d_name}](../devices/{did}.md) | {mfg} | {model} | {sw} | [`{did[:8]}...`](../devices/{did}.md) |")
        lines.append("")

    lines.extend([
        "## Entitäten-Mapping",
        "",
    ])

    if not area_ents:
        lines.append("*Keine Entitäten diesem Raum zugeordnet.*")
        lines.append("")
    else:
        lines.extend([
            "| Entität | Domain | Friendly Name | Zustand | Zugeordnetes Gerät |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for eid in area_ents:
            domain = eid.split(".")[0]
            st = states_by_id.get(eid, {})
            attrs = st.get("attributes", {})
            friendly = attrs.get("friendly_name", eid)
            state_val = st.get("state", "unknown")
            did = entity_to_device.get(eid)
            if did and did in devices:
                d = devices[did]
                d_name = d.get("name_by_user") or d.get("name") or did[:8]
                dev_link = f"[{d_name}](../devices/{did}.md)"
            else:
                dev_link = "-"
            lines.append(f"| `{eid}` | `{domain}` | {friendly} | `{state_val}` | {dev_link} |")
        lines.append("")

    lines.extend([
        "## Namenskonventions-Audit",
        "",
        "Invariante 2 aus [`map/CONTEXT.md`](../CONTEXT.md): `<domain>.<area>_<funktion>`",
        "",
    ])

    if not area_ents:
        lines.append("*Keine Entitäten für Prüfung vorhanden.*")
        lines.append("")
    else:
        lines.extend([
            "| Entität | Konformität | Befund |",
            "| :--- | :--- | :--- |",
        ])
        for eid in area_ents:
            status, note = audit_naming_convention(eid, aid)
            lines.append(f"| `{eid}` | {status} | {note} |")
        lines.append("")

    return "\n".join(lines)


def generate_device_markdown(dev_id: str, d: Dict[str, Any], areas: Dict[str, Any], states_by_id: Dict[str, Any]) -> str:
    """Generates map/devices/<device_id>.md."""
    name = d.get("name_by_user") or d.get("name") or dev_id
    mfg = d.get("manufacturer") or "Unbekannt"
    model = d.get("model") or "Unbekannt"
    sw = d.get("sw_version") or "-"
    hw = d.get("hw_version") or "-"
    aid = d.get("area_id") or ""
    area_info = areas.get(aid, {})
    area_name = area_info.get("name", "Nicht zugeordnet")
    area_link = f"[{area_name}](../areas/{aid}.md)" if aid else "*Nicht zugeordnet*"
    entities = d.get("entities") or []

    lines = [
        f"# Hardware-Gerät: {name}",
        "",
        f"Inventar-Datensatz für physisches Smart-Home-Gerät im Home Assistant.",
        "",
        "## Gerätestammdaten",
        "",
        f"- **Geräte-ID:** `{dev_id}`",
        f"- **Name:** {name}",
        f"- **Hersteller:** {mfg}",
        f"- **Modell:** {model}",
        f"- **Firmware / Software:** `{sw}`",
        f"- **Hardware-Version:** `{hw}`",
        f"- **Raum-Zuordnung:** {area_link}",
        f"- **Status Deaktivierung:** {d.get('disabled_by') or 'Aktiv'}",
        f"- **Erfassungszeitpunkt:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Bereitgestellte Entitäten",
        "",
    ]

    if not entities:
        lines.append("*Dieses Gerät stellt aktuell keine aktiven Entitäten bereit.*")
        lines.append("")
    else:
        lines.extend([
            "| Entität | Domain | Friendly Name | Aktueller Zustand |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for eid in entities:
            domain = eid.split(".")[0]
            st = states_by_id.get(eid, {})
            attrs = st.get("attributes", {})
            friendly = attrs.get("friendly_name", eid)
            state_val = st.get("state", "unknown")
            lines.append(f"| `{eid}` | `{domain}` | {friendly} | `{state_val}` |")
        lines.append("")

    return "\n".join(lines)


def generate_areas_index(areas: Dict[str, Any]) -> str:
    """Generates map/areas/README.md."""
    lines = [
        "# Smart Home Bereiche — map/areas",
        "",
        "Übersicht aller physischen Räume und Zonen im Smart Home.",
        "",
        "| Bereich-ID | Raumname | Geräte | Entitäten | Dokumentation |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    total_devs = sum(len(a["devices"]) for a in areas.values())
    total_ents = sum(len(a["entities"]) for a in areas.values())

    for aid in sorted(areas.keys()):
        a = areas[aid]
        lines.append(f"| `{aid}` | {a['name']} | {len(a['devices'])} | {len(a['entities'])} | [`{aid}.md`]({aid}.md) |")

    lines.extend([
        "",
        f"**Gesamt:** {len(areas)} Räume | {total_devs} Geräte-Zuordnungen | {total_ents} Entitäten in Räumen",
        "",
        "## Invarianten",
        "",
        "1. Jede Entität gehört zu genau einer primären Area.",
        "2. Benennungsmuster: `<domain>.<area>_<funktion>`.",
        "3. Änderungen an Raumnamen oder Entitätszuordnungen erfordern Prüfung der Automationskataloge.",
    ])
    return "\n".join(lines)


def generate_devices_index(devices: Dict[str, Any], areas: Dict[str, Any]) -> str:
    """Generates map/devices/README.md."""
    lines = [
        "# Hardware-Inventar — map/devices",
        "",
        f"Vollständiges Verzeichnis aller {len(devices)} physischen Smart-Home-Geräte im System.",
        "",
        "| Gerät | Hersteller | Modell | Raum | Entitäten | Gerätedatei |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for did in sorted(devices.keys()):
        d = devices[did]
        name = d.get("name_by_user") or d.get("name") or did
        mfg = d.get("manufacturer") or "Unbekannt"
        model = d.get("model") or "Unbekannt"
        aid = d.get("area_id") or ""
        area_name = areas.get(aid, {}).get("name", "Nicht zugeordnet") if aid else "-"
        area_link = f"[{area_name}](../areas/{aid}.md)" if aid else "-"
        ent_count = len(d.get("entities") or [])
        lines.append(f"| [{name}]({did}.md) | {mfg} | {model} | {area_link} | {ent_count} | [`{did[:8]}...`]({did}.md) |")

    lines.extend([
        "",
        f"**Inventar-Stand:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ])
    return "\n".join(lines)


def update_map_context(areas: Dict[str, Any], devices: Dict[str, Any], root_dir: Path) -> None:
    """Updates map/CONTEXT.md with summary."""
    context_file = root_dir / "map" / "CONTEXT.md"
    area_names = ", ".join(sorted(a["name"] for a in areas.values())) or "noch keine erfasst"
    content = f"""# Smart Home System Map

ICM Form 6: Kartografierung der physischen und logischen Topologie des Smart Homes rund um Home Assistant.

## Struktur & Kataloge

- [`areas/`](areas/README.md): **{len(areas)} physische Räume und Zonen** ({area_names}).
- [`devices/`](devices/README.md): **{len(devices)} Physische Geräte** (Hardware-Inventar).
- [`integrations/`](integrations/README.md): Home Assistant Integrationen und Controller.

## Topologie-Übersicht

| Kennzahl | Wert |
| :--- | :--- |
| **Erfasste Räume** | {len(areas)} |
| **Erfasste Hardware-Geräte** | {len(devices)} |
| **Letzte Bestandssynchronisation** | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} |

## Invarianten

1. **Jede Entität hat genau eine primäre Area.**
2. **Namenskonvention:** `<domain>.<area>_<funktion>` (z. B. `light.living_room_ceiling`, `binary_sensor.hallway_motion`).
3. **Change Impact:** Vor dem Umbenennen oder Entfernen einer Entität prüft der Agent gegen die Automations-Kataloge in `memory/canonical/`.
"""
    atomic_write(context_file, content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Smart Home System Map")
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
        topo = fetch_all_topology(url, token)
        areas = topo["areas"]
        devices = topo["devices"]
        states_by_id = topo["states_by_id"]
        entity_to_device = topo["entity_to_device"]

        root_dir = Path(__file__).resolve().parent.parent

        written_files = []

        if not args.dry_run:
            # 1. Write map/areas/<area_id>.md for all 10 areas
            areas_dir = root_dir / "map" / "areas"
            for aid, a in areas.items():
                area_file = areas_dir / f"{aid}.md"
                md = generate_area_markdown(a, devices, states_by_id, entity_to_device)
                atomic_write(area_file, md)
                written_files.append(str(area_file))

            # 2. Write map/areas/README.md
            areas_index_file = areas_dir / "README.md"
            atomic_write(areas_index_file, generate_areas_index(areas))
            written_files.append(str(areas_index_file))

            # 3. Write map/devices/<device_id>.md for all devices
            devices_dir = root_dir / "map" / "devices"
            for did, d in devices.items():
                dev_file = devices_dir / f"{did}.md"
                md = generate_device_markdown(did, d, areas, states_by_id)
                atomic_write(dev_file, md)
                written_files.append(str(dev_file))

            # 4. Write map/devices/README.md
            devs_index_file = devices_dir / "README.md"
            atomic_write(devs_index_file, generate_devices_index(devices, areas))
            written_files.append(str(devs_index_file))

            # 5. Update map/CONTEXT.md
            update_map_context(areas, devices, root_dir)
            written_files.append(str(root_dir / "map" / "CONTEXT.md"))

        result_summary = {
            "success": True,
            "dry_run": args.dry_run,
            "areas_count": len(areas),
            "devices_count": len(devices),
            "total_entities": topo["states_count"],
            "written_files_count": len(written_files),
            "areas": {aid: {"name": a["name"], "entities": len(a["entities"]), "devices": len(a["devices"])} for aid, a in areas.items()},
        }

        if args.json_output:
            print(json.dumps(result_summary, indent=2, ensure_ascii=False))
        else:
            status_str = "Dry-run completed" if args.dry_run else f"Successfully generated {len(written_files)} files"
            print(f"{status_str}: {len(areas)} areas, {len(devices)} devices, {topo['states_count']} entities.")
            for aid, a in areas.items():
                print(f"  - {a['name']} ({aid}): {len(a['devices'])} devices, {len(a['entities'])} entities")

        return 0
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
