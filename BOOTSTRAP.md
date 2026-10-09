# BOOTSTRAP.md — Initialisierung dieses Template-Workspaces

Anleitung, um dieses Template auf einer **neuen Maschine** in Betrieb zu nehmen.
Danach gilt [`AGENTS.md`](AGENTS.md) (Verhalten) und [`CONTEXT.md`](CONTEXT.md) (ICM-Routing).

## 1. Basis-Setup

1. Vorlage klonen/kopieren.
2. `.env.example` → `.env` kopieren und ausfüllen (Home Assistant; optional DIRIGERA/Sonos).
3. Onboarding starten: [`pipelines/00_home-init/CONTEXT.md`](pipelines/00_home-init/CONTEXT.md)
   (Plattform, Home-Profil, Zugangsdaten, Git-Modus bestätigen).
4. Git-Modus: Standard `Full-Auto` (siehe `AGENTS.md`); auf Wunsch `Review`.

## 2. Referenzierte Skills einbinden (GitHub)

Dieses Template liefert **keine** Skills mit (keine Kopie, keine Junction) — nur Verweise.
Bei Bedarf unter `.agents/skills/` einbinden; das Verzeichnis ist bereits gitignoriert.
`opencode.json` enthält dafür schon `"skills": [".agents/skills"]`.

| Skill | Zweck | GitHub |
| :--- | :--- | :--- |
| workspace-lock | Single-Harness-/Concurrency-Schutz (optional) | <https://github.com/martinderm/workspace-lock> |
| icm-architect | ICM-Workspace-/System-Map-Governance | <https://github.com/RinDig/icm-architect> |
| prompting-pro | Strukturierte Prompt-Führung | <https://github.com/martinderm/prompting-pro> |
| software-engineering-kit | Software-Lifecycle-Router | <https://github.com/martinderm/software-engineering-kit> |

Ziel-Versionen sind in `.agents/upstream.lock.json` (`source: external`) gepinnt.

**Beispiel — Windows (Junction):**

```powershell
git clone https://github.com/martinderm/workspace-lock <shared>/workspace-lock
New-Item -ItemType Junction -Path .agents\skills\workspace-lock -Target <shared>\workspace-lock
```

**Beispiel — Linux/macOS (Symlink):**

```bash
git clone https://github.com/martinderm/workspace-lock ../skills/workspace-lock
ln -s ../../skills/workspace-lock .agents/skills/workspace-lock
```

## 3. Harness-Verlinkung (optional, empfohlen)

Die meisten Harnesses lesen `AGENTS.md` direkt. Manche erwarten zusätzlich ein
Konventionsverzeichnis. Eine solche Verlinkung ist **sinnvoll, aber optional** — und bewusst
**nicht** im Repo enthalten.

- **Antigravity:** `.gemini/` → `.agents/`

```powershell
# Windows
New-Item -ItemType Junction -Path .gemini -Target .agents
```

```bash
# Linux/macOS
ln -s .agents .gemini
```

Solche Links sind rein additive Harness-Sichten, kein Skill-Bundling, und bleiben gitignoriert
(`.gemini`, `.agents/skills`).

## 4. Verifikation

- **Conformance:** `python <Shared-Memory>/agent-architecture/scripts/lint_workspace.py --workspace . --strict --json` → `0 errors / 0 warnings / 0 info`.
- **Upstreams:** `python <Shared-Memory>/agent-architecture/scripts/upstream_lock.py check --workspace . --json` → `drift_detected: false`.

## 5. Normativer Standard

`agent-architecture` wird nur verlinkt, nie kopiert: <https://github.com/martinderm/shared-memory>
