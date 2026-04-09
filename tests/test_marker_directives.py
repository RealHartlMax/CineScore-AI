from __future__ import annotations

import unittest

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.marker_directives import parse_marker_music_directive
from cinescore_ai.resolve import ResolveMarker


class MarkerDirectivesTests(unittest.TestCase):
    def test_parse_marker_music_directive_extracts_image_flag_and_section(self) -> None:
        marker = ResolveMarker(
            frame_offset=0,
            absolute_frame=0,
            relative_seconds=0.0,
            timestamp="00:00:00.000",
            duration_frames=0,
            color="Blue",
            name="Music",
            note="image=yes\nsection=Intro\nSanfter Einstieg",
        )

        directive = parse_marker_music_directive(marker)

        self.assertTrue(directive.use_image)
        self.assertEqual(directive.section_label, "Intro")
        self.assertEqual(directive.cleaned_note, "Sanfter Einstieg")

    def test_parse_marker_music_directive_extracts_named_music_track(self) -> None:
        marker = ResolveMarker(
            frame_offset=0,
            absolute_frame=0,
            relative_seconds=0.0,
            timestamp="00:00:00.000",
            duration_frames=0,
            color="Blue",
            name="Music Track 2: Mayor Pierce Theme",
            note="düster untertun",
        )

        directive = parse_marker_music_directive(marker)

        self.assertEqual(directive.music_track_slot, 2)
        self.assertEqual(directive.theme_label, "Mayor Pierce Theme")
        self.assertEqual(directive.section_label, "Mayor Pierce Theme")
        self.assertEqual(directive.track_lane, "slot:2")
        self.assertEqual(directive.track_display_label, "Track 2")

    def test_parse_marker_music_directive_reads_advanced_directives_from_note_and_keywords(self) -> None:
        marker = ResolveMarker(
            frame_offset=0,
            absolute_frame=0,
            relative_seconds=0.0,
            timestamp="00:00:00.000",
            duration_frames=0,
            color="Blue",
            name="Cue Accent",
            note="length=20\nSanfter Einstieg",
            keywords=("lyrics=yes", "fade=3.5", "track=main", "country"),
        )

        directive = parse_marker_music_directive(marker)

        self.assertEqual(directive.track_lane, "lane:main")
        self.assertEqual(directive.track_display_label, "main")
        self.assertEqual(directive.vocals_mode, "lyrics")
        self.assertEqual(directive.fade_seconds, 3.5)
        self.assertEqual(directive.length_seconds, 20.0)
        self.assertEqual(directive.style_keywords, ("country",))
        self.assertEqual(directive.cleaned_note, "Sanfter Einstieg")

    def test_parse_marker_music_directive_accepts_keywords_directive_in_note(self) -> None:
        marker = ResolveMarker(
            frame_offset=0,
            absolute_frame=0,
            relative_seconds=0.0,
            timestamp="00:00:00.000",
            duration_frames=0,
            color="Blue",
            name="Cue Accent",
            note="tags=western, dark\nabrupter Stopp",
        )

        directive = parse_marker_music_directive(marker)

        self.assertEqual(directive.style_keywords, ("western", "dark"))
        self.assertEqual(directive.cleaned_note, "abrupter Stopp")

    def test_parse_marker_music_directive_reads_structured_free_text_and_stop(self) -> None:
        marker = ResolveMarker(
            frame_offset=0,
            absolute_frame=0,
            relative_seconds=0.0,
            timestamp="00:00:00.000",
            duration_frames=0,
            color="Blue",
            name="Cue Accent",
            note=(
                "Genre = Western, Scifi\n"
                "Instruments = Banjo, Synth Pad\n"
                "BPM = 85\n"
                "Key = D minor\n"
                "Mood = nostalgic, eerie\n"
                "Song_Structure = Intro, Verse\n"
                "Input = Ein sanfter Banjo-Klang\n"
                "[Stop]\n"
                "ruhiger Start"
            ),
        )

        directive = parse_marker_music_directive(marker)

        self.assertEqual(directive.genre_tags, ("Western", "Scifi"))
        self.assertEqual(directive.instruments, ("Banjo", "Synth Pad"))
        self.assertEqual(directive.bpm, 85)
        self.assertEqual(directive.key_scale, "D minor")
        self.assertEqual(directive.mood_tags, ("nostalgic", "eerie"))
        self.assertEqual(directive.structure_tags, ("Intro", "Verse"))
        self.assertEqual(directive.input_text, "Ein sanfter Banjo-Klang")
        self.assertTrue(directive.stop_here)
        self.assertEqual(directive.stop_mode, "natural")
        self.assertEqual(directive.cleaned_note, "ruhiger Start")

    def test_parse_marker_music_directive_reads_stophard(self) -> None:
        marker = ResolveMarker(
            frame_offset=0,
            absolute_frame=0,
            relative_seconds=0.0,
            timestamp="00:00:00.000",
            duration_frames=0,
            color="Blue",
            name="Cue Accent",
            note="[StopHard]\nabrupter Abschluss",
        )

        directive = parse_marker_music_directive(marker)

        self.assertTrue(directive.stop_here)
        self.assertEqual(directive.stop_mode, "hard")
        self.assertEqual(directive.cleaned_note, "abrupter Abschluss")
