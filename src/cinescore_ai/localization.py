from __future__ import annotations

from dataclasses import dataclass
import locale
import os
import sys
from pathlib import Path
from typing import Mapping
import xml.etree.ElementTree as ET


GERMAN_TRANSLATIONS: dict[str, str] = {
    "CineScore AI Settings": "CineScore AI Einstellungen",
    "Resolve Context": "Resolve-Kontext",
    "Gemini": "Gemini",
    "Gemini Music (Lyria 3)": "Gemini Music (Lyria 3)",
    "Audio Provider": "Audio-Anbieter",
    "Paths": "Pfade",
    "Status": "Status",
    "Discard unsaved changes": "Ungespeicherte Änderungen verwerfen",
    "Test Gemini": "Gemini testen",
    "Test Audio Provider": "Audio-Anbieter testen",
    "Save": "Speichern",
    "Check for updates": "Auf Updates prüfen",
    "Project": "Projekt",
    "Timeline": "Timeline",
    "Start TC / Frame": "Start-TC / Frame",
    "Frame rate": "Bildrate",
    "Markers": "Marker",
    "Last preview render": "Letzter Vorschau-Render",
    "Render status": "Render-Status",
    "Render progress": "Render-Fortschritt",
    "Refresh Resolve Context": "Resolve-Kontext aktualisieren",
    "Render 720p Preview Now": "720p-Vorschau jetzt rendern",
    "Markers will appear here after loading the current timeline.": "Marker erscheinen hier, nachdem die aktuelle Timeline geladen wurde.",
    "Not loaded yet.": "Noch nicht geladen.",
    "No preview render queued.": "Noch kein Vorschau-Render eingereiht.",
    "Idle": "Leerlauf",
    "Endpoint": "Endpunkt",
    "Model": "Modell",
    "API key": "API-Schlüssel",
    "Analysis source": "Analysequelle",
    "No preview available yet.": "Noch keine Vorschau verfügbar.",
    "Not tested yet.": "Noch nicht getestet.",
    "Analyze Last Preview With Gemini": "Letzte Vorschau mit Gemini analysieren",
    "Gemini analysis results will appear here as structured JSON.": "Gemini-Analyseergebnisse erscheinen hier als strukturiertes JSON.",
    "Structured Gemini analysis will appear here after a preview render is available.": "Strukturierte Gemini-Analyse erscheint hier, sobald ein Vorschau-Render verfügbar ist.",
    "Provider": "Anbieter",
    "Base URL": "Basis-URL",
    "Model hint": "Modell-Hinweis",
    "Test endpoint": "Test-Endpunkt",
    "No Gemini plan available yet.": "Noch kein Gemini-Plan verfügbar.",
    "Generate Timeline Audio From Last Analysis": "Timeline-Audio aus der letzten Analyse erzeugen",
    "Generated audio segment details will appear here after composition.": "Details zu erzeugten Audiosegmenten erscheinen hier nach der Komposition.",
    "Generated audio placements will appear here after a Gemini analysis is available.": "Platzierungen des erzeugten Audios erscheinen hier, sobald eine Gemini-Analyse verfügbar ist.",
    "Lyria 3 Pro": "Lyria 3 Pro",
    "Lyria 3 Clip": "Lyria 3 Clip",
    "Instrumental only": "Nur instrumental",
    "With lyrics": "Mit Text",
    "Vocals": "Gesang",
    "Output format": "Ausgabeformat",
    "Marker images": "Marker-Bilder",
    "Use marker images when flagged": "Marker-Bilder verwenden, wenn markiert",
    "Ignore marker images": "Marker-Bilder ignorieren",
    "Crossfade seconds": "Crossfade-Sekunden",
    "Crossfade seconds (Resolve)": "Crossfade-Sekunden (Resolve)",
    "Source preview": "Quellvorschau",
    "Not generated yet.": "Noch nicht erzeugt.",
    "Generate Timeline Music With Gemini": "Timeline-Musik mit Gemini erzeugen",
    "Gemini music generation results, lyrics, structure text, and placement details will appear here.": "Ergebnisse der Gemini-Musikerzeugung, Liedtext-, Struktur- und Platzierungsdetails erscheinen hier.",
    "Gemini music output summary: requested {requested}. Saved files -> WAV: {wav_count}, MP3: {mp3_count}.": "Gemini-Musik-Ausgabe: angefordert {requested}. Gespeicherte Dateien -> WAV: {wav_count}, MP3: {mp3_count}.",
    "Requested WAV but Gemini returned MP3-compatible audio for {count} cue(s); saved as MP3 to preserve import compatibility.": "WAV wurde angefordert, aber Gemini lieferte MP3-kompatibles Audio fuer {count} Cue(s); zur Import-Kompatibilitaet als MP3 gespeichert.",
    "Use marker names like 'Music Track 1: Farmer John Theme' to define named music lanes. Markers with the same lane are grouped into one generated cue for that lane, and later markers in that lane are treated as in-cue directives. Use structured free text per paragraph such as 'Genre = Western, Scifi', 'Instruments = Banjo, Synth Pad', 'BPM = 85', 'Key = D minor', 'Mood = nostalgic, eerie', 'Song_Structure = Intro, Verse, Chorus', and 'Input = A gentle banjo motif that accelerates over time'. Use '[Stop]' to end naturally at that marker timestamp, or '[StopHard]' for an abrupt exact cut.": "Verwende Markernamen wie 'Music Track 1: Farmer John Theme', um benannte Musik-Lanes zu definieren. Marker mit derselben Lane werden zu einem erzeugten Cue fuer diese Lane zusammengefasst, und spaetere Marker in dieser Lane werden als In-Cue-Direktiven behandelt. Nutze strukturierten Freitext pro Absatz wie 'Genre = Western, Scifi', 'Instruments = Banjo, Synth Pad', 'BPM = 85', 'Key = D minor', 'Mood = nostalgic, eerie', 'Song_Structure = Intro, Verse, Chorus' und 'Input = Ein sanftes Banjo-Motiv, das mit der Zeit schneller wird'. Setze '[Stop]', damit der Cue natuerlich an diesem Marker-Zeitstempel endet, oder '[StopHard]' fuer einen abrupten exakten Schnitt.",
    "Output directory": "Ausgabeordner",
    "Temp directory": "Temporärer Ordner",
    "Temp preview retention (days)": "Aufbewahrung Temp-Vorschau (Tage)",
    "Cache actions": "Cache-Aktionen",
    "Delete preview cache": "Vorschau-Cache löschen",
    "Delete all temp cache files": "Gesamten Temp-Cache löschen",
    "Browse": "Durchsuchen",
    "Runtime: {runtime}. {summary}": "Laufzeit: {runtime}. {summary}",
    "Installed version: {version}": "Installierte Version: {version}",
    "Development Mode": "Entwicklungsmodus",
    "Running outside DaVinci Resolve using the mock adapter.": "Läuft außerhalb von DaVinci Resolve mit dem Mock-Adapter.",
    "Connected to the DaVinci Resolve scripting runtime.": "Mit der DaVinci-Resolve-Scripting-Laufzeit verbunden.",
    "Resolve scripting handle is missing.": "Der Resolve-Scripting-Handle fehlt.",
    "Secrets are stored in the OS keychain via '{backend}'.": "Geheimnisse werden über '{backend}' im OS-Schlüsselbund gespeichert.",
    "No persistent keychain backend was found. Secrets stay in memory for this session only.": "Kein persistentes Schlüsselbund-Backend gefunden. Geheimnisse bleiben nur für diese Sitzung im Speicher.",
    "Settings loaded.": "Einstellungen geladen.",
    "Resolve context can now be refreshed, preview renders can run to completion, Gemini can analyze the latest preview, Gemini Lyria can compose marker-driven music, and optional external audio providers can place generated audio back into Resolve.": "Der Resolve-Kontext kann jetzt aktualisiert werden, Vorschau-Render können vollständig durchlaufen, Gemini kann die letzte Vorschau analysieren, Gemini Lyria kann marker-gesteuerte Musik komponieren und optionale externe Audio-Anbieter können erzeugtes Audio zurück in Resolve platzieren.",
    "Testing...": "Wird getestet...",
    "Generating audio...": "Audio wird erzeugt...",
    "Analyzing preview...": "Vorschau wird analysiert...",
    "Generating music...": "Musik wird erzeugt...",
    "Preparing preview render...": "Vorschau-Render wird vorbereitet...",
    "Starting...": "Startet...",
    "Loading Resolve timeline context...": "Resolve-Timeline-Kontext wird geladen...",
    "Starting 720p preview render and waiting for completion...": "720p-Vorschau-Render wird gestartet und auf Abschluss gewartet...",
    "Testing Gemini connection...": "Gemini-Verbindung wird getestet...",
    "Testing audio provider connection...": "Verbindung zum Audio-Anbieter wird getestet...",
    "Starting audio generation from the latest Gemini analysis...": "Audio-Erzeugung aus der letzten Gemini-Analyse wird gestartet...",
    "Starting Gemini video analysis for the latest preview render...": "Gemini-Videoanalyse für den letzten Vorschau-Render wird gestartet...",
    "Starting Gemini music generation from timeline markers...": "Gemini-Musikerzeugung aus Timeline-Markern wird gestartet...",
    "Run Gemini analysis first.": "Bitte zuerst die Gemini-Analyse ausführen.",
    "Audio generation skipped because no Gemini analysis result is available yet.": "Audio-Erzeugung übersprungen, da noch kein Gemini-Analyseergebnis vorliegt.",
    "Saved configuration to {path}.": "Konfiguration wurde in {path} gespeichert.",
    "Secrets are only available for the current app session.": "Geheimnisse sind nur für die aktuelle App-Sitzung verfügbar.",
    "Discarded unsaved changes.": "Ungespeicherte Änderungen wurden verworfen.",
    "Task failed: {error}": "Aufgabe fehlgeschlagen: {error}",
    "Temp cache directory does not exist: {path}": "Temp-Cache-Ordner existiert nicht: {path}",
    "Deleted {count} preview cache file(s) from {path}.": "{count} Vorschau-Cache-Datei(en) aus {path} gelöscht.",
    "Deleted {count} temp cache entries from {path}.": "{count} Temp-Cache-Einträge aus {path} gelöscht.",
    "Opened audio folder for manual import: {path}": "Audio-Ordner für manuellen Import geöffnet: {path}",
    "Drag the generated audio file into the Resolve Media Pool manually.": "Ziehe die erzeugte Audiodatei manuell in den Resolve Media Pool.",
    "Loaded timeline '{timeline}' from project '{project}' with {count} markers.": "Timeline '{timeline}' aus Projekt '{project}' mit {count} Markern geladen.",
    "Unavailable": "Nicht verfügbar",
    "Gemini analysis completed.": "Gemini-Analyse abgeschlossen.",
    "Gemini analysis completed for {preview_path}.": "Gemini-Analyse für {preview_path} abgeschlossen.",
    "Gemini music generation completed.": "Gemini-Musikerzeugung abgeschlossen.",
    "Gemini music generated {count} cue(s) and placed them back into Resolve.": "Gemini hat {count} Cue(s) erzeugt und in Resolve platziert.",
    "Audio generation completed.": "Audio-Erzeugung abgeschlossen.",
    "Generated and placed {count} audio segment(s) on Resolve track {track}.": "{count} Audiosegment(e) wurden erzeugt und auf Resolve-Spur {track} platziert.",
    "Warning: {warning}": "Warnung: {warning}",
    "No markers were found on the active timeline.": "Auf der aktiven Timeline wurden keine Marker gefunden.",
    "Untitled marker": "Unbenannter Marker",
    "No note": "Keine Notiz",
    "No color": "Keine Farbe",
    "keywords: {keywords}": "Stichwörter: {keywords}",
    "Choose output directory": "Ausgabeordner auswählen",
    "Choose temp directory": "Temporären Ordner auswählen",
    "Unsaved changes": "Ungespeicherte Änderungen",
    "Discard unsaved changes and close the window?": "Ungespeicherte Änderungen verwerfen und das Fenster schließen?",
    "Update available": "Update verfügbar",
    "A new CineScore AI version is available.": "Eine neue CineScore-AI-Version ist verfügbar.",
    "Installed version: {version}": "Installierte Version: {version}",
    "Latest version: {version}": "Neueste Version: {version}",
    "Release: {title}": "Release: {title}",
    "Release notes": "Änderungsprotokoll",
    "No changelog provided for this release.": "Für dieses Release wurde kein Änderungsprotokoll bereitgestellt.",
    "Update now": "Jetzt aktualisieren",
    "Later": "Später",
    "Automatic update is currently only supported on Windows.": "Die automatische Aktualisierung wird derzeit nur unter Windows unterstützt.",
    "Checking for CineScore AI updates...": "CineScore AI sucht nach Updates...",
    "Update available: installed {current}, latest {latest}.": "Update verfügbar: installiert {current}, neueste Version {latest}.",
    "CineScore AI is already up to date.": "CineScore AI ist bereits auf dem neuesten Stand.",
    "Update check failed: {error}": "Update-Prüfung fehlgeschlagen: {error}",
    "Start update": "Update starten",
    "DaVinci Resolve will be closed automatically for the update. Save your project first. Continue?": "DaVinci Resolve wird für das Update automatisch geschlossen. Speichere dein Projekt zuerst. Fortfahren?",
    "Could not start updater: {error}": "Updater konnte nicht gestartet werden: {error}",
    "Update helper started. DaVinci Resolve will close automatically. After installation, the helper can reopen Resolve.": "Der Update-Helfer wurde gestartet. DaVinci Resolve wird automatisch geschlossen. Nach der Installation kann der Helfer Resolve wieder öffnen.",
}


