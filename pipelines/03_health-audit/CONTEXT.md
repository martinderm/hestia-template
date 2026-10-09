# Pipeline: 03_health-audit

Regelmäßige Integritäts- und Sicherheitsprüfungen des Smart Homes.

| Schritt | Verantwortung | Artefakt |
| :--- | :--- | :--- |
| `01_backup` | Letzten Backup-Status prüfen | `backup-health.json` |
| `02_mesh` | Zigbee/Thread Signalstärke (LQI / RSSI) abrufen | `mesh-topology.json` |
| `03_logs` | Core & Add-on Error-Logs analysieren | `log-findings.md` |
| `04_report` | Audit-Bericht in `memory/operations/` archivieren | `memory/operations/health-audit-<date>.md` |

**Berechtigung:** Rein lesende Prüfungen; darf vollautomatisiert ablaufen.
