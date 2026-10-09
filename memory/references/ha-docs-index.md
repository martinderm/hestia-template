---
title: "Home Assistant Dokumentations-Index & Nachschlage-Katalog"
description: "Kuratierte Single Source of Truth fuer externe Home Assistant Dokumentationen, Spezifikationen und Syntax-Referenzen."
version: "1.0"
date: 2026-10-08
category: "reference"
---

# Home Assistant — Dokumentations-Index & Nachschlage-Katalog

Dieses Dokument dient als **Bibliothekskatalog** für den Agenten. Statt zehntausende Seiten externer Dokumentation lokal zu spiegeln, ruft der Agent bei konkreten Fragen die folgenden kanonischen URLs gezielt per Web- bzw. HTTP-Fetch ab.

---

## 1. Primäre Einstiegspunkte (Kanonische Quellen)

| Bereich | URL | Zweck |
| :--- | :--- | :--- |
| **Offizielle Nutzer-Doku** | `https://www.home-assistant.io/docs/` | Konfiguration, Grundlagen, UI, Konzepte |
| **Entwickler-Doku** | `https://developers.home-assistant.io/` | REST/WebSocket APIs, Architektur, Schemas |
| **Integrations-Verzeichnis** | `https://www.home-assistant.io/integrations/` | Gerätespezifische Optionen (Shelly, ZHA, Matter etc.) |
| **Community & Blueprints** | `https://community.home-assistant.io/` | Best Practices, Fehlerlösungen, Blueprints Exchange |
| **Home Assistant Green Hub** | `https://green.home-assistant.io/` | Hardwarespezifische Anleitungen für den HA Green |

---

## 2. Thematische Deep-Links & Trigger

### A. Automatisierungen & Skripte
*Trigger: Wenn eine neue Automation entworfen, Trigger/Conditions definiert oder Skripte geschrieben werden.*

- **Automations-Übersicht:** `https://www.home-assistant.io/docs/automation/`
- **Trigger-Typen:** `https://www.home-assistant.io/docs/automation/trigger/`  
  *(State, Numeric State, Event, Time, Template, Sun, MQTT, Zone, Geolocation)*
- **Conditions:** `https://www.home-assistant.io/docs/automation/condition/`  
  *(And/Or/Not, Numeric State, State, Template, Time, Sun, Zone)*
- **Actions:** `https://www.home-assistant.io/docs/automation/action/`  
  *(Action Calls `action:`, Choose, Repeat, Wait, Stop, Parallel)*
- **Skripte & Sequenzen:** `https://www.home-assistant.io/docs/scripts/`

### B. Templating (Jinja2 & HA-Erweiterungen)
*Trigger: Wenn dynamische Werte berechnet, Bedingungen in Templates geprüft oder Sensordaten formatiert werden.*

- **HA Templating Guide:** `https://www.home-assistant.io/docs/configuration/templating/`
- **Jinja2 Dokumentation:** `https://jinja.palletsprojects.com/en/latest/templates/`
- **Wichtige native Funktionen:**
  - `states('entity_id')` — Liefert den Status als String (sicher gegen Nicht-Verfügbarkeit).
  - `is_state('entity_id', 'on')` — Prüft Zustand boolesch.
  - `state_attr('entity_id', 'attribute')` — Liest Attribute sicher aus.
  - `has_value('entity_id')` — Prüft, ob ein Zustand nicht `unavailable` oder `unknown` ist.

### C. Blueprints
*Trigger: Wenn wiederverwendbare Vorlagen für Automationen oder Skripte erstellt werden.*

- **Blueprint-Grundlagen:** `https://www.home-assistant.io/docs/blueprint/`
- **Blueprint-Tutorial:** `https://www.home-assistant.io/docs/blueprint/tutorial/`
- **Schema & Inputs:** `https://www.home-assistant.io/docs/blueprint/schema/`

### D. APIs & Integration (Fernsteuerung vom Agenten)
*Trigger: Wenn Skripte in `scripts/ha_client.py` erweitert oder Daten via REST/WebSocket abgefragt werden.*

- **REST API Spezifikation:** `https://developers.home-assistant.io/docs/api/rest/`
  - `GET /api/states` — Alle Entitäten und deren Zustand.
  - `GET /api/states/<entity_id>` — Einzelner Entitätszustand.
  - `POST /api/services/<domain>/<service>` — Service/Action ausführen.
  - `POST /api/config/core/check_config` — Konfigurationsprüfung (Dry-Run).
- **WebSocket API:** `https://developers.home-assistant.io/docs/api/websocket/`
- **Supervisor API:** `https://developers.home-assistant.io/docs/api/supervisor/endpoints/` *(Backups, OS-Updates)*

### E. Dashboards & Lovelace
*Trigger: Wenn UI-Karten, Dashboards oder Grundrisse entworfen werden.*

- **Dashboards Übersicht:** `https://www.home-assistant.io/dashboards/`
- **Karten-Verzeichnis (Cards):** `https://www.home-assistant.io/dashboards/cards/`
  - Entities, Gauge, Tile, Thermostat, Markdown, Picture-Elements etc.

### F. Protokolle & Hardware (Home Assistant Green Ökosystem)
*Trigger: Wenn Hardware eingebunden, das Funknetzwerk auditiert oder Kanäle optimiert werden.*

- **Zigbee Home Automation (ZHA):** `https://www.home-assistant.io/integrations/zha/`
- **Matter & Thread Integration:** `https://www.home-assistant.io/integrations/matter/`
- **Connect ZBT-1 / SkyConnect Stick:** `https://connectzbt1.home-assistant.io/`
- **Shelly Integration:** `https://www.home-assistant.io/integrations/shelly/`
- **ESPHome Dokumentation:** `https://esphome.io/`

---

## 3. Kurz-Spickzettel für häufige Syntax-Muster

### Modernes Automations-Skelett (YAML ab HA 2024+)
```yaml
alias: "Flur: Licht bei Bewegung wenn dunkel"
description: "Schaltet das Flurlicht bei erkannter Bewegung ein, sofern Helligkeit unter 30 Lux"
mode: single

trigger:
  - trigger: state
    entity_id: binary_sensor.hallway_motion
    to: "on"

condition:
  - condition: numeric_state
    entity_id: sensor.hallway_illuminance
    below: 30

action:
  - action: light.turn_on
    target:
      entity_id: light.hallway_ceiling
    data:
      brightness_pct: 80
```
> *Hinweis:* In modernen HA-Versionen ersetzt der Block `action:` den älteren Begriff `service:` (beide sind rückwärtskompatibel, aber `action:` ist Standard).

### Sichere Jinja2-Template-Abfragen
```jinja2
{# Empfohlen: states() mit Fallback #}
{{ states('sensor.living_room_temperature') | float(default=20.0) }}

{# Falsch/Riskant (wirft Fehler wenn Sensor unavailable): #}
{# states.sensor.living_room_temperature.state #}

{# Sichere Attributabfrage: #}
{{ state_attr('climate.office', 'current_temperature') }}
```
