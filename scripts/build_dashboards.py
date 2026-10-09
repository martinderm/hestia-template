#!/usr/bin/env python3
"""
build_dashboards.py — Generic Lovelace dashboard generator (stdlib-only).

Derives dashboards from a cached Home Assistant state dump and optional
per-home configuration. This file contains NO home-specific data; tailor it via:

  - memory/canonical/home-profile.json      -> {"name": "<Home label>"}
  - _shared/templates/dashboards/areas.json -> [{"id": "<area_id>", "name": "<Area>"}, ...]

Generates:
  - dashboards/CONTEXT.md
  - dashboards/home.yaml                  (Home Overview)
  - dashboards/domains/<domain>.yaml      (only for domains present in the state dump)
  - dashboards/areas/<area_id>.yaml       (only when areas.json defines areas)
  - dashboards/lovelace_complete.yaml     (All-in-one consolidated config)

State dump: tmp/states.json  (as produced by `ha_client.py states`), overridable
with `--states`. Use `--fetch` to query Home Assistant live via scripts/ha_client.py.

Usage:
    python scripts/build_dashboards.py [--states tmp/states.json] [--fetch] [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Domains rendered with a dedicated native card instead of a generic entities list.
DOMAIN_CARD: Dict[str, str] = {
    "climate": "thermostat",
    "media_player": "media-control",
}

DOMAIN_ICON: Dict[str, str] = {
    "light": "mdi:lightbulb-group",
    "switch": "mdi:toggle-switch",
    "climate": "mdi:thermostat",
    "media_player": "mdi:speaker-multiple",
    "cover": "mdi:window-shutter",
    "fan": "mdi:fan",
    "sensor": "mdi:eye",
    "binary_sensor": "mdi:checkbox-marked-circle-outline",
    "update": "mdi:package-up",
    "scene": "mdi:palette",
    "button": "mdi:gesture-tap-button",
    "vacuum": "mdi:robot-vacuum",
    "lock": "mdi:lock",
}


def atomic_write(filepath: Path, content: str) -> None:
    """Safely write content atomically using a temp file and os.replace."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(filepath.parent), prefix=f"{filepath.stem}.", suffix=".tmp")
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


def load_home_name() -> str:
    profile = Path(__file__).resolve().parent.parent / "memory" / "canonical" / "home-profile.json"
    if profile.exists():
        try:
            data = json.loads(profile.read_text(encoding="utf-8"))
            name = str(data.get("name", "")).strip()
            if name:
                return name
        except Exception:
            pass
    return "Smart Home"


def load_area_config() -> List[Dict[str, str]]:
    cfg = Path(__file__).resolve().parent.parent / "_shared" / "templates" / "dashboards" / "areas.json"
    if not cfg.exists():
        return []
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [{"id": str(a["id"]), "name": str(a.get("name", a["id"]))} for a in data if isinstance(a, dict) and "id" in a]
    except Exception:
        pass
    return []


