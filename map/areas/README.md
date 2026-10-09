# Smart Home Bereiche — map/areas

Übersicht aller physischen Räume und Zonen im Smart Home.

> **Leerer Katalog.** Nach dem Onboarding wird dieses Verzeichnis von
> `scripts/build_system_map.py` mit einer `<area_id>.md` je Raum befüllt.

| Bereich-ID | Raumname | Geräte | Entitäten | Dokumentation |
| :--- | :--- | :--- | :--- | :--- |
| *(leer)* | | | | |

## Invarianten

1. Jede Entität gehört zu genau einer primären Area.
2. Benennungsmuster: `<domain>.<area>_<funktion>`.
3. Änderungen an Raumnamen oder Entitätszuordnungen erfordern Prüfung der Automationskataloge.

## Optionale Konfiguration

Lokale Namensvarianten für Area-Präfixe können in `memory/canonical/area-aliases.json`
hinterlegt werden, z. B. `{"buero": ["office", "arbeitszimmer"]}`.
