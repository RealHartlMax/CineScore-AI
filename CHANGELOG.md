# Changelog

All notable changes to CineScore-AI will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

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

---

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
