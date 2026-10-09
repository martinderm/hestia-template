# Smart Home System Map

ICM Form 6: Kartografierung der physischen und logischen Topologie des Smart Homes.

> **Instanzzone:** Diese Kataloge sind absichtlich **leer**. Sie füllen sich beim Onboarding
> und der Geräte-Einbindung mit den Daten des konkreten Zuhauses
> (`python scripts/build_system_map.py` oder manuell).

## Struktur & Kataloge

- [`areas/`](areas/README.md): Physische Räume und Zonen.
- [`devices/`](devices/README.md): Physisches Hardware-Inventar.
- [`integrations/`](integrations/README.md): Home Assistant Integrationen und Controller (Bridges, Gateways).

## Topologie-Übersicht

| Kennzahl | Wert |
| :--- | :--- |
| **Erfasste Räume** | *(wird nach Onboarding befüllt)* |
| **Erfasste Hardware-Geräte** | *(wird nach Onboarding befüllt)* |

## Invarianten

1. **Jede Entität hat genau eine primäre Area.**
2. **Namenskonvention:** `<domain>.<area>_<funktion>` (z. B. `light.living_room_ceiling`, `binary_sensor.hallway_motion`).
3. **Change Impact:** Vor dem Umbenennen oder Entfernen einer Entität prüft der Agent gegen die Automations-Kataloge in `memory/canonical/`.
