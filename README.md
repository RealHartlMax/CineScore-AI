# CineScore-AI

English and German documentation in one file.

- [English](#english)
- [Deutsch](#deutsch)

---

## English

AI-powered music workflow for DaVinci Resolve: from timeline markers and video analysis to automatically placed music tracks.

### What is CineScore-AI?

CineScore-AI is a Python desktop application for DaVinci Resolve.
It combines three steps into one workflow:

1. Read timeline context and markers from Resolve
2. Run Gemini analysis on a rendered preview
3. Generate marker-guided music and place it back into Resolve

You can run it directly inside Resolve or in development mode without Resolve.

### Important: Read the Disclaimer

Before using CineScore-AI, please read the [DISCLAIMER.md](DISCLAIMER.md). This tool is designed to complement creative professionals, not replace them. Learn about responsible use, best practices, and ethical considerations.

### Core Features

- 720p preview rendering (queued or direct render with completion wait)
- Structured Gemini video analysis based on the latest preview
- Marker-driven Gemini music generation (Lyria 3)
- Cue splitting by named music lanes and crossfades
- Optional audio provider integration (AIMLAPI-compatible, SunoAPI)
- Placement of generated audio files into Resolve audio tracks
- Localization (German/English) and secure secret handling (OS keychain when available)
- Tab-based UI for a cleaner workflow

### UI Overview

The settings window is split into tabs:

- Resolve: load context, render preview, inspect markers
- Gemini: endpoint, analysis model, API key, video analysis
- Gemini Music: Lyria model, vocals, marker options, cue generation
- Audio: external audio providers and prompt-based generation
- Paths: output and temp directories
- Status: live status and log output

### Requirements

- Python 3.10 or 3.11
- DaVinci Resolve (for production timeline integration)
- Internet access for Gemini and optional audio providers
- Gemini API key
- Optional: AIMLAPI or SunoAPI key

Recommended right now: use the Gemini API path for production workflows.
Other external audio provider API integrations are still work in progress and not fully validated yet.

### Gemini API Key and Billing Setup

You can create the Gemini API key at https://aistudio.google.com.

Typical setup flow:

1. Open AI Studio and sign in with your Google account.
2. Create or select a Google Cloud project.
3. Enable billing for that project (for this CineScore workflow, assume a billing account is required).
4. Create an API key in AI Studio.
5. Paste the key into the Gemini API key field in CineScore AI and click `Test Gemini`.

Notes:

- Keep your key private and never post it in issues or logs.
- Use usage limits/quotas in Google Cloud to avoid unexpected costs.

### Installation

#### For End Users

Download the latest release and use the provided installer:

1. Download `CineScore-AI-Setup.exe` from the latest GitHub release
2. Run the installer — it handles all setup automatically, including the Resolve script entry

No cloning or Python required.

#### For Developers

Cloning is required for development from source:

1. Clone the repository

```bash
git clone https://github.com/<your-org>/CineScore-AI.git
cd CineScore-AI
```

2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### Running the App

Development mode (without Resolve):

```bash
python scripts/dev_entry.py
```

Resolve runtime (inside DaVinci Resolve):

```python
exec(open("<path-to-project>/scripts/resolve_entry.py", encoding="utf-8").read())
```

Important: the Resolve startup script expects the global `resolve` object that only exists inside Resolve.

### Resolve Script Setup (for developers running from source)

If you cloned from source and want to use the app with Resolve, run the installer script:

```powershell
python scripts/install_resolve_runtime.py
```

What this does:

1. Copies runtime files to `%APPDATA%/CineScore-AI/resolve-runtime`
2. Writes exactly one launcher script to Resolve:
	 `%APPDATA%/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility/CineScore AI.py`
3. Resolve shows only `CineScore AI` in the Scripts menu

Optional arguments:

```powershell
python scripts/install_resolve_runtime.py --install-root "D:\Apps\CineScore-AI-runtime"
python scripts/install_resolve_runtime.py --launcher-path "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\CineScore AI.py"
```

### Update Notification and In-App Update

When a newer GitHub release is available, CineScore AI shows a popup at startup with:

1. installed version
2. latest version
3. release changelog

On Windows, the app can start an automatic update:

1. Click `Update now`
2. DaVinci Resolve is closed automatically
3. Runtime under `%APPDATA%/CineScore-AI/resolve-runtime` is updated
4. After update, the helper asks whether Resolve should be reopened

Important:

- Save your current Resolve project before updating
- Automatic in-app update is currently Windows-only
- You can also run a manual check with `Check for updates`

### Automatic Tags and Releases

The release flow can create tags automatically when a commit message on the default branch contains an explicit release marker.

Supported markers:

- `release: v0.2.0`
- `version: 0.2.0`
- `hotfix: 0.1.2c`

Important:

- Commit message version must match [src/cinescore_ai/version.py](src/cinescore_ai/version.py)
- Auto-tag flow creates `v0.2.0` and invokes the release workflow directly
- Markers are explicit by design to avoid accidental releases

#### Recommended Release Commit Schema

1. Bump version in [src/cinescore_ai/version.py](src/cinescore_ai/version.py), for example to `0.2.0`.
2. Commit with an explicit marker line, for example:

```text
feat: improve updater fallback and release docs

release: v0.2.0
```

Alternative:

```text
chore: prepare release notes

version: 0.2.0
```

Hotfix example:

```text
fix: correct updater edge case

hotfix: 0.1.2c
```

3. Push to the default branch.
4. Workflow creates `v0.2.0` and starts the release pipeline.

Notes:

- If commit version and app version differ, workflow fails intentionally.
- If tag already exists, no duplicate release is generated.

#### Platform Suitability

- CI runs on Linux, Windows, and macOS with Python 3.10 and 3.11.
- Release artifacts are source/runtime archives (ZIP + TAR.GZ), usable across platforms.
- In-app updater automation is still Windows-only.

### Recommended Workflow

1. Resolve tab: refresh context
2. Resolve tab: render 720p preview
3. Gemini tab: analyze latest preview
4. Gemini Music tab: generate cue-based music from markers
5. Optional Audio tab: generate alternatives with external providers

### Marker Directives for Music Control

Directives can be provided in marker name, marker note, or marker keywords.

Named lane format example:

```text
Music Track 1: Farmer John Theme
```

Typical directives:

```text
image=yes
lyrics=yes
fade=3.5
length=20
track=main
theme=Reveal Theme
keywords=cinematic, orchestral, tense
Genre = Western, Scifi
Instruments = Banjo, Synth Pad
BPM = 85
Key = D minor
Mood = nostalgic, eerie
Song_Structure = Intro, Verse, Chorus
Input = A gentle banjo motif that accelerates over time
[Stop]
```

Notes:

- `image=yes`: include marker images as visual prompt context
- `lyrics=yes`: force vocals for this cue
- `fade`: preferred crossfade length
- `length`: target cue duration (optional explicit override via marker note/keywords)
- Marker `Duration` field in Resolve (Marker dialog) is also considered as cue length for Lyria 3 Pro, so duration can be set without free text
- `track`: numeric or named lane (`main`, `alt`, and so on)
- `Genre`, `Instruments`, `BPM`, `Key`, `Mood`, `Song_Structure`: structured prompt fields
- `Input`: free text per marker, used with marker timing
- `[Stop]`: natural ending exactly at marker timestamp
- `[StopHard]`: abrupt hard cut exactly at marker timestamp

JSON-ready prompt structure example:

```json
{
	"cue": {
		"index": 1,
		"count": 2,
		"start_seconds": 0.0,
		"target_duration_seconds": 4.0,
		"track_slot": 1,
		"track_lane": "Track 1",
		"genres": ["Western", "Scifi"],
		"instruments": ["Banjo", "Synth Pad"],
		"bpm": 85,
		"key_scale": "D minor",
		"mood": ["nostalgic", "eerie"],
		"structure": ["Intro", "Verse", "Chorus"],
		"vocals_mode": "instrumental"
	},
	"marker_inputs": [
		{
			"timestamp": "00:00:00.000",
			"genre": ["Western", "Scifi"],
			"input": "A gentle banjo motif that accelerates over time",
			"stop": false
		},
		{
			"timestamp": "00:00:04.000",
			"genre": [],
			"input": "Immediate stop without tail",
			"stop": true
		}
	]
}
```

### Models and Output Formats

- Lyria 3 Pro: `lyria-3-pro-preview`
- Lyria 3 Clip: `lyria-3-clip-preview`
- WAV output is only supported by Lyria 3 Pro (according to API docs)
- MP3 is the default path for both models
- If WAV is requested, CineScore now enforces it strictly and fails the generation if the API returns a non-WAV response
- WAV output requests target 48 kHz and >=24-bit (preferably 32-bit) and is validated after writing

### Configuration and Paths

Config file:

- Windows: `AppData/Roaming/CineScore-AI/config.json`
- macOS: `Library/Application Support/CineScore-AI/config.json`
- Linux: `~/.config/CineScore-AI/config.json`

Default directories:

- Output: `Music/CineScore AI/<project>/<timeline>`
- Temp/Preview: local CineScore-AI cache directory

Generated music is grouped into project and timeline subfolders. The same structure is also used for the Resolve MediaPool import under `CineScore AI Music / <project> / <timeline>`.

### Tests

Run all tests:

```bash
pytest
```

Resolve installer tests:

```bash
pytest tests/test_resolve_install.py
```

Selected areas:

```bash
pytest tests/test_resolve.py
pytest tests/test_gemini_music.py
pytest tests/test_ui_smoke.py
```

### Troubleshooting

Preview render rejected by Resolve:

Fallback render profiles are used (including alternate resolution keys) to improve compatibility across Resolve versions.

WAV not imported or MediaInfo shows MPEG inside `.wav`:

With strict WAV mode, CineScore aborts generation if the API returns non-WAV audio. If this happens, select MP3 output as a practical fallback and rerun.

`URL can't contain control characters` during `generateContent`:

This usually indicates a non-normalized model name. Current versions normalize display names to API model IDs.

No connection to Gemini or audio provider:

- verify API key
- verify endpoint URL
- check timeout, proxy, or firewall
- use the provider test button in the UI first

### Project Structure (short)

```text
scripts/
	dev_entry.py          # Start without Resolve (mock)
	resolve_entry.py      # Start inside Resolve runtime
src/cinescore_ai/
	app.py                # App bootstrap
	ui/main_window.py     # Main window and tabs
	resolve.py            # Resolve adapters (real/mock)
	workflow.py           # Preview render workflow
	gemini.py             # Gemini video analysis
	gemini_music.py       # Cue-based music generation
	audio.py              # External audio provider workflow
	marker_directives.py  # Marker directive parsing
	config.py             # Settings load/save
tests/
	...                   # Unit and smoke tests
```

### Security and Privacy

- API keys are managed through a secret-store abstraction
- OS keychain is used when available
- Without persistent keychain support, secrets are session-only

---

## Deutsch

KI-gestuetzter Musik-Workflow fuer DaVinci Resolve: von Timeline-Markern ueber Videoanalyse bis zur automatisch platzierten Musikspur.

### Was ist CineScore-AI?

CineScore-AI ist ein Python-basiertes Desktop-Tool fuer DaVinci Resolve.
Es verbindet drei Schritte zu einem durchgaengigen Ablauf:

1. Timeline-Kontext und Marker aus Resolve lesen
2. Gemini-Analyse auf einem Vorschau-Render ausfuehren
3. Marker-gesteuerte Musik generieren und in Resolve platzieren

Das Projekt kann direkt in Resolve laufen oder im Development Mode ohne Resolve getestet werden.

### Wichtig: Disclaimer lesen

Bitte lies vor der Nutzung von CineScore-AI den [DISCLAIMER.md](DISCLAIMER.md). Dieses Tool ist dafür gedacht, kreative Profis zu ergänzen, nicht zu ersetzen. Erfahre mehr über verantwortungsvollen Einsatz, Best Practices und ethische Überlegungen.

### Kernfunktionen

- 720p Vorschau-Render (Queue oder direktes Rendern mit Warten auf Abschluss)
- Strukturierte Gemini-Videoanalyse auf Basis des letzten Preview-Renders
- Marker-gesteuerte Gemini-Musikgenerierung (Lyria 3)
- Cue-Aufteilung ueber benannte Musik-Lanes und Crossfades
- Optionale Audio-Provider-Integration (AIMLAPI-kompatibel, SunoAPI)
- Rueckplatzierung erzeugter Audiodateien auf Resolve-Audiospuren
- Lokalisierung (Deutsch/Englisch) und sichere Secret-Verwaltung (OS-Keychain, falls verfuegbar)
- Tab-basierte UI fuer einen klaren Workflow

### UI-Ueberblick

Die Einstellungen sind in Reiter aufgeteilt:

- Resolve: Kontext laden, Preview rendern, Marker ansehen
- Gemini: Endpoint, Analysemodell, API-Key, Videoanalyse
- Gemini Music: Lyria-Modell, Vocals, Marker-Optionen, Cue-Generierung
- Audio: externe Audio-Provider und Prompt-basierte Generierung
- Paths: Ausgabe- und Temp-Verzeichnisse
- Status: laufende Meldungen und Verlauf

### Voraussetzungen

- Python 3.10 oder 3.11
- DaVinci Resolve (fuer produktive Timeline-Integration)
- Internetzugang fuer Gemini und optionale Audio-Provider
- Gemini API-Key
- Optional: AIMLAPI- oder SunoAPI-Key

Aktuell empfohlen: nutze fuer produktive Workflows den Weg ueber die Gemini-API.
Andere externe Audio-Provider-API-Schnittstellen sind noch Work in Progress und bisher nicht vollstaendig validiert.

### Gemini API-Key und Abrechnung einrichten

Den Gemini API-Key erstellst du unter https://aistudio.google.com.

Typischer Ablauf:

1. AI Studio oeffnen und mit dem Google-Konto anmelden.
2. Ein Google-Cloud-Projekt auswaehlen oder neu erstellen.
3. Fuer dieses Projekt Abrechnung aktivieren (fuer diesen CineScore-Workflow ist ein Abrechnungskonto einzuplanen).
4. API-Key in AI Studio erzeugen.
5. Den Key in CineScore AI im Gemini-API-Key-Feld eintragen und `Test Gemini` ausfuehren.

Hinweise:

- API-Key privat halten und nie in Issues oder Logs posten.
- In Google Cloud Kontingente/Limits setzen, um unerwartete Kosten zu vermeiden.

### Installation

#### Fuer Endnutzer

Lade das aktuelle Release herunter und nutze den mitgelieferten Installer:

1. `CineScore-AI-Setup.exe` aus dem letzten GitHub-Release herunterladen
2. Installer ausfuehren — alles wird automatisch eingerichtet, inklusive des Resolve-Script-Eintrags

Klonen und Python sind nicht erforderlich.

#### Fuer Entwickler

Klonen ist nur fuer Entwicklung aus dem Quellcode noetig:

1. Repository klonen

```bash
git clone https://github.com/<your-org>/CineScore-AI.git
cd CineScore-AI
```

2. Virtuelle Umgebung anlegen und aktivieren

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Abhaengigkeiten installieren

```bash
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### Starten

Development Mode (ohne Resolve):

```bash
python scripts/dev_entry.py
```

Resolve Runtime (in DaVinci Resolve):

```python
exec(open("<pfad-zum-projekt>/scripts/resolve_entry.py", encoding="utf-8").read())
```

Wichtig: Der Resolve-Startskript erwartet das globale `resolve`-Objekt, das nur in Resolve verfuegbar ist.

### Resolve-Script-Einrichtung (Fuer Entwickler aus dem Quellcode)

Wenn Du aus dem Repository kloniert hast und die App mit Resolve nutzen willst, fuehre das Installer-Skript aus:

```powershell
python scripts/install_resolve_runtime.py
```

Das Skript macht Folgendes:

1. Kopiert Runtime-Dateien nach `%APPDATA%/CineScore-AI/resolve-runtime`
2. Schreibt genau eine sichtbare Launcher-Datei nach Resolve:
	 `%APPDATA%/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility/CineScore AI.py`
3. Resolve zeigt danach nur `CineScore AI` im Scripts-Menue an

Optionale Parameter:

```powershell
python scripts/install_resolve_runtime.py --install-root "D:\Apps\CineScore-AI-runtime"
python scripts/install_resolve_runtime.py --launcher-path "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\CineScore AI.py"
```

### Update-Benachrichtigung und In-App-Update

Wenn eine neuere GitHub-Release-Version verfuegbar ist, zeigt CineScore AI beim Start ein Popup mit:

1. installierter Version
2. neuer Version
3. Changelog der Release

Unter Windows kann die App das Update direkt anstossen:

1. Auf `Update now` klicken
2. DaVinci Resolve wird automatisch geschlossen
3. Runtime unter `%APPDATA%/CineScore-AI/resolve-runtime` wird aktualisiert
4. Nach Abschluss fragt der Helfer, ob Resolve wieder gestartet werden soll

Wichtig:

- Vor dem Update das aktuelle Resolve-Projekt speichern
- Automatische In-App-Updates sind aktuell nur unter Windows verfuegbar
- Im Hauptfenster gibt es zusaetzlich den Button `Check for updates`

### Automatische Tags und Releases

Der Release-Flow kann automatisch Tags erzeugen, wenn die Commit-Nachricht auf dem Default-Branch eine explizite Versionsmarkierung enthaelt.

Unterstuetzte Marker:

- `release: v0.2.0`
- `version: 0.2.0`
- `hotfix: 0.1.2c`

Wichtig:

- Die Commit-Version muss zu [src/cinescore_ai/version.py](src/cinescore_ai/version.py) passen
- Der Auto-Tag-Flow erzeugt `v0.2.0` und ruft den Release-Workflow direkt auf
- Das ist absichtlich explizit, damit normale Commits mit Zahlen keine Releases ausloesen

#### Empfohlenes Release-Commit-Schema

1. Version in [src/cinescore_ai/version.py](src/cinescore_ai/version.py) anheben, z. B. auf `0.2.0`.
2. Mit expliziter Marker-Zeile committen, z. B.:

```text
feat: improve updater fallback and release docs

release: v0.2.0
```

Alternativ:

```text
chore: prepare release notes

version: 0.2.0
```

Hotfix-Beispiel:

```text
fix: korrigiere Sonderfall im Updater

hotfix: 0.1.2c
```

3. Auf den Default-Branch pushen.
4. Der Workflow erstellt `v0.2.0` und startet die Release-Pipeline.

Hinweise:

- Wenn Commit-Version und App-Version abweichen, stoppt der Workflow absichtlich
- Wenn der Tag bereits existiert, wird kein doppelter Release erzeugt

#### Plattform-Eignung

- CI laeuft multiplatform auf Linux, Windows und macOS mit Python 3.10 und 3.11
- Release-Artefakte sind source-/runtime-basierte Archive (ZIP + TAR.GZ) und plattformunabhaengig nutzbar
- Der In-App-Updater bleibt weiterhin nur unter Windows automatisiert

### Empfohlener Workflow

1. Resolve-Reiter: Kontext aktualisieren
2. Resolve-Reiter: 720p Preview rendern
3. Gemini-Reiter: letzte Preview analysieren
4. Gemini Music-Reiter: Cue-basierte Musik aus Markern erzeugen
5. Optional Audio-Reiter: externe Provider fuer Varianten nutzen

### Marker-Direktiven fuer Musiksteuerung

Direktiven koennen im Marker-Namen, in Marker-Notizen oder Keywords stehen.

Benannte Lane, Beispiel:

```text
Music Track 1: Farmer John Theme
```

Typische Direktiven:

```text
image=yes
lyrics=yes
fade=3.5
length=20
track=main
theme=Reveal Theme
keywords=cinematic, orchestral, tense
Genre = Western, Scifi
Instruments = Banjo, Synth Pad
BPM = 85
Key = D minor
Mood = nostalgic, eerie
Song_Structure = Intro, Verse, Chorus
Input = Eine sanfte Banjo-Melodie, die zunehmend schneller wird
[Stop]
```

Hinweise:

- `image=yes`: Marker-Frames als visuellen Prompt-Kontext nutzen
- `lyrics=yes`: Gesang fuer den Cue erzwingen
- `fade`: bevorzugte Crossfade-Dauer
- `length`: Ziel-Laenge des Cues (optional explizites Override ueber Marker-Notiz/Keywords)
- Das Marker-Feld `Dauer` in Resolve (Marker-Dialog) wird fuer Lyria 3 Pro ebenfalls als Cue-Laenge beruecksichtigt, damit die Laenge ohne Freitext gesetzt werden kann
- `track`: numerische oder benannte Lane (`main`, `alt`, usw.)
- `Genre`, `Instruments`, `BPM`, `Key`, `Mood`, `Song_Structure`: strukturierte Prompt-Felder
- `Input`: Freitext pro Marker mit Zeitbezug
- `[Stop]`: natuerliches Ende exakt am Marker-Zeitstempel
- `[StopHard]`: harter abrupter Schnitt exakt am Marker-Zeitstempel

Beispiel fuer JSON-ready Prompt-Struktur:

```json
{
	"cue": {
		"index": 1,
		"count": 2,
		"start_seconds": 0.0,
		"target_duration_seconds": 4.0,
		"track_slot": 1,
		"track_lane": "Track 1",
		"genres": ["Western", "Scifi"],
		"instruments": ["Banjo", "Synth Pad"],
		"bpm": 85,
		"key_scale": "D minor",
		"mood": ["nostalgic", "eerie"],
		"structure": ["Intro", "Verse", "Chorus"],
		"vocals_mode": "instrumental"
	},
	"marker_inputs": [
		{
			"timestamp": "00:00:00.000",
			"genre": ["Western", "Scifi"],
			"input": "Eine sanfte Banjo-Melodie, die zunehmend schneller wird",
			"stop": false
		},
		{
			"timestamp": "00:00:04.000",
			"genre": [],
			"input": "Sofortiger Abbruch ohne Ausklang",
			"stop": true
		}
	]
}
```

### Modelle und Ausgabeformate

- Lyria 3 Pro: `lyria-3-pro-preview`
- Lyria 3 Clip: `lyria-3-clip-preview`
- WAV-Ausgabe wird laut API nur von Lyria 3 Pro unterstuetzt
- MP3 ist fuer beide Modelle der Standard
- Wenn WAV angefordert wird, erzwingt CineScore dieses Format jetzt strikt und bricht die Erzeugung ab, falls die API kein WAV zurueckliefert
- WAV-Anfragen zielen auf 48 kHz und >=24-bit (bevorzugt 32-bit) und werden nach dem Schreiben geprueft

### Konfiguration und Speicherorte

Konfigurationsdatei:

- Windows: `AppData/Roaming/CineScore-AI/config.json`
- macOS: `Library/Application Support/CineScore-AI/config.json`
- Linux: `~/.config/CineScore-AI/config.json`

Standardordner:

- Output: `Music/CineScore AI/<projekt>/<timeline>`
- Temp/Preview: lokaler CineScore-AI-Cache-Ordner

Generierte Musik wird in Unterordnern nach Projekt und Timeline abgelegt. Dieselbe Struktur wird auch beim Resolve-MediaPool-Import unter `CineScore AI Music / <Projekt> / <Timeline>` verwendet.

### Tests

Alle Tests:

```bash
pytest
```

Resolve-Installer gezielt pruefen:

```bash
pytest tests/test_resolve_install.py
```

Ausgewaehlte Bereiche:

```bash
pytest tests/test_resolve.py
pytest tests/test_gemini_music.py
pytest tests/test_ui_smoke.py
```

### Troubleshooting

Resolve lehnt Preview-Render-Settings ab:

Fallback-Renderprofile (inklusive alternativer Aufloesungs-Keys) verbessern die Kompatibilitaet zwischen Resolve-Versionen.

WAV wird nicht importiert oder MediaInfo zeigt MPEG in `.wav`:

Im strikten WAV-Modus bricht CineScore die Erzeugung ab, wenn die API kein WAV liefert. In diesem Fall MP3 als praktikable Alternative auswaehlen und erneut starten.

`URL can't contain control characters` bei `generateContent`:

Das deutet oft auf einen nicht normalisierten Modellnamen hin. Aktuelle Versionen normalisieren Anzeige-Namen auf API-Modell-IDs.

Keine Verbindung zu Gemini oder Audio-Provider:

- API-Key pruefen
- Endpoint pruefen
- Timeout, Proxy und Firewall pruefen
- Zuerst den jeweiligen Test-Button in der UI nutzen

### Projektstruktur (Kurzuebersicht)

```text
scripts/
	dev_entry.py          # Start ohne Resolve (Mock)
	resolve_entry.py      # Start in Resolve Runtime
src/cinescore_ai/
	app.py                # App-Bootstrap
	ui/main_window.py     # Hauptfenster und Tabs
	resolve.py            # Resolve-Adapter (real/mock)
	workflow.py           # Preview-Render-Workflow
	gemini.py             # Videoanalyse mit Gemini
	gemini_music.py       # Cue-basierte Musikgenerierung
	audio.py              # Externer Audio-Provider-Workflow
	marker_directives.py  # Parsing der Marker-Direktiven
	config.py             # Laden/Speichern der Einstellungen
tests/
	...                   # Unit- und Smoke-Tests
```

### Sicherheit und Datenschutz

- API-Keys werden ueber eine Secret-Store-Abstraktion verwaltet
- Wenn verfuegbar wird die OS-Keychain verwendet
- Ohne persistente Keychain bleiben Secrets nur in der aktuellen Sitzung
