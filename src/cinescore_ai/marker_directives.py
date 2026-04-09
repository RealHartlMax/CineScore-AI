from __future__ import annotations

from dataclasses import dataclass
import re

from cinescore_ai.resolve import ResolveMarker


_POSITIVE_INT_RE = re.compile(r"\d+")
_MUSIC_TRACK_NAME_RE = re.compile(r"^\s*music\s*track\s*(\d+)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_STOPHARD_TOKENS = frozenset({"[stophard]", "[stop_hard]", "[stop-hard]"})
_BOOL_TRUE_TOKENS = frozenset({"1", "true", "yes", "y", "on"})
_BOOL_FALSE_TOKENS = frozenset({"0", "false", "no", "n", "off"})
_SECTION_KEYS = frozenset({"section", "structure", "part"})
_TRACK_KEYS = frozenset({"track", "music_track", "slot", "lane"})
_THEME_KEYS = frozenset({"theme", "title"})
_VOCALS_KEYS = frozenset({"lyrics", "vocal", "vocals"})
_FADE_KEYS = frozenset({"fade", "crossfade"})
_LENGTH_KEYS = frozenset({"length", "duration"})
_GENRE_KEYS = frozenset({"genre", "genres"})
_INSTRUMENT_KEYS = frozenset({"instrument", "instruments"})
_BPM_KEYS = frozenset({"bpm", "tempo"})
_KEY_SCALE_KEYS = frozenset({"key", "scale", "tonart"})
_MOOD_KEYS = frozenset({"mood", "atmosphere", "stimmung"})
_STRUCTURE_KEYS = frozenset({"song_structure", "arrangement", "form"})
_INPUT_KEYS = frozenset({"input", "brief", "prompt"})
_STOP_KEYS = frozenset({"stop", "end", "cut"})
_STOP_MODE_KEYS = frozenset({"stop_mode", "stopmode"})
_STOP_HARD_VALUES = frozenset({"now", "hard", "abrupt", "immediate", "hardcut", "hard-cut"})
_STOP_NATURAL_VALUES = frozenset({"natural", "soft", "outro", "tail"})
_STOP_MODE_HARD_VALUES = frozenset({"hard", "abrupt", "immediate"})
_STOP_MODE_NATURAL_VALUES = frozenset({"natural", "soft", "outro"})
_KEYWORD_KEYS = frozenset({"keywords", "keyword", "tags", "tag"})


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
    note_text = marker.note or ""
    directive = MarkerMusicDirective(marker=marker, cleaned_note=note_text.strip())
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

    for raw_line in note_text.splitlines():
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
            cleaned_lines.append(line)

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
    stripped_token = token.strip()
    normalized_token = stripped_token.lower()
    if normalized_token == "[stop]":
        directive.stop_here = True
        directive.stop_mode = "natural"
        return True
    if normalized_token in _STOPHARD_TOKENS:
        directive.stop_here = True
        directive.stop_mode = "hard"
        return True

    # Fast path for plain text note lines/keywords with no directive separator.
    if ":" not in stripped_token and "=" not in stripped_token:
        if stripped_token and collect_unparsed_as_style_keyword:
            style_keywords.append(stripped_token)
        return False

    parsed = _parse_directive_line(stripped_token)
    if parsed is None:
        if stripped_token and collect_unparsed_as_style_keyword:
            style_keywords.append(stripped_token)
        return False

    key, value = parsed
    if key in {"image", "use_image"}:
        bool_value = _parse_bool(value)
        if bool_value is not None:
            directive.use_image = bool_value
            return True
    if key in _SECTION_KEYS and value:
        directive.section_label = value.strip()
        return True
    if key in _TRACK_KEYS and value:
        slot, lane = _parse_track_value(value)
        directive.music_track_slot = slot
        directive.track_lane = lane
        directive.track_display_label = _track_display_label(slot, lane)
        return True
    if key in _THEME_KEYS and value:
        directive.theme_label = value.strip()
        if not directive.section_label:
            directive.section_label = directive.theme_label
        return True
    if key in _VOCALS_KEYS and value:
        vocals_mode = _parse_vocals_mode(value)
        if vocals_mode is not None:
            directive.vocals_mode = vocals_mode
            return True
    if key == "instrumental" and value:
        bool_value = _parse_bool(value)
        if bool_value is not None:
            directive.vocals_mode = "instrumental" if bool_value else "lyrics"
            return True
    if key in _FADE_KEYS and value:
        parsed_float = _parse_positive_float(value, allow_zero=True)
        if parsed_float is not None:
            directive.fade_seconds = parsed_float
            return True
    if key in _LENGTH_KEYS and value:
        parsed_float = _parse_positive_float(value, allow_zero=False)
        if parsed_float is not None:
            directive.length_seconds = parsed_float
            return True
    if key in _GENRE_KEYS and value:
        for tag in _split_keywords(value):
            genre_tags.append(tag)
        return True
    if key in _INSTRUMENT_KEYS and value:
        for item in _split_keywords(value):
            instruments.append(item)
        return True
    if key in _BPM_KEYS and value:
        parsed_int = _parse_positive_int(value)
        if parsed_int is not None:
            directive.bpm = parsed_int
            return True
    if key in _KEY_SCALE_KEYS and value:
        directive.key_scale = value.strip()
        return True
    if key in _MOOD_KEYS and value:
        for item in _split_keywords(value):
            mood_tags.append(item)
        return True
    if key in _STRUCTURE_KEYS and value:
        for item in _split_keywords(value):
            structure_tags.append(item)
        return True
    if key in _INPUT_KEYS and value:
        directive.input_text = value.strip()
        return True
    if key in _STOP_KEYS:
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
        if normalized_value in _STOP_HARD_VALUES:
            directive.stop_here = True
            directive.stop_mode = "hard"
            return True
        if normalized_value in _STOP_NATURAL_VALUES:
            directive.stop_here = True
            directive.stop_mode = "natural"
            return True
    if key in _STOP_MODE_KEYS and value:
        normalized_value = value.strip().lower()
        if normalized_value in _STOP_MODE_HARD_VALUES:
            directive.stop_here = True
            directive.stop_mode = "hard"
            return True
        if normalized_value in _STOP_MODE_NATURAL_VALUES:
            directive.stop_here = True
            directive.stop_mode = "natural"
            return True
    if key in _KEYWORD_KEYS and value:
        for keyword in _split_keywords(value):
            style_keywords.append(keyword)
        return True

    if collect_unparsed_as_style_keyword:
        style_keywords.append(stripped_token)
    return False


def _parse_directive_line(line: str) -> tuple[str, str] | None:
    normalized = line
    if normalized.lower().startswith("cinescore:"):
        normalized = normalized.split(":", 1)[1].strip()

    if "=" in normalized:
        left, _, right = normalized.partition("=")
        return left.strip().lower(), right.strip()
    if ":" in normalized:
        left, _, right = normalized.partition(":")
        return left.strip().lower(), right.strip()
    return None


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in _BOOL_TRUE_TOKENS:
        return True
    if normalized in _BOOL_FALSE_TOKENS:
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
    match = _POSITIVE_INT_RE.search(value)
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
    match = _MUSIC_TRACK_NAME_RE.match(value)
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
    return tuple(stripped for part in parts if (stripped := part.strip()))
