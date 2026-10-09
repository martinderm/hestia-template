# Pipeline: 00_home-init

Onboarding eines neuen Zuhauses auf einem neuen Gerät. Erfasst die Plattform und die
Grunddaten, bevor Geräte oder Automationen angelegt werden.

| Schritt | Verantwortung | Artefakt |
| :--- | :--- | :--- |
| `01_platform` | Plattform/Hub abfragen (z. B. Home Assistant Green/Yellow, anderes System, oder plattformneutral) | `platform.md` |
| `02_home-profile` | Name, Ort/Zeitzone und Basis-URL des Zuhauses erfassen | `memory/canonical/home-profile.json` |
| `03_credentials` | Zugangsdaten in `.env` referenzieren (nie committen) | `.env` (lokal) |
| `04_seed` | Leere Data-Zones und `map/`-Kataloge initialisieren | `map/**`, `memory/**` |

**Pflicht-Interview (Human Gate):**

1. **Welche Plattform/Hub** steuert das Zuhause? (Standard: Home Assistant; Alternativen explizit nennen)
2. **Wie heißt das Zuhause** und in welcher Zeitzone liegt es?
3. **Wie wird der Agent angebunden?** (`HASS_URL`/`HASS_TOKEN` oder plattformspezifische Werte)
4. **Welche optionalen Hubs** sind vorhanden? (z. B. IKEA DIRIGERA, Sonos)

**Regel:** Ohne bestätigtes Home-Profil bleibt das Onboarding offen; die Plattform ist
optional, aber die Wahl muss dokumentiert sein. Credentials werden nie in Git überführt.
