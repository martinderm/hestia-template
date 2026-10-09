# Smart Home Dashboards

ICM Form 6: Architektur und Konzeption der Lovelace-Dashboards.

> **Generiertes Verzeichnis.** Die YAML-Dateien werden von
> [`scripts/build_dashboards.py`](../scripts/build_dashboards.py) erzeugt. Quelle der Wahrheit
> sind der Generator und die optionale Konfiguration in
> [`_shared/templates/dashboards/`](../_shared/templates/).

## Struktur-Hierarchie

- `home.yaml` — Haupt-Overview.
- `areas/<area_id>.yaml` — Raum-Dashboards (sofern `areas.json` Räume definiert).
- `domains/<domain>.yaml` — Fach-Dashboards je Domäne.
- `lovelace_complete.yaml` — All-in-One-Konfiguration für das Deployment.

## UI-Designprinzipien

1. **Native Lovelace Cards (Vanilla First):** Keine instabilen HACS-Custom-Cards.
2. **Glance-First:** Wichtige Zustände und Aktionen mit einem Tipp erreichbar.
3. **Generiert, nicht handgepflegt:** Änderungen am Generator bzw. der Config vornehmen.
4. **Operations:** System-Health spiegelt sich im Health-Dashboard und in
   [`pipelines/03_health-audit/`](../pipelines/03_health-audit/CONTEXT.md) wider.
