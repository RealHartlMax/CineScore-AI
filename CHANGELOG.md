# Changelog

All notable changes to CineScore-AI will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)


## [0.1.2d] - 2026-04-09

### Hotfix Release

Additional hotfix following the `v0.1.2c` release.

### Added

- **Windows installer integration**
  - Real Windows `.exe` installer now built by CI using Inno Setup
  - Installer asset included in releases and synchronized to `versions.json`
  - Direct checksum computation during build (no post-release API polling)

### Changed

- **Release workflow optimization**
  - Windows installer job runs in parallel after validation
  - Removed unreliable release asset polling; checksums now passed directly from build jobs
  - Metadata update now uses direct workflow outputs instead of GitHub API lookups

- **Discord notifications**
  - Release workflow sends changelog notification after GitHub release
  - Final release confirmation sent to Discord after versions.json update
  - Supports both `DISCORD_CHANGELOG_CINESCORE` and `DISCORD_RELEASE_CINESCORE` secrets


## [0.1.2c] - 2026-04-09

### Hotfix Release

Follow-up hotfix after the already committed `v0.1.2b` release.

### Added

- **Update dialog release history**
  - The update window now shows the changelog chain for all releases newer than the installed version instead of only the latest release body
  - Update checks now collect the full list of newer GitHub releases so users can review all skipped versions in one place

### Changed

- **Auto-tag workflow feedback**
  - Added a final report job that explains why the auto-tag release pipeline continued, stopped, or skipped downstream jobs
  - Workflow summaries now expose reasons such as missing marker, version mismatch, existing tag, or downstream release failure


## [0.1.2b] - 2026-04-09

### Hotfix Release

Release automation and CI hotfix for the follow-up `v0.1.2b` release candidate.

### Fixed

- **Version suffix support for hotfix tags**
  - Release and auto-tag workflows now accept tags like `v0.1.2b` in addition to separator-based suffixes
  - Updater version sorting now treats `0.1.2b` as a pre-release below stable `0.1.2`

- **Release workflow metadata sync**
  - Fixed embedded Python indentation in the `versions.json` update step
  - Release workflow can now sync changelog-derived highlights and release notes into `versions.json`

### Changed

- **Release asset clarity**
  - Runtime archive names now encode their intended platform directly
  - Release notes include an `Assets` section that explains which package belongs to Windows vs. macOS/Linux

- **CI stability**
  - Release validation tests now use the same macOS Qt layer settings as the main CI workflow
  - UI smoke tests clear the dirty flag before closing to avoid blocking confirmation dialogs in headless runners


## [0.1.2] - 2026-04-09

### Hotfix Release

CI/CD stability and test infrastructure hotfix. No application-level behavior changes.

### Fixed

- **Release workflow tag resolution**
  - Release workflow now correctly prioritizes explicit `tag_name` input over `GITHUB_REF_NAME` (which previously resolved to branch name `main` in `workflow_call` context)
  - Added automatic semver normalization: bare `0.x.y` inputs are normalized to `v0.x.y`
  - Added `TAG_PATTERN` validation that rejects non-semver tags early with a clear error message
  - Added `git ls-remote` inference fallback when an invalid tag is detected but a valid SHA is available
  - Fixed `pipefail` exit on `git ls-remote` pipeline by appending `|| true`

- **Test suite — `_ensure_media_pool_music_folder` return type**
  - Two tests in `test_resolve.py` expected a bare `folder` object but the function returns a `(folder, name)` tuple
  - Both tests now correctly unpack the tuple and assert both the folder reference and the folder name string

### Added

- **CI: `pytest-timeout` guard for Qt tests**
  - Added `pytest-timeout>=2.3` to dev dependencies
  - Configured a 30-second per-test timeout via `[tool.pytest.ini_options]` in `pyproject.toml`
  - Prevents Qt headless tests from hanging indefinitely on macOS/Windows CI runners