def load_states(states_file: Path, fetch: bool) -> List[Dict[str, Any]]:
    if fetch:
        from ha_client import ha_request, load_env_token
        url, token = load_env_token()
        if not token:
            raise RuntimeError("No HASS_TOKEN found (needed for --fetch).")
        res = ha_request(url, "states", token)
        if not res.get("success"):
            raise RuntimeError(f"Failed to fetch states: {res.get('error')}")
        return res.get("data", [])
    if not states_file.exists():
        raise RuntimeError(f"State dump '{states_file}' not found. Run `ha_client.py states` or pass --fetch.")
    data = json.loads(states_file.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("data", [])
    return data if isinstance(data, list) else []


def group_by_domain(states: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for st in states:
        eid = st.get("entity_id", "")
        if "." not in eid:
            continue
        domain = eid.split(".", 1)[0]
        grouped.setdefault(domain, []).append(st)
    for domain in grouped:
        grouped[domain].sort(key=lambda s: s.get("entity_id", ""))
    return grouped


def _domain_cards(domain: str, entities: List[Dict[str, Any]]) -> str:
    card_type = DOMAIN_CARD.get(domain)
    lines: List[str] = []
    if card_type == "thermostat":
        for e in entities:
            lines.append(f"      - type: thermostat\n        entity: {e['entity_id']}")
    elif card_type == "media-control":
        for e in entities:
            lines.append(f"      - type: media-control\n        entity: {e['entity_id']}")
    else:
        lines.append("      - type: entities")
        lines.append("        show_header_toggle: false")
        lines.append("        entities:")
        for e in entities:
            lines.append(f"          - entity: {e['entity_id']}")
    return "\n".join(lines)


def generate_domain_yaml(domain: str, entities: List[Dict[str, Any]]) -> str:
    title = domain.replace("_", " ").title()
    icon = DOMAIN_ICON.get(domain, "mdi:shape")
    header = "# Auto-generated by scripts/build_dashboards.py — edit config, not output.\n"
    return (
        f"{header}title: {title}\nviews:\n"
        f"  - title: {title}\n    path: {domain}\n    icon: {icon}\n    cards:\n"
        f"{_domain_cards(domain, entities)}\n"
    )


def _area_entities(area_id: str, states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Heuristic: an entity belongs to an area when its object_id is prefixed with the area id."""
    prefix = area_id.lower().replace("-", "_")
    hits = []
    for st in states:
        eid = st.get("entity_id", "")
        obj = eid.split(".", 1)[1] if "." in eid else ""
        if obj.startswith(prefix) or f"_{prefix}_" in f"_{obj}_":
            hits.append(st)
    return hits


def generate_area_yaml(area: Dict[str, str], states: List[Dict[str, Any]]) -> str:
    title = area["name"]
    entities = _area_entities(area["id"], states)
    header = "# Auto-generated by scripts/build_dashboards.py — edit config, not output.\n"
    if not entities:
        body = (
            "      - type: markdown\n"
            f"        content: \"Noch keine Entitäten mit Präfix `{area['id']}_` erfasst.\"\n"
        )
    else:
        body = "\n".join(f"      - entity: {e['entity_id']}" for e in entities) + "\n"
        body = "      - type: entities\n        entities:\n" + body
    return (
        f"{header}title: {title}\nviews:\n"
        f"  - title: {title}\n    path: {area['id']}\n    icon: mdi:floor-plan\n    cards:\n{body}"
    )


def generate_home_yaml(home_name: str, grouped: Dict[str, List[Dict[str, Any]]]) -> str:
    header = "# Auto-generated by scripts/build_dashboards.py — edit config, not output.\n"
    top_domains = sorted(grouped.items(), key=lambda kv: -len(kv[1]))[:3]
    blocks = [
        "      - type: markdown",
        f"        content: \"# {home_name}\\\\n\\\\nGeneriert aus dem Home-Assistant-Entitätsbestand.\"",
    ]
    for domain, entities in top_domains:
        title = domain.replace("_", " ").title()
        blocks.append("      - type: entities")
        blocks.append(f"        title: {title}")
        blocks.append("        entities:")
        for e in entities[:20]:
            blocks.append(f"          - entity: {e['entity_id']}")
    return (
        f"{header}title: {home_name}\nviews:\n"
        f"  - title: Home\n    path: home\n    icon: mdi:home\n    cards:\n"
        + "\n".join(blocks) + "\n"
    )


def generate_context_md(home_name: str) -> str:
    return f"""# Smart Home Dashboards

ICM Form 6: Architektur und Konzeption der Lovelace-Dashboards für **{home_name}**.

Dieses Verzeichnis enthält **generierte** Lovelace-Konfigurationen. Quelle der Wahrheit
ist [`scripts/build_dashboards.py`](../scripts/README.md) plus die optionale
Konfiguration in [`_shared/templates/dashboards/`](../_shared/templates/).

## Struktur-Hierarchie

- `home.yaml` — Haupt-Overview.
- `areas/<area_id>.yaml` — Raum-Dashboards (sofern in `_shared/templates/dashboards/areas.json` definiert).
- `domains/<domain>.yaml` — Fach-Dashboards je Domäne.
- `lovelace_complete.yaml` — All-in-One-Konfiguration für das Deployment.

## UI-Designprinzipien

1. **Native Lovelace Cards (Vanilla First):** Keine instabilen HACS-Custom-Cards.
2. **Glance-First:** Wichtige Zustände und Aktionen mit einem Tipp erreichbar.
3. **Generiert, nicht handgepflegt:** Änderungen immer am Generator bzw. an der Config vornehmen.
4. **Operations:** System-Health spiegelt sich im Health-Dashboard und in [`pipelines/03_health-audit/`](../pipelines/03_health-audit/CONTEXT.md) wider.
"""


def generate_complete_yaml(home_name: str, grouped: Dict[str, List[Dict[str, Any]]]) -> str:
    header = "# Auto-generated by scripts/build_dashboards.py — edit config, not output.\n"
    views: List[str] = [
        f"  - title: Home\n    path: home\n    icon: mdi:home\n    cards:\n"
        f"      - type: markdown\n        content: \"# {home_name}\"\n"
    ]
    for domain, entities in grouped.items():
        title = domain.replace("_", " ").title()
        views.append(
            f"  - title: {title}\n    path: {domain}\n    icon: {DOMAIN_ICON.get(domain, 'mdi:shape')}\n    cards:\n"
            f"{_domain_cards(domain, entities)}\n"
        )
    return f"{header}title: {home_name}\nviews:\n" + "\n".join(views)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Smart Home Lovelace dashboards")
    parser.add_argument("--states", default="tmp/states.json", help="Path to cached states JSON (relative to workspace root)")
    parser.add_argument("--fetch", action="store_true", help="Fetch states live from Home Assistant (needs HASS_TOKEN)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without writing files")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON envelope")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    dashboards_dir = root_dir / "dashboards"
    areas_dir = dashboards_dir / "areas"
    domains_dir = dashboards_dir / "domains"

    try:
        home_name = load_home_name()
        states = load_states(root_dir / args.states, args.fetch)
        grouped = group_by_domain(states)
        areas = load_area_config()
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"success": False, "error": str(exc)}))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    written_files: List[str] = []
    if not args.dry_run:
        atomic_write(dashboards_dir / "CONTEXT.md", generate_context_md(home_name)); written_files.append("dashboards/CONTEXT.md")
        atomic_write(dashboards_dir / "home.yaml", generate_home_yaml(home_name, grouped)); written_files.append("dashboards/home.yaml")
        for domain, entities in grouped.items():
            atomic_write(domains_dir / f"{domain}.yaml", generate_domain_yaml(domain, entities)); written_files.append(f"dashboards/domains/{domain}.yaml")
        for area in areas:
            atomic_write(areas_dir / f"{area['id']}.yaml", generate_area_yaml(area, states)); written_files.append(f"dashboards/areas/{area['id']}.yaml")
        atomic_write(dashboards_dir / "lovelace_complete.yaml", generate_complete_yaml(home_name, grouped)); written_files.append("dashboards/lovelace_complete.yaml")

    result = {
        "success": True,
        "dry_run": args.dry_run,
        "home_name": home_name,
        "entities_count": len(states),
        "domains_count": len(grouped),
        "areas_count": len(areas),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "written_files_count": len(written_files),
        "written_files": written_files,
    }
    if args.json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status = "Dry-run completed" if args.dry_run else f"Generated {len(written_files)} dashboard files"
        print(f"{status}: {len(states)} entities, {len(grouped)} domains, {len(areas)} areas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
