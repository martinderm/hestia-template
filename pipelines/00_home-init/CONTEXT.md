# Pipeline: 00_home-init

Onboarding eines neuen Zuhauses auf einem neuen Gerät. Erfasst die Plattform und die
Grunddaten, bevor Geräte oder Automationen angelegt werden.

| Schritt | Verantwortung | Artefakt |
| :--- | :--- | :--- |
| `01_platform` | Plattform/Hub abfragen (z. B. Home Assistant Green/Yellow, anderes System, oder plattformneutral) | `platform.md` |
| `02_home-profile` | Name, Ort/Zeitzone und Basis-URL des Zuhauses erfassen | `memory/canonical/home-profile.json` |
| `03_credentials` | Zugangsdaten in `.env` referenzieren (nie committen) | `.env` (lokal) |
| `04_seed` | Leere Data-Zones und `map/`-Kataloge initialisieren | `map/**`, `memory/**` |
| `05_git-mode` | Git-Betriebsmodus bestätigen (Standard: `Full-Auto`) | `git_mode` in `memory/canonical/home-profile.json` |
| `06_skills` | Benötigte Skills per GitHub einbinden (Klon/Submodul/Junction unter `.agents/skills/`) | `.agents/skills/*` (gitignoriert) |

**Pflicht-Interview (Human Gate):**

1. **Welche Plattform/Hub** steuert das Zuhause? (Standard: Home Assistant; Alternativen explizit nennen)
2. **Wie heißt das Zuhause** und in welcher Zeitzone liegt es?
3. **Wie wird der Agent angebunden?** (`HASS_URL`/`HASS_TOKEN` oder plattformspezifische Werte)
4. **Welche optionalen Hubs** sind vorhanden? (z. B. IKEA DIRIGERA, Sonos)
5. **Git-Betriebsmodus:** Standard ist `Full-Auto` (direktes Validieren/Committen/Pushen bei konfiguriertem Upstream). Auf Wunsch `Review`.

**Regel:** Ohne bestätigtes Home-Profil bleibt das Onboarding offen; die Plattform ist
optional, aber die Wahl muss dokumentiert sein. Credentials werden nie in Git überführt.
Die **Neuanlage** eines Remote-Repositories/Hostings bleibt auch in `Full-Auto` ein
ausdrückliches Human Gate.
