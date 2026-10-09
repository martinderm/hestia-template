# hestia-template

Instanzfreie **Vorlage** für Smart-Home-Management und Orchestrierung. Sie trägt die volle
Meta-Ebene (Governance, ICM-Routing, Pipelines, Data-Zones, Toolchain) und leere,
deklarierte Instanz-Zonen, mit denen ein **neues** Zuhause auf einem **neuen Gerät**
verwaltet werden kann.

Entwickelt nach den Standards von **Agent-Architecture** und **ICM-Architect** für die Harnesses:

- **Google Antigravity** (Junction `.gemini` → `.agents`)
- **OpenCode & OpenChamber** (Config unter `.opencode/opencode.json`)
- **OpenAI Codex** (nutzt `AGENTS.md`)

## Schnellstart

1. Vorlage auf das neue Gerät kopieren/klonen.
2. `.env.example` → `.env` kopieren und ausfüllen (HA-URL/-Token, optional DIRIGERA/Sonos).
3. Onboarding starten: [`pipelines/00_home-init/CONTEXT.md`](pipelines/00_home-init/CONTEXT.md)
   (fragt Plattform/Hub, Home-Name und Basis-URL ab).
4. [`AGENTS.md`](AGENTS.md) für Verhaltens- und Sicherheitsregeln konsultieren.
5. [`CONTEXT.md`](CONTEXT.md) für das ICM-Routing konsultieren.

## Git-Modus

**Standard ist `Full-Auto`:** Der Agent validiert, committet und (bei konfiguriertem Upstream)
pusht abgeschlossene Änderungen direkt. Die Neuanlage eines Remote-Repos bleibt ein Human Gate.
Der Modus kann im Onboarding bzw. Session-Kontext auf `Review` gestellt werden.

## Verlinkte Skills

Als Junctions unter `.agents/skills/` gebunden, gepinnt in `.agents/upstream.lock.json`:

| Skill | Rolle | Quelle |
| :--- | :--- | :--- |
| `workspace-lock` | Single-Harness-/Concurrency-Schutz (optional) | <https://github.com/martinderm/workspace-lock> |
| `icm-architect` | ICM-Workspace- und System-Map-Governance | <https://github.com/RinDig/icm-architect> |
| `prompting-pro` | Strukturierte Prompt-Führung | <https://github.com/martinderm/prompting-pro> |
| `software-engineering-kit` | Software-Lifecycle-Router | <https://github.com/martinderm/software-engineering-kit> |

Normativer Standard (verlinken, nicht kopieren): **agent-architecture** —
<https://github.com/martinderm/shared-memory>

## Plattform

Standard ist **Home Assistant**, der Agent ist aber plattformoffen; die konkrete Plattform
wird im Onboarding abgefragt.

## License

Dieses Template steht unter der **MIT-Lizenz** — siehe [`LICENSE`](LICENSE).

Die gebundenen Shared Skills (`.agents/skills/`, Junctions) sind **nicht** Teil dieses
Repositories und behalten ihre eigenen Lizenzen; Details in
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).
