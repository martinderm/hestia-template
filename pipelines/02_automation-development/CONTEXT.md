# Pipeline: 02_automation-development

Lifecycle zur Entwicklung, Prüfung und Bereitstellung von Home Assistant Automatisierungen.

| Schritt | Verantwortung | Artefakt |
| :--- | :--- | :--- |
| `01_spec` | Trigger, Conditions & Actions spezifizieren | `automation-spec.md` |
| `02_draft` | YAML / Blueprint im Workspace verfassen | `automation-draft.yaml` |
| `03_lint` | Syntax & Entitäts-Existenz prüfen (`scripts/lint_ha_yaml.py`) | `lint-report.json` |
| `04_deploy` | **Human Gate** → Staged Push auf das Zielsystem | `deployment-receipt.json` |

**Sicherheitsregel:** Kein Deployment ohne vorangegangenen erfolgreichen Lint-Report und ausdrückliche Freigabe.
