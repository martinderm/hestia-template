# Pipeline: 01_device-onboarding

Strukturierter Ablauf zur Einbindung neuer Hardware in das Smart Home.

| Schritt | Verantwortung | Artefakt |
| :--- | :--- | :--- |
| `01_discovery` | Gerät pairen / Netzwerk-Identifikation | `discovered-device.json` |
| `02_naming` | Namenskonvention & Area-Zuweisung prüfen | `entity-mapping.md` |
| `03_dashboard` | Lovelace Card & Default-Automationen entwerfen | `lovelace-card.yaml` |
| `04_register` | In System Map [`map/`](../../map/CONTEXT.md) eintragen | `map/devices/<device-id>.md` |

**Human Gate:** Das Pairing und die finale Übernahme in die System Map erfordern menschliche Bestätigung.

**Voraussetzung:** Abgeschlossenes Onboarding ([`00_home-init/`](../00_home-init/CONTEXT.md)).