- **CI: macOS Qt headless stability (`QT_MAC_WANTS_LAYER`)**
  - Added `QT_MAC_WANTS_LAYER=1` environment variable to the CI test step
  - Prevents the Cocoa Metal layer initialization hang on macOS Ventura+ headless runners

## [0.1.1] - 2026-04-09

### Hotfix Release

Focused hotfix release for WAV generation reliability, workflow robustness, and UI/doc polish.

### Fixed

- **Gemini WAV generation compatibility**
  - Added automatic retry without `responseMimeType` when Gemini rejects WAV `response_mime_type` requests (HTTP 400)
  - Kept strict WAV validation active after retry (non-WAV responses are still rejected in WAV mode)

- **WAV fallback UX**
  - Added a confirmation popup when WAV generation fails with known WAV/API mismatch errors
  - Users can explicitly choose whether to retry with MP3 fallback (`Yes`/`No`)

- **Release automation marker parsing**
  - Added `hotfix:` marker support in auto-tag workflow
  - Improved version marker handling for optional `v` prefix in release tags

### Changed

- **Output organization and Resolve import structure**
  - Generated music is now grouped by project and timeline subfolders
  - Resolve Media Pool import path now mirrors this structure under `CineScore AI Music / <project> / <timeline>`

- **UI refinement**
  - Discord community button updated to icon-based style
  - Removed visual focus frame on Discord icon button

- **Documentation updates**
  - Clarified installer vs. source/developer setup paths
  - Added donation/support guidance in disclaimer with reference to funding configuration

## [0.1.0] - 2026-04-09

### Initial Release

This is the first stable release of CineScore-AI, bringing AI-powered music workflow integration with DaVinci Resolve.

### Added

- **DaVinci Resolve Integration**
  - Timeline context and marker reading from Resolve
  - 720p preview rendering with queued and direct render options
  - Automated script installation to Resolve Scripts menu
  - Support for marker-driven audio placement

- **Gemini AI Video Analysis**
  - Structured video analysis using Google Gemini models
  - Configurable analysis models and endpoints
  - Video preview rendering for context analysis
  - API key management with secure storage

- **Gemini Music Generation**
  - AI-powered music generation using Lyria model
  - Marker-guided cue generation
  - Support for vocals configuration
  - Named music lanes and crossfade support

- **User Interface**
  - Tab-based settings window (Resolve, Gemini, Gemini Music, Audio, Paths, Status)
  - Live status and log output display
  - Persistent version label showing installed version
  - Bilingual interface (English/German)

- **Audio Workflow**
  - Automated audio file placement into Resolve audio tracks
  - Optional external audio provider integration (AIMLAPI-compatible, SunoAPI)
  - Prompt-based audio generation fallback

- **Configuration & Security**
  - OS keychain integration for secure secret storage
  - Configurable output and temporary directories
  - User profiles and settings persistence
  - Application configuration management

- **Development & Testing**
  - Comprehensive pytest test suite (55 tests)
  - Multi-platform support (Windows, macOS, Linux)
  - Python 3.10+ compatibility
  - CI/CD pipeline with GitHub Actions

- **Documentation**
  - Bilingual README (English/German)
  - Ethical use disclaimer with attribution guidance
  - Setup guides for Gemini API and DaVinci Resolve
  - Troubleshooting and platform-specific guidance

- **Updates & Release Management**
  - Automatic update notification system (Windows-focused)
  - GitHub release-based version tracking
  - Runtime archive distribution (ZIP and TAR.GZ)

### Known Limitations

- In-app automatic updates currently Windows-only
- Some external audio provider integrations (SunoAPI, AIMLAPI) are still work-in-progress
- Resolve integration requires Resolve installation for production use
- Gemini API requires active billing account

### Requirements

- Python 3.10 or 3.11
- DaVinci Resolve (for production timeline integration)
- Gemini API key with billing enabled
- Internet connectivity

### Installation

See [README.md](README.md) for detailed installation instructions.

---

# Changelog (Deutsch)

