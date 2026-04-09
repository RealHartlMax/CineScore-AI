from __future__ import annotations

from dataclasses import dataclass
import re

from cinescore_ai.resolve import ResolveMarker


@dataclass(slots=True)
class MarkerMusicDirective:
    marker: ResolveMarker
    use_image: bool = False
    section_label: str | None = None
    music_track_slot: int | None = None
    track_lane: str | None = None
    track_display_label: str | None = None
    theme_label: str | None = None
    vocals_mode: str | None = None
    fade_seconds: float | None = None
    length_seconds: float | None = None
    genre_tags: tuple[str, ...] = ()
    instruments: tuple[str, ...] = ()
    bpm: int | None = None
    key_scale: str | None = None
    mood_tags: tuple[str, ...] = ()
    structure_tags: tuple[str, ...] = ()
    input_text: str | None = None
    stop_here: bool = False
    stop_mode: str | None = None
    style_keywords: tuple[str, ...] = ()
    cleaned_note: str = ""


def parse_marker_music_directive(marker: ResolveMarker) -> MarkerMusicDirective:
    directive = MarkerMusicDirective(marker=marker, cleaned_note=(marker.note or "").strip())
    name_track_slot, name_theme_label = _parse_music_track_name(marker.name or "")
    directive.music_track_slot = name_track_slot
    directive.track_lane = _track_lane_for_slot(name_track_slot) if name_track_slot is not None else None
    directive.track_display_label = _track_display_label(name_track_slot, None)
    directive.theme_label = name_theme_label
    if name_theme_label and not directive.section_label:
        directive.section_label = name_theme_label
    cleaned_lines: list[str] = []
    genre_tags: list[str] = []
    instruments: list[str] = []
    mood_tags: list[str] = []
    structure_tags: list[str] = []
    style_keywords: list[str] = []

    for raw_line in (marker.note or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if not _apply_directive_token(
            directive,
            line,
            genre_tags,
            instruments,
            mood_tags,
            structure_tags,
            style_keywords,
            collect_unparsed_as_style_keyword=False,
        ):
            cleaned_lines.append(raw_line.strip())

    for keyword in marker.keywords:
        _apply_directive_token(
            directive,
            keyword,
            genre_tags,
            instruments,
            mood_tags,
            structure_tags,
            style_keywords,
        )

    directive.cleaned_note = "\n".join(cleaned_lines).strip()
    directive.genre_tags = tuple(dict.fromkeys(tag for tag in genre_tags if tag))
    directive.instruments = tuple(dict.fromkeys(item for item in instruments if item))
    directive.mood_tags = tuple(dict.fromkeys(item for item in mood_tags if item))
    directive.structure_tags = tuple(dict.fromkeys(item for item in structure_tags if item))
    directive.style_keywords = tuple(dict.fromkeys(keyword for keyword in style_keywords if keyword))
    if directive.theme_label and not directive.section_label:
        directive.section_label = directive.theme_label
    if directive.track_display_label is None:
        directive.track_display_label = _track_display_label(directive.music_track_slot, directive.track_lane)
    return directive


def _apply_directive_token(
    directive: MarkerMusicDirective,
    token: str,
    genre_tags: list[str],
    instruments: list[str],
    mood_tags: list[str],
    structure_tags: list[str],
    style_keywords: list[str],
    *,
    collect_unparsed_as_style_keyword: bool = True,
) -> bool:
    normalized_token = token.strip().lower()
    if normalized_token == "[stop]":
        directive.stop_here = True
        directive.stop_mode = "natural"
        return True
    if normalized_token in {"[stophard]", "[stop_hard]", "[stop-hard]"}:
        directive.stop_here = True
        directive.stop_mode = "hard"
        return True

    parsed = _parse_directive_line(token)
    if parsed is None:
        cleaned = token.strip()
        if cleaned and collect_unparsed_as_style_keyword:
            style_keywords.append(cleaned)
        return False

    key, value = parsed
    if key in {"image", "use_image"}:
        bool_value = _parse_bool(value)
        if bool_value is not None:
            directive.use_image = bool_value
            return True
    if key in {"section", "structure", "part"} and value:
        directive.section_label = value.strip()
        return True
    if key in {"track", "music_track", "slot", "lane"} and value:
        slot, lane = _parse_track_value(value)
        directive.music_track_slot = slot
        directive.track_lane = lane
        directive.track_display_label = _track_display_label(slot, lane)
        return True
    if key in {"theme", "title"} and value:
        directive.theme_label = value.strip()
        if not directive.section_label:
            directive.section_label = directive.theme_label
        return True
    if key in {"lyrics", "vocal", "vocals"} and value:
        vocals_mode = _parse_vocals_mode(value)
        if vocals_mode is not None:
            directive.vocals_mode = vocals_mode
            return True
    if key == "instrumental" and value:
        bool_value = _parse_bool(value)
        if bool_value is not None:
            directive.vocals_mode = "instrumental" if bool_value else "lyrics"
            return True
    if key in {"fade", "crossfade"} and value:
        parsed_float = _parse_positive_float(value, allow_zero=True)
        if parsed_float is not None:
            directive.fade_seconds = parsed_float
            return True
    if key in {"length", "duration"} and value:
        parsed_float = _parse_positive_float(value, allow_zero=False)
        if parsed_float is not None:
            directive.length_seconds = parsed_float
            return True
    if key in {"genre", "genres"} and value:
        for tag in _split_keywords(value):
            genre_tags.append(tag)
        return True
    if key in {"instrument", "instruments"} and value:
        for item in _split_keywords(value):
            instruments.append(item)
        return True
    if key in {"bpm", "tempo"} and value:
        parsed_int = _parse_positive_int(value)
        if parsed_int is not None:
            directive.bpm = parsed_int
            return True
    if key in {"key", "scale", "tonart"} and value:
        directive.key_scale = value.strip()
        return True
    if key in {"mood", "atmosphere", "stimmung"} and value:
        for item in _split_keywords(value):
            mood_tags.append(item)
        return True
    if key in {"song_structure", "arrangement", "form"} and value:
        for item in _split_keywords(value):
            structure_tags.append(item)
        return True
    if key in {"input", "brief", "prompt"} and value:
        directive.input_text = value.strip()
        return True
    if key in {"stop", "end", "cut"}:
        if not value:
            directive.stop_here = True
            directive.stop_mode = "natural"
            return True
        bool_value = _parse_bool(value)
        if bool_value is not None:
            directive.stop_here = bool_value
            directive.stop_mode = "natural" if bool_value else None
            return True
        normalized_value = value.strip().lower()
        if normalized_value in {"now", "hard", "abrupt", "immediate", "hardcut", "hard-cut"}:
            directive.stop_here = True
            directive.stop_mode = "hard"
            return True
        if normalized_value in {"natural", "soft", "outro", "tail"}:
            directive.stop_here = True
            directive.stop_mode = "natural"
            return True
    if key in {"stop_mode", "stopmode"} and value:
        normalized_value = value.strip().lower()
        if normalized_value in {"hard", "abrupt", "immediate"}:
            directive.stop_here = True
            directive.stop_mode = "hard"
            return True
        if normalized_value in {"natural", "soft", "outro"}:
            directive.stop_here = True
            directive.stop_mode = "natural"
            return True
    if key in {"keywords", "keyword", "tags", "tag"} and value:
        for keyword in _split_keywords(value):
            style_keywords.append(keyword)
        return True

    if collect_unparsed_as_style_keyword:
        style_keywords.append(token.strip())
    return False


def _parse_directive_line(line: str) -> tuple[str, str] | None:
    normalized = line
    if normalized.lower().startswith("cinescore:"):
        normalized = normalized.split(":", 1)[1].strip()

    for separator in ("=", ":"):
        if separator in normalized:
            left, right = normalized.split(separator, 1)
            return left.strip().lower(), right.strip()
    return None


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _parse_positive_float(value: str, *, allow_zero: bool) -> float | None:
    try:
        parsed = float(value.strip())
    except ValueError:
        return None
    if parsed < 0 or (parsed == 0 and not allow_zero):
        return None
    return parsed


def _parse_positive_int(value: str) -> int | None:
    match = re.search(r"\d+", value)
    if match is None:
        return None
    parsed = int(match.group(0))
    return parsed if parsed > 0 else None


def _parse_vocals_mode(value: str) -> str | None:
    normalized = value.strip().lower()
    if normalized in {"lyrics", "lyric", "with-lyrics", "with_lyrics"}:
        return "lyrics"
    bool_value = _parse_bool(value)
    if bool_value is True:
        return "lyrics"
    if bool_value is False:
        return "instrumental"
    if normalized in {"instrumental", "no-vocals", "no_vocals"}:
        return "instrumental"
    return None


def _parse_music_track_name(value: str) -> tuple[int | None, str | None]:
    match = re.match(r"^\s*music\s*track\s*(\d+)\s*:\s*(.+?)\s*$", value, flags=re.IGNORECASE)
    if not match:
        return None, None
    return int(match.group(1)), match.group(2).strip()


def _parse_track_value(value: str) -> tuple[int | None, str]:
    normalized = value.strip()
    if not normalized:
        return None, "track-default"
    try:
        slot = max(1, int(normalized))
    except ValueError:
        lane = normalized.lower()
        return None, f"lane:{lane}"
    return slot, _track_lane_for_slot(slot)


def _track_lane_for_slot(slot: int | None) -> str | None:
    if slot is None:
        return None
    return f"slot:{slot}"


def _track_display_label(slot: int | None, lane: str | None) -> str | None:
    if slot is not None:
        return f"Track {slot}"
    if lane is None:
        return None
    if lane.startswith("lane:"):
        return lane.split(":", 1)[1]
    return lane


def _split_keywords(value: str) -> tuple[str, ...]:
    parts = value.replace(";", ",").split(",")
    return tuple(part.strip() for part in parts if part and part.strip())
