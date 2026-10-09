# Script-Toolchain

Kanonische Übersicht aller operativen Python-Werkzeuge im Workspace [`hestia-template`](../CONTEXT.md).

---

## 1. Architektur- & Designprinzipien

Alle Skripte in `scripts/` folgen strikt den Smart-Home-Governance- und Authoring-Standards:

- **Python-first (Zero Dependencies):** Ausschließlich Python 3 Standardbibliothek (`urllib`, `json`, `socket`, `ssl`, `xml.etree`, `argparse`). Keine externen Pip-Pakete erforderlich.
- **Cross-Platform:** Pfadbehandlung via `pathlib.Path`, plattformunabhängige Socket- & HTTP-Kommunikation.
- **Structured CLI Envelope:** Alle Abfrage- und Ausführungsskripte unterstützen das Flag `--json`.
- **Dry-Run by Default:** Zustandsändernde Operationen laufen standardmäßig im sicheren Lesemodus. Mutationen erfordern das explizite Flag `--execute`.
- **Fail-Closed & Safe Credentials:** API-Tokens verbleiben strikt in `.env` und werden dynamisch geladen.
- **Keine Instanzdaten im Code:** Keine hartcodierten Räume, Geräte, IP-Adressen oder Zähler eines konkreten Zuhauses.

---

## 2. Authentifizierung & Konfiguration (`.env`)

Die Skripte greifen auf folgende Umgebungsvariablen in `.env` (Workspace-Root) zu. Vorlage: [`.env.example`](../.env.example).

| Variable | Beschreibung | Standard | Verwendet von |
| :--- | :--- | :--- | :--- |
| `HASS_URL` | Basis-URL des Home Assistant | `http://homeassistant.local:8123` | `ha_client.py`, `build_system_map.py`, `deploy_dashboard.py`, `run_health_audit.py` |
| `HASS_TOKEN` | Long-Lived Access Token für HA REST- & WebSocket-API | *(Secret)* | Alle HA-Clients |
| `DIRIGERA_IP` | Lokale IP des IKEA DIRIGERA Hubs | *(leer)* | `dirigera_client.py` |
| `DIRIGERA_TOKEN` | OAuth2 Bearer Token des DIRIGERA Hubs | *(Secret)* | `dirigera_client.py` |
| `SONOS_IPS` | Kommaseparierte Sonos-Player-IPs | *(leer)* | `sonos_client.py` (sonst SSDP-Discovery) |

---

## 3. Skript-Katalog

### A. Home Assistant Core & REST

#### [`ha_client.py`](ha_client.py)
Universeller REST-Client für Home Assistant.
- `status` — API-Erreichbarkeit und Core-Status prüfen.
- `states` — Entitäten und Zustände abfragen (optional `--filter-domain light`).
- `call-service` — Dienste ausführen (benötigt `--execute`).
- `config` / `template` — Konfiguration bzw. Jinja2-Template rendern.
- Beispiel: `python scripts/ha_client.py states --filter-domain climate --json`

#### [`lint_ha_yaml.py`](lint_ha_yaml.py)
Validiert Home Assistant YAML (Automationen, Skripte, Szenen) vor dem Staging auf Syntax- und Strukturfehler.
- Beispiel: `python scripts/lint_ha_yaml.py --file pipelines/02_automation-development/staging/automation.yaml --json`

#### [`inspect_unmapped_entities.py`](inspect_unmapped_entities.py)
Analysiert Entitäten, die keinem Raum in `map/areas/` zugeordnet sind.
- Beispiel: `python scripts/inspect_unmapped_entities.py`

---

### B. Hardware-Hubs & Integrationen

#### [`dirigera_client.py`](dirigera_client.py)
Direkte Kommunikation mit dem IKEA DIRIGERA Hub via lokaler REST/HTTPS-API (Port 8443, Self-Signed SSL).
- `pair` — Startet den OAuth2-PKCE-Pairing-Flow (`--ip <hub-ip>`, physische Taste am Hub).
- `status` — Hub-Firmware, Online-Status und Systemdaten.
- `devices` — Listet Geräte (`--filter-type light`).
- `dump` — Exportiert den kompletten Gerätekatalog als JSON.
- Beispiel: `python scripts/dirigera_client.py status --json`

#### [`sonos_client.py`](sonos_client.py)
Lokale Diagnose des Multiroom-Audiosystems via UPnP SOAP auf Port 1400 (ohne Cloud).
- `topology` — Zonen, Koordinatoren und Stereopaare.
- `players` — Lautsprecher mit IP, MAC, Hardware-Generation und Firmware.
- Ziel-IPs: `--ip` (wiederholbar), `SONOS_IPS`, sonst SSDP-Discovery.
- Beispiel: `python scripts/sonos_client.py topology --json`

---

### C. System Map & ICM-Synchronisation

#### [`build_system_map.py`](build_system_map.py)
Generiert die kanonische Smart-Home-Topologie (ICM Form 6) aus der Home-Assistant-API:
- Raum-Dokumente in [`map/areas/`](../map/areas/README.md), Hardware-Inventar in [`map/devices/`](../map/devices/README.md), Indexe und `map/CONTEXT.md`.
- Lokale Namensvarianten von Areas lassen sich optional in `memory/canonical/area-aliases.json` hinterlegen.
- Beispiel: `python scripts/build_system_map.py --dry-run --json`

---

### D. Lovelace Dashboards & UI

#### [`build_dashboards.py`](build_dashboards.py)
Generischer Lovelace-Generator auf Basis eines State-Dumps (`tmp/states.json` oder `--fetch`):
- `dashboards/home.yaml`, `dashboards/domains/<domain>.yaml`, optional `dashboards/areas/<area_id>.yaml`, `dashboards/lovelace_complete.yaml`.
- Home-Name aus `memory/canonical/home-profile.json`; Raumliste optional aus `_shared/templates/dashboards/areas.json`.
- Beispiel: `python scripts/build_dashboards.py --states tmp/states.json --dry-run`

#### [`deploy_dashboard.py`](deploy_dashboard.py)
Deployt eine generierte Lovelace-Konfiguration via WebSocket API (`lovelace/config/save`). Standardmäßig Dry-Run.
- Beispiel: `python scripts/deploy_dashboard.py --url-path smart-home --title "Smart Home" --dry-run`

---

### E. Health- & Operations-Audits

#### [`run_health_audit.py`](run_health_audit.py)
Führt die 4-stufige Health-Audit-Pipeline aus ([`pipelines/03_health-audit/`](../pipelines/03_health-audit/CONTEXT.md)):
1. `01_backup` — Backup-Status (`backup-health.json`).
2. `02_mesh` — Signalstärken (LQI/RSSI) und Batterien (`mesh-topology.json`).
3. `03_logs` — Verfügbarkeit, Core- und Add-on-Updates (`log-findings.md`).
4. `04_report` — Markdown-Bericht in `memory/operations/health-audit-<datum>.md`.
- Beispiel: `python scripts/run_health_audit.py --dry-run --json`

---

## 4. Best Practices für Agenten & Entwickler

1. **Locking optional:** Vor schreibenden Läufen in Multi-Harness-Szenarien den Skill `workspace-lock` verwenden (siehe [`AGENTS.md`](../AGENTS.md)).
2. **Review-First:** Vor Deployments immer den `--dry-run`-Output prüfen.
3. **Keine Secrets committen:** Niemals Token-Werte hardcoden; immer `.env` nutzen.
4. **Keine Instanzdaten hardcoden:** Räume, Geräte und Netzadressen gehören in `memory/canonical/` bzw. `.env`, nicht in Skripte.