Alle bemerkenswerten Änderungen an CineScore-AI werden in dieser Datei dokumentiert.

Format basierend auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)


## [0.1.2d] - 2026-04-09

### Hotfix-Release

Zusaetzlicher Hotfix nach dem `v0.1.2c`-Release.

### Hinzugefuegt

- **Windows-Installer-Integration**
  - Echter Windows-`.exe`-Installer wird jetzt von CI mit Inno Setup gebaut
  - Installer-Asset ist in Releases enthalten und wird in `versions.json` synchronisiert
  - Direkte Checksum-Berechnung waehrend des Build (kein Polling nach der Release-Veroeffentlichung)

### Geaendert

- **Release-Workflow-Optimierung**
  - Windows-Installer-Job laeuft parallel nach Validierung
  - Unzuverlaessiges Release-Asset-Polling entfernt; Checksums werden jetzt direkt von Build-Jobs uebergeben
  - Metadaten-Update nutzt jetzt direkte Workflow-Outputs statt GitHub-API-Lookups

- **Discord-Benachrichtigungen**
  - Release-Workflow sendet Changelog-Benachrichtigung nach GitHub-Release
  - Finale Release-Bestaetigung wird nach versions.json-Update zu Discord gesendet
  - Unterstuetzt `DISCORD_CHANGELOG_CINESCORE` und `DISCORD_RELEASE_CINESCORE` Secrets


## [0.1.2c] - 2026-04-09

### Hotfix-Release

Nachgelagerter Hotfix nach dem bereits commiteten `v0.1.2b`-Release.

### Hinzugefuegt

- **Release-Historie im Update-Dialog**
  - Das Update-Fenster zeigt jetzt die Changelog-Kette aller Releases an, die neuer als die installierte Version sind, statt nur den Body des neuesten Releases
  - Update-Checks sammeln jetzt die komplette Liste neuerer GitHub-Releases, damit Nutzer alle uebersprungenen Versionen gesammelt sehen koennen

### Geaendert

- **Rueckmeldung im Auto-Tag-Workflow**
  - Ein finaler Report-Job erklaert jetzt, warum die Auto-Tag-Release-Pipeline weiterlief, stoppte oder nachgelagerte Jobs uebersprungen hat
  - Workflow-Zusammenfassungen zeigen Gruende wie fehlenden Marker, Versions-Mismatch, existierenden Tag oder Fehler im nachgelagerten Release-Workflow


## [0.1.2b] - 2026-04-09

### Hotfix-Release

Release-Automation- und CI-Hotfix fuer den nachfolgenden `v0.1.2b`-Release-Kandidaten.

### Behoben

- **Versionssuffix-Unterstuetzung fuer Hotfix-Tags**
  - Release- und Auto-Tag-Workflows akzeptieren jetzt Tags wie `v0.1.2b` zusaetzlich zu Suffixen mit Trenner
  - Die Versionssortierung des Updaters behandelt `0.1.2b` als Vorabversion unterhalb des stabilen `0.1.2`

- **Release-Workflow Metadaten-Synchronisierung**
  - Einrueckungsfehler im eingebetteten Python des `versions.json`-Update-Schritts behoben
  - Der Release-Workflow kann nun Highlights und Release-Notes aus dem Changelog nach `versions.json` uebernehmen

### Geaendert

- **Klarere Release-Artefakte**
  - Die Runtime-Archivnamen tragen jetzt die Zielplattform direkt im Dateinamen
  - Die Release-Notes enthalten einen Abschnitt `Assets`, der Windows- und macOS/Linux-Pakete klar zuordnet

- **CI-Stabilitaet**
  - Die Release-Validierungstests verwenden nun dieselben macOS-Qt-Layer-Einstellungen wie der Haupt-CI-Workflow
  - UI-Smoke-Tests setzen vor dem Schliessen den Dirty-Status zurueck, um blockierende Dialoge auf Headless-Runnern zu vermeiden