SUPPORTED_LANGUAGES = {"en", "de"}


def get_resolve_preferences_file_path() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Blackmagic Design" / "DaVinci Resolve" / "Preferences" / "config.user.xml"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "Blackmagic Design" / "DaVinci Resolve" / "config.user.xml"
    return Path.home() / ".local" / "share" / "DaVinciResolve" / "Preferences" / "config.user.xml"


def normalize_language_code(language_code: str | None) -> str:
    normalized = (language_code or "").strip().lower().replace("-", "_")
    if normalized.startswith("de"):
        return "de"
    if normalized.startswith("en"):
        return "en"
    return "en"


def read_resolve_language_code(preferences_file: Path | None = None) -> str | None:
    path = preferences_file or get_resolve_preferences_file_path()
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError, UnicodeDecodeError):
        return None
    language = root.findtext("Language")
    return language.strip() if isinstance(language, str) and language.strip() else None


def detect_application_language(preferences_file: Path | None = None) -> str:
    resolve_language = read_resolve_language_code(preferences_file)
    if resolve_language:
        return normalize_language_code(resolve_language)
    system_language = locale.getlocale()[0] or os.environ.get("LANG")
    return normalize_language_code(system_language)


@dataclass(frozen=True, slots=True)
class Localizer:
    language_code: str = "en"

    def __post_init__(self) -> None:
        object.__setattr__(self, "language_code", normalize_language_code(self.language_code))

    def t(self, text: str, **kwargs: object) -> str:
        localized = self._translations().get(text, text)
        if kwargs:
            return localized.format(**kwargs)
        return localized

    def _translations(self) -> Mapping[str, str]:
        if self.language_code == "de":
            return GERMAN_TRANSLATIONS
        return {}
