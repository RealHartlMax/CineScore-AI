from __future__ import annotations

from base64 import b64encode
from copy import deepcopy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.config import GeminiMusicSettings, GeminiSettings
from cinescore_ai.frame_extractor import ExtractedMarkerFrame
from cinescore_ai.gemini import GeminiMusicPromptPlan, GeminiVideoAnalysisResult
from cinescore_ai.gemini_music import GeminiMusicGenerationError, GeminiMusicGenerationService, _normalize_music_model_name
from cinescore_ai.resolve import MockResolveAdapter


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return self._responses.pop(0)


class _FakeFrameExtractor:
    def extract_marker_frames(self, directives, output_directory, max_images=10):
        if not directives:
            return []
        output_dir = Path(output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        frame_path = output_dir / "frame_01.jpg"
        frame_path.write_bytes(b"jpeg-bytes")
        return [
            ExtractedMarkerFrame(
                marker_timestamp=directives[0].marker.timestamp,
                marker_name=directives[0].marker.name,
                image_path=str(frame_path),
            )
        ]


class _FakeAudioProcessor:
    def __init__(self) -> None:
        self.calls = []

    def apply_fades_in_place(self, file_path, request) -> None:
        self.calls.append((str(file_path), request))


class _FailingImportResolveAdapter(MockResolveAdapter):
    def place_audio_clip(self, file_path: str, record_frame: int, track_index: int, timeline_context=None):
        raise RuntimeError(f"Resolve could not import audio file '{file_path}' into the media pool.")


class GeminiMusicGenerationServiceTests(unittest.TestCase):
    def test_normalize_music_model_name_accepts_display_and_prefixed_values(self) -> None:
        self.assertEqual(_normalize_music_model_name("Lyria 3 Pro"), "lyria-3-pro-preview")
        self.assertEqual(_normalize_music_model_name("Lyria 3 Clip"), "lyria-3-clip-preview")
        self.assertEqual(_normalize_music_model_name("models/lyria-3-pro-preview"), "lyria-3-pro-preview")

    def test_generate_from_timeline_respects_named_music_tracks_and_overlaps(self) -> None:
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = [
            deepcopy(context.markers[0]),
            deepcopy(context.markers[1]),
            deepcopy(context.markers[2]),
            deepcopy(context.markers[1]),
        ]
        context.markers[0].frame_offset = 0
        context.markers[0].absolute_frame = context.start_frame
        context.markers[0].relative_seconds = 0.0
        context.markers[0].timestamp = "00:00:00.000"
        context.markers[0].name = "Music Track 1: Farmer John Theme"
        context.markers[0].note = "image=yes\nSanfter Einstieg"
        context.markers[1].frame_offset = int(round(2.967 * context.frame_rate))
        context.markers[1].absolute_frame = context.start_frame + context.markers[1].frame_offset
        context.markers[1].relative_seconds = 2.967
        context.markers[1].timestamp = "00:00:02.967"
        context.markers[1].name = "Music Track 2: Mayor Pierce Theme"
        context.markers[1].note = "image=no\ndüster untertun"
        context.markers[2].frame_offset = int(round(3.3 * context.frame_rate))
        context.markers[2].absolute_frame = context.start_frame + context.markers[2].frame_offset
        context.markers[2].relative_seconds = 3.3
        context.markers[2].timestamp = "00:00:03.300"
        context.markers[2].name = "Music Track 1: Farmer John Theme"
        context.markers[2].note = "image=no\nstarker Drop"
        context.markers[3].frame_offset = int(round(5.283 * context.frame_rate))
        context.markers[3].absolute_frame = context.start_frame + context.markers[3].frame_offset
        context.markers[3].relative_seconds = 5.283
        context.markers[3].timestamp = "00:00:05.283"
        context.markers[3].name = "Music Track 2: Mayor Pierce Theme"
        context.markers[3].note = "image=no\nabrupter Stopp"

        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue 1 structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-bytes-1").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue 2 structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-bytes-2").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue 3 structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-bytes-3").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue 4 structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-bytes-4").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        audio_processor = _FakeAudioProcessor()
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=audio_processor,
            session=session,
        )
        analysis_result = GeminiVideoAnalysisResult(
            preview_path="preview.mp4",
            remote_file_name=None,
            remote_file_uri=None,
            remote_cleanup_attempted=False,
            remote_cleanup_succeeded=False,
            plan=GeminiMusicPromptPlan(
                timeline_summary="Calm intro, then energetic drop.",
                base_music_prompt="Warm ambient opening with a bold payoff.",
                extend_prompts=[],
                mix_notes=[],
            ),
            raw_json={},
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            result = service.generate_from_timeline(
                api_key="secret",
                gemini_settings=GeminiSettings(
                    endpoint="https://generativelanguage.googleapis.com/v1beta/models",
                    timeout_seconds=30,
                ),
                music_settings=GeminiMusicSettings(
                    model="lyria-3-pro-preview",
                    vocals_mode="instrumental",
                    output_format="mp3",
                    use_marker_images=True,
                    max_images=10,
                ),
                timeline_context=context,
                preview_path=preview_path,
                output_directory=temp_dir,
                analysis_result=analysis_result,
            )

            self.assertEqual(len(result.cues), 2)
            self.assertTrue(Path(result.cues[0].output_path).exists())
            self.assertTrue(Path(result.cues[1].output_path).exists())
            expected_output_dir = Path(temp_dir) / "mock-project" / "assembly-cut"
            self.assertEqual(Path(result.output_directory), expected_output_dir)
            self.assertEqual(Path(result.cues[0].output_path).parent, expected_output_dir)
            self.assertEqual(
                result.cues[0].placement.media_pool_folder_name,
                "CineScore AI Music / Mock Project / Assembly Cut",
            )
            self.assertEqual(result.cues[0].mime_type, "audio/mpeg")
            self.assertEqual(result.cues[0].placement.track_index, 4)
            self.assertEqual(result.cues[1].placement.track_index, 5)
            self.assertEqual(result.cues[0].plan.music_track_slot, 1)
            self.assertEqual(result.cues[1].plan.music_track_slot, 2)
            self.assertEqual(len(result.cues[0].used_marker_images), 1)
            self.assertEqual(len(result.cues[1].used_marker_images), 0)
            self.assertIn("Sanfter Einstieg", result.cues[0].plan.prompt)
            self.assertIn("starker Drop", result.cues[0].plan.prompt)
            self.assertIn("düster untertun", result.cues[1].plan.prompt)
            self.assertIn("abrupter Stopp", result.cues[1].plan.prompt)
            self.assertIn("Music track slot: 1", result.cues[0].plan.prompt)
            # Verify generic cue identifier instead of specific theme names (copyright filter protection)
            self.assertIn("Cue identifier: Cue 1", result.cues[0].plan.prompt)
            self.assertIn("Cue identifier: Cue 2", result.cues[1].plan.prompt)
            self.assertIn("Calm intro, then energetic drop.", result.cues[0].plan.prompt)
            self.assertGreater(result.cues[0].plan.fade_out_seconds, 0.0)
            self.assertEqual(result.cues[1].plan.fade_in_seconds, result.cues[0].plan.fade_out_seconds)
            self.assertEqual(len(audio_processor.calls), 0)

        self.assertEqual(
            session.calls[0][1],
            "https://generativelanguage.googleapis.com/v1beta/models/lyria-3-pro-preview:generateContent",
        )
        payload = session.calls[0][2]["json"]
        self.assertEqual(payload["generationConfig"]["responseModalities"], ["AUDIO", "TEXT"])
        self.assertEqual(payload["contents"][0]["parts"][1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(
            session.calls[1][2]["json"]["contents"][0]["parts"][0]["text"].splitlines()[0],
            "Compose cue 2 of 2 for an edited video timeline.",
        )

    def test_generate_from_timeline_requests_wav_when_selected(self) -> None:
        """When WAV is selected and returned as WAV, the output keeps .wav."""
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = []
        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/wav",
                                                "data": b64encode(b"wav-bytes").decode("ascii"),
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                )
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            result = service.generate_from_timeline(
                api_key="secret",
                gemini_settings=GeminiSettings(),
                music_settings=GeminiMusicSettings(model="Lyria 3 Pro", output_format="wav"),
                timeline_context=context,
                preview_path=preview_path,
                output_directory=temp_dir,
            )

            self.assertTrue(result.cues[0].output_path.endswith(".wav"))
            self.assertEqual(result.model, "lyria-3-pro-preview")
            self.assertEqual(session.calls[0][2]["json"]["generationConfig"]["responseMimeType"], "audio/wav")

    def test_generate_from_timeline_rejects_mp3_when_wav_is_requested(self) -> None:
        """If WAV is requested but Gemini returns MPEG audio, the request fails in strict WAV mode."""
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = []
        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"mp3-bytes").decode("ascii"),
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                )
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            with self.assertRaises(GeminiMusicGenerationError) as ctx:
                service.generate_from_timeline(
                    api_key="secret",
                    gemini_settings=GeminiSettings(),
                    music_settings=GeminiMusicSettings(model="Lyria 3 Pro", output_format="wav"),
                    timeline_context=context,
                    preview_path=preview_path,
                    output_directory=temp_dir,
                )

            self.assertIn("requested WAV but Gemini returned audio/mpeg", str(ctx.exception))

    def test_generate_from_timeline_uses_marker_duration_field_without_length_directive(self) -> None:
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = [deepcopy(context.markers[0])]
        context.markers[0].frame_offset = 0
        context.markers[0].absolute_frame = context.start_frame
        context.markers[0].relative_seconds = 0.0
        context.markers[0].timestamp = "00:00:00.000"
        context.markers[0].duration_frames = int(context.frame_rate * 5)  # Resolve marker duration field: 5 seconds
        context.markers[0].name = "Duration cue"
        context.markers[0].note = "simple cue without length directive"

        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-bytes").decode("ascii"),
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                )
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            result = service.generate_from_timeline(
                api_key="secret",
                gemini_settings=GeminiSettings(),
                music_settings=GeminiMusicSettings(model="lyria-3-pro-preview", output_format="mp3"),
                timeline_context=context,
                preview_path=preview_path,
                output_directory=temp_dir,
            )

            self.assertEqual(len(result.cues), 1)
            self.assertAlmostEqual(result.cues[0].plan.requested_duration_seconds, 5.0, places=2)

    def test_generate_from_timeline_raises_when_response_mime_type_is_rejected(self) -> None:
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = []
        session = _FakeSession(
            [
                _FakeResponse(
                    400,
                    {},
                    text=(
                        '{"error":{"message":"* GenerateContentRequest.generation_config.response_mime_type: '
                        'allowed mimetypes are `text/plain`, `application/json`"}}'
                    ),
                ),
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"mp3-bytes").decode("ascii"),
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            with self.assertRaises(GeminiMusicGenerationError) as ctx:
                service.generate_from_timeline(
                    api_key="secret",
                    gemini_settings=GeminiSettings(),
                    music_settings=GeminiMusicSettings(model="lyria-3-pro-preview", output_format="wav"),
                    timeline_context=context,
                    preview_path=preview_path,
                    output_directory=temp_dir,
                )

            self.assertEqual(len(session.calls), 2)
            self.assertIn("responseMimeType", session.calls[0][2]["json"]["generationConfig"])
            self.assertNotIn("responseMimeType", session.calls[1][2]["json"]["generationConfig"])
            self.assertIn("requested WAV but Gemini returned audio/mpeg", str(ctx.exception))

    def test_generate_from_timeline_raises_on_http_error(self) -> None:
        """An HTTP error from the Gemini API raises GeminiMusicGenerationError with status and body."""
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = []
        session = _FakeSession(
            [
                _FakeResponse(
                    429,
                    {},
                    text='{"error":{"message":"Resource exhausted"}}',
                ),
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            with self.assertRaises(GeminiMusicGenerationError) as ctx:
                service.generate_from_timeline(
                    api_key="secret",
                    gemini_settings=GeminiSettings(),
                    music_settings=GeminiMusicSettings(model="lyria-3-pro-preview", output_format="mp3"),
                    timeline_context=context,
                    preview_path=preview_path,
                    output_directory=temp_dir,
                )
            self.assertIn("HTTP 429", str(ctx.exception))

    def test_generate_from_timeline_honors_keyword_lane_length_and_lyrics_overrides(self) -> None:
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = [deepcopy(context.markers[0]), deepcopy(context.markers[1])]
        context.markers[0].frame_offset = 0
        context.markers[0].absolute_frame = context.start_frame
        context.markers[0].relative_seconds = 0.0
        context.markers[0].timestamp = "00:00:00.000"
        context.markers[0].name = "Opening cue"
        context.markers[0].note = "length=20\nSanfter Einstieg"
        context.markers[0].keywords = ("track=main", "lyrics=yes", "country")
        context.markers[1].frame_offset = int(round(4.0 * context.frame_rate))
        context.markers[1].absolute_frame = context.start_frame + context.markers[1].frame_offset
        context.markers[1].relative_seconds = 4.0
        context.markers[1].timestamp = "00:00:04.000"
        context.markers[1].name = "Counter cue"
        context.markers[1].note = "düster untertun"
        context.markers[1].keywords = ("track=alt", "fade=3.5")

        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue A structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-main").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue B structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-alt").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            result = service.generate_from_timeline(
                api_key="secret",
                gemini_settings=GeminiSettings(),
                music_settings=GeminiMusicSettings(
                    model="lyria-3-pro-preview",
                    vocals_mode="instrumental",
                    output_format="mp3",
                    use_marker_images=False,
                    crossfade_seconds=2.0,
                ),
                timeline_context=context,
                preview_path=preview_path,
                output_directory=temp_dir,
            )

            self.assertEqual(len(result.cues), 2)
            self.assertEqual(result.cues[0].plan.track_lane, "lane:main")
            self.assertEqual(result.cues[0].plan.track_display_label, "main")
            self.assertEqual(result.cues[0].plan.vocals_mode, "lyrics")
            self.assertEqual(result.cues[0].plan.requested_duration_seconds, 20.0)
            self.assertEqual(result.cues[0].plan.directives[0].cleaned_note, "Sanfter Einstieg")
            self.assertIn("Music track lane: main", result.cues[0].plan.prompt)
            self.assertIn("Style keywords for this cue: country", result.cues[0].plan.prompt)
            self.assertIn("Include vocals and lyrics for this cue.", result.cues[0].plan.prompt)
            self.assertIn("- 00:00:00.000 Sanfter Einstieg", result.cues[0].plan.prompt)
            self.assertTrue(result.cues[0].output_path.endswith("track_main_opening-cue.mp3"))
            self.assertEqual(result.cues[1].plan.track_lane, "lane:alt")
            self.assertEqual(result.cues[1].plan.fade_in_seconds, 3.5)
            self.assertEqual(result.cues[1].placement.track_index, 5)

    def test_generate_from_timeline_honors_stop_marker_and_structured_prompt_fields(self) -> None:
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = [deepcopy(context.markers[0]), deepcopy(context.markers[1])]
        context.markers[0].frame_offset = 0
        context.markers[0].absolute_frame = context.start_frame
        context.markers[0].relative_seconds = 0.0
        context.markers[0].timestamp = "00:00:00.000"
        context.markers[0].name = "Music Track 1: Main Theme"
        context.markers[0].note = (
            "Genre = Western, Scifi\n"
            "Instruments = Banjo, Synth Pad\n"
            "BPM = 85\n"
            "Key = D minor\n"
            "Mood = nostalgic, eerie\n"
            "Song_Structure = Intro, Verse\n"
            "Input = Eine sanfte Banjo-Melodie"
        )

        context.markers[1].frame_offset = int(round(4.0 * context.frame_rate))
        context.markers[1].absolute_frame = context.start_frame + context.markers[1].frame_offset
        context.markers[1].relative_seconds = 4.0
        context.markers[1].timestamp = "00:00:04.000"
        context.markers[1].name = "Music Track 1: Main Theme"
        context.markers[1].note = "[Stop]\nInput = Wird schneller und endet hart"

        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-main").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            result = service.generate_from_timeline(
                api_key="secret",
                gemini_settings=GeminiSettings(),
                music_settings=GeminiMusicSettings(
                    model="lyria-3-pro-preview",
                    vocals_mode="instrumental",
                    output_format="mp3",
                    use_marker_images=False,
                    crossfade_seconds=2.0,
                ),
                timeline_context=context,
                preview_path=preview_path,
                output_directory=temp_dir,
            )

            self.assertEqual(len(result.cues), 1)
            self.assertAlmostEqual(result.cues[0].plan.requested_duration_seconds, 4.0, places=2)
            self.assertIn("Genre = Western, Scifi", result.cues[0].plan.prompt)
            self.assertIn("Instruments = Banjo, Synth Pad", result.cues[0].plan.prompt)
            self.assertIn("BPM = 85", result.cues[0].plan.prompt)
            self.assertIn("Key/Scale = D minor", result.cues[0].plan.prompt)
            self.assertIn("Mood = nostalgic, eerie", result.cues[0].plan.prompt)
            self.assertIn("Structure = Intro, Verse", result.cues[0].plan.prompt)
            self.assertIn("Structured inputs:", result.cues[0].plan.prompt)
            self.assertIn("Structured prompt JSON:", result.cues[0].plan.prompt)
            self.assertIn('"genres": [', result.cues[0].plan.prompt)
            self.assertIn('"instruments": [', result.cues[0].plan.prompt)
            self.assertIn('"bpm": 85', result.cues[0].plan.prompt)
            self.assertIn('"key_scale": "D minor"', result.cues[0].plan.prompt)
            self.assertIn('"stop_timestamp": "00:00:04.000"', result.cues[0].plan.prompt)
            self.assertIn('"stop_mode": "natural"', result.cues[0].plan.prompt)
            self.assertIn("Input = Eine sanfte Banjo-Melodie", result.cues[0].plan.prompt)
            self.assertIn("Input = Wird schneller und endet hart", result.cues[0].plan.prompt)
            self.assertIn("resolve naturally and end exactly at 00:00:04.000", result.cues[0].plan.prompt)
            self.assertIn("avoid abrupt truncation", result.cues[0].plan.prompt)

    def test_generate_from_timeline_honors_stophard_with_abrupt_instruction(self) -> None:
        adapter = MockResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = [deepcopy(context.markers[0]), deepcopy(context.markers[1])]
        context.markers[0].frame_offset = 0
        context.markers[0].absolute_frame = context.start_frame
        context.markers[0].relative_seconds = 0.0
        context.markers[0].timestamp = "00:00:00.000"
        context.markers[0].name = "Music Track 1: Main Theme"
        context.markers[0].note = "Input = kontinuierlicher Aufbau"

        context.markers[1].frame_offset = int(round(4.0 * context.frame_rate))
        context.markers[1].absolute_frame = context.start_frame + context.markers[1].frame_offset
        context.markers[1].relative_seconds = 4.0
        context.markers[1].timestamp = "00:00:04.000"
        context.markers[1].name = "Music Track 1: Main Theme"
        context.markers[1].note = "[StopHard]"

        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "Cue structure"},
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-main").decode("ascii"),
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            result = service.generate_from_timeline(
                api_key="secret",
                gemini_settings=GeminiSettings(),
                music_settings=GeminiMusicSettings(
                    model="lyria-3-pro-preview",
                    vocals_mode="instrumental",
                    output_format="mp3",
                    use_marker_images=False,
                    crossfade_seconds=2.0,
                ),
                timeline_context=context,
                preview_path=preview_path,
                output_directory=temp_dir,
            )

            self.assertEqual(len(result.cues), 1)
            self.assertAlmostEqual(result.cues[0].plan.requested_duration_seconds, 4.0, places=2)
            self.assertIn('"stop_mode": "hard"', result.cues[0].plan.prompt)
            self.assertIn("stop exactly at 00:00:04.000 with an abrupt hard cut", result.cues[0].plan.prompt)
            self.assertIn("Do not add tail reverb", result.cues[0].plan.prompt)

    def test_generate_from_timeline_writes_all_cues_before_first_import_failure(self) -> None:
        adapter = _FailingImportResolveAdapter()
        context = adapter.get_current_timeline_context()
        context.markers = [deepcopy(context.markers[0]), deepcopy(context.markers[1])]
        context.markers[0].frame_offset = 0
        context.markers[0].absolute_frame = context.start_frame
        context.markers[0].relative_seconds = 0.0
        context.markers[0].timestamp = "00:00:00.000"
        context.markers[0].name = "Cue A"
        context.markers[1].frame_offset = int(round(4.0 * context.frame_rate))
        context.markers[1].absolute_frame = context.start_frame + context.markers[1].frame_offset
        context.markers[1].relative_seconds = 4.0
        context.markers[1].timestamp = "00:00:04.000"
        context.markers[1].name = "Cue B"

        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-a").decode("ascii"),
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                ),
                _FakeResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/mpeg",
                                                "data": b64encode(b"audio-b").decode("ascii"),
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        service = GeminiMusicGenerationService(
            resolve_adapter=adapter,
            frame_extractor=_FakeFrameExtractor(),
            audio_processor=_FakeAudioProcessor(),
            session=session,
        )

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.mp4"
            preview_path.write_bytes(b"mp4-data")

            with self.assertRaises(GeminiMusicGenerationError):
                service.generate_from_timeline(
                    api_key="secret",
                    gemini_settings=GeminiSettings(),
                    music_settings=GeminiMusicSettings(
                        model="lyria-3-pro-preview",
                        vocals_mode="instrumental",
                        output_format="mp3",
                        use_marker_images=False,
                    ),
                    timeline_context=context,
                    preview_path=preview_path,
                    output_directory=temp_dir,
                )

            output_root = Path(temp_dir) / "mock-project" / "assembly-cut"
            generated_files = sorted(output_root.glob("*.mp3"))
            self.assertEqual(len(generated_files), 2)