## [0.1.2] - 2026-04-09

### Hotfix-Release

CI/CD-Stabilitaets- und Testinfrastruktur-Hotfix. Keine Aenderungen am Anwendungsverhalten.

### Behoben

- **Release-Workflow Tag-Aufloesung**
  - Release-Workflow priorisiert nun korrekt den expliziten `tag_name`-Input vor `GITHUB_REF_NAME` (der im `workflow_call`-Kontext zuvor den Branch-Namen `main` lieferte)
  - Automatische Semver-Normalisierung: einfache Eingaben wie `0.x.y` werden zu `v0.x.y` normalisiert
  - `TAG_PATTERN`-Validierung ergaenzt, die Nicht-Semver-Tags fruehzeitig mit klarer Fehlermeldung ablehnt
  - `git ls-remote`-Inference-Fallback hinzugefuegt fuer den Fall, dass ein ungueltiger Tag erkannt wird, aber ein gueltiger SHA vorliegt
  - `pipefail`-Abbruch in der `git ls-remote`-Pipeline durch `|| true` behoben

- **Testsuite — Rueckgabetyp `_ensure_media_pool_music_folder`**
  - Zwei Tests in `test_resolve.py` erwarteten ein reines `folder`-Objekt, die Funktion gibt jedoch ein `(folder, name)`-Tupel zurueck
  - Beide Tests entpacken das Tupel nun korrekt und pruefen sowohl die Ordnerreferenz als auch den Ordnernamen

### Hinzugefuegt

- **CI: `pytest-timeout`-Absicherung fuer Qt-Tests**
  - `pytest-timeout>=2.3` zu den Dev-Abhaengigkeiten hinzugefuegt
  - 30-Sekunden-Timeout pro Test ueber `[tool.pytest.ini_options]` in `pyproject.toml` konfiguriert
  - Verhindert, dass Qt-Headless-Tests auf macOS/Windows-CI-Runnern dauerhaft haengen bleiben

- **CI: macOS Qt-Headless-Stabilitaet (`QT_MAC_WANTS_LAYER`)**
  - Umgebungsvariable `QT_MAC_WANTS_LAYER=1` zum CI-Testschritt hinzugefuegt
  - Verhindert den Cocoa-Metal-Layer-Initialisierungs-Haenger auf macOS Ventura+ Headless-Runnern

## [0.1.1] - 2026-04-09

### Hotfix-Release

Fokussiertes Hotfix-Release fuer WAV-Generierungsstabilitaet, robusteren Workflow sowie UI-/Doku-Feinschliff.

### Behoben

- **Gemini WAV-Generierungskompatibilitaet**
  - Automatischer Retry ohne `responseMimeType`, wenn Gemini WAV-`response_mime_type` Anfragen mit HTTP 400 ablehnt
  - Strikte WAV-Pruefung bleibt auch nach Retry aktiv (Nicht-WAV wird im WAV-Modus weiterhin abgelehnt)

- **WAV-Fallback-UX**
  - Bestaetigungs-Popup hinzugefuegt, wenn WAV-Generierung bei bekannten WAV/API-Mismatch-Fehlern scheitert
  - Nutzer koennen explizit per `Ja`/`Nein` entscheiden, ob ein MP3-Fallback-Retry erfolgen soll

- **Release-Automation Marker-Parsing**
  - `hotfix:` Marker im Auto-Tag-Workflow unterstuetzt
  - Versionsmarker-Handling fuer optionales `v`-Praefix bei Release-Tags verbessert

### Geaendert

- **Ausgabe-Organisation und Resolve-Importstruktur**
  - Generierte Musik wird nun in Unterordnern nach Projekt und Timeline abgelegt
  - Resolve Media-Pool Importpfad spiegelt diese Struktur unter `CineScore AI Music / <project> / <timeline>`

- **UI-Feinschliff**
  - Discord-Community-Button auf icon-basierten Stil umgestellt
  - Sichtbarer Fokusrahmen am Discord-Icon-Button entfernt

