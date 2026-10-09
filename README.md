# hestia-template

Instanzfreie **Vorlage** für Smart-Home-Management und Orchestrierung. Sie trägt die volle
Meta-Ebene (Governance, ICM-Routing, Pipelines, Data-Zones, Toolchain) und leere,
deklarierte Instanz-Zonen, mit denen ein **neues** Zuhause auf einem **neuen Gerät**
verwaltet werden kann.

Entwickelt nach den Standards von **Agent-Architecture** und **ICM-Architect** für die Harnesses:

- **Google Antigravity** (optionale `.gemini`-Verlinkung: siehe [`BOOTSTRAP.md`](BOOTSTRAP.md))
- **OpenCode & OpenChamber** (Config unter `.opencode/opencode.json`)
- **OpenAI Codex** (nutzt `AGENTS.md`)

## Schnellstart

Setup und Optionen: **[`BOOTSTRAP.md`](BOOTSTRAP.md)**. Kurz:

1. Vorlage klonen/kopieren.
2. `.env.example` → `.env` und ausfüllen.
3. Onboarding: [`pipelines/00_home-init/CONTEXT.md`](pipelines/00_home-init/CONTEXT.md).
4. Verhalten: [`AGENTS.md`](AGENTS.md); Routing: [`CONTEXT.md`](CONTEXT.md).

## Git-Modus

**Standard ist `Full-Auto`:** Der Agent validiert, committet und (bei konfiguriertem Upstream)
pusht abgeschlossene Änderungen direkt. Die Neuanlage eines Remote-Repos bleibt ein Human Gate.
Der Modus kann im Onboarding bzw. Session-Kontext auf `Review` gestellt werden.

## Referenzierte Skills (nur GitHub)

Das Template liefert **keine** Skills mit (keine Kopie, keine Junction) — nur Verweise auf die
Upstream-Repositories. GitHub-URLs, Einbindung und Ziel-Versionen stehen in
[`BOOTSTRAP.md`](BOOTSTRAP.md) und `.agents/upstream.lock.json` (`source: external`).

## Plattform

Standard ist **Home Assistant**, der Agent ist aber plattformoffen; die konkrete Plattform
wird im Onboarding abgefragt.

## License

Dieses Template steht unter der **MIT-Lizenz** — siehe [`LICENSE`](LICENSE).

Die **referenzierten** Shared Skills (GitHub, `.agents/skills/`) sind **nicht** Teil dieses
Repositories und behalten ihre eigenen Lizenzen; Details in
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).
