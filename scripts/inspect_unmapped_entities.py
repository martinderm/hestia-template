#!/usr/bin/env python3
"""Inspect unmapped entities and domains."""
import json
from pathlib import Path

def main():
    states_file = Path("tmp/states.json")
    if not states_file.exists():
        print("tmp/states.json not found")
        return

    with open(states_file, "r", encoding="utf-8") as f:
        states = json.load(f)["data"]

    # Read area files
    mapped_entities = set()
    for md in Path("map/areas").glob("*.md"):
        if md.name == "README.md":
            continue
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("| `") and "` | `" in line:
                eid = line.split("`")[1]
                mapped_entities.add(eid)

    print(f"Total states: {len(states)}")
    print(f"Mapped in areas: {len(mapped_entities)}")
    unmapped = [s for s in states if s["entity_id"] not in mapped_entities]
    print(f"Unmapped entities: {len(unmapped)}")

    by_domain = {}
    for s in unmapped:
        d = s["entity_id"].split(".")[0]
        by_domain[d] = by_domain.get(d, 0) + 1

    print("\nUnmapped by domain:")
    for d, c in sorted(by_domain.items(), key=lambda x: -x[1]):
        print(f"  {d:20}: {c}")

    print("\nSample unmapped entities (first 25):")
    for s in unmapped[:25]:
        print(f"  {s['entity_id']:40} | state: {s['state']} | name: {s.get('attributes', {}).get('friendly_name')}")

if __name__ == "__main__":
    main()