- **Dokumentations-Updates**
  - Installer-Setup fuer Endnutzer klarer von Source/Developer-Setup abgegrenzt
  - Spenden-/Support-Hinweis im Disclaimer mit Verweis auf Funding-Konfiguration ergaenzt

## [0.1.0] - 2026-04-09

### Erstes Release

Dies ist das erste stabile Release von CineScore-AI mit KI-gestützter Musik-Workflow-Integration in DaVinci Resolve.

### Hinzugefuegt

- **DaVinci Resolve Integration**
  - Lesen von Timeline-Kontext und Markern aus Resolve
  - 720p Vorschau-Rendering mit Warteschlangen- und direkter Render-Option
  - Automatisierte Script-Installation in Resolve Scripts-Menue
  - Unterstuetzung fuer Marker-gesteuerte Audio-Platzierung

- **Gemini KI-Videoanalyse**
  - Strukturierte Videoanalyse mit Google Gemini-Modellen
  - Konfigurierbare Analysemodelle und Endpoints
  - Video-Vorschau-Rendering fuer Kontext-Analyse
  - API-Key-Verwaltung mit sicherer Speicherung

- **Gemini Musikgenerierung**
  - KI-gestuetzte Musikgenerierung mit Lyria-Modell
  - Marker-gesteuerte Cue-Generierung
  - Unterstuetzung fuer Vocals-Konfiguration
  - Benannte Musik-Lanes und Crossfade-Unterstuetzung

- **Benutzeroberfläche**
  - Tab-basierte Einstellungenfenster (Resolve, Gemini, Gemini Music, Audio, Paths, Status)
  - Live-Status- und Protokoll-Ausgabeanzeige
  - Persistente Versions-Anzeige mit installierter Version
  - Zweisprachige Oberflaeche (Englisch/Deutsch)

- **Audio-Workflow**
  - Automatisierte Audio-Datei-Platzierung in Resolve-Audiospuren
  - Optionale externe Audio-Provider-Integration (AIMLAPI-kompatibel, SunoAPI)
  - Prompt-basierte Audio-Generierung als Fallback

- **Konfiguration & Sicherheit**
  - OS-Keychain-Integration fuer sichere Secret-Speicherung
  - Konfigurierbare Ausgabe- und temporaere Verzeichnisse
  - Benutzerprofil und Settings-Persistierung
  - Anwendungs-Konfigurationsverwaltung

- **Entwicklung & Tests**
  - Umfassendes pytest Test-Suite (55 Tests)
  - Plattformuebergreifende Unterstuetzung (Windows, macOS, Linux)
  - Python 3.10+ Kompatibilitaet
  - CI/CD-Pipeline mit GitHub Actions

- **Dokumentation**
  - Zweisprachiges README (Englisch/Deutsch)
  - Ethische Verwendungs-Disclaimer mit Attribution-Anleitung
  - Setup-Anleitungen fuer Gemini API und DaVinci Resolve
  - Troubleshooting und plattformspezifische Anleitungen

- **Updates & Release-Management**
  - Automatisches Update-Benachrichtigungssystem (hauptsaechlich Windows)
  - GitHub-Release-basierte Versions-Verfolgung
  - Runtime-Archive-Verteilung (ZIP und TAR.GZ)

### Bekannte Einschraenkungen

- In-App automatische Updates derzeit nur Windows
- Einige externe Audio-Provider-Integrationen (SunoAPI, AIMLAPI) sind noch Work-in-Progress
- Resolve-Integration erfordert Resolve-Installation fuer produktive Nutzung
- Gemini API erfordert aktives Abrechnungskonto

### Voraussetzungen

- Python 3.10 oder 3.11
- DaVinci Resolve (fuer produktive Timeline-Integration)
- Gemini API-Key mit aktivier Abrechnung
- Internetzugang

### Installation

Siehe [README.md](README.md) fuer detaillierte Installationsanleitungen.
