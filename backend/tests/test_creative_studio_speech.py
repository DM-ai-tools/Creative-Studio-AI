import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from app.services.creative_studio_speech import _atempo_filter, _fit_audio_to_window
from app.services.ffmpeg_util import probe_video_duration


class CreativeStudioSpeechTests(unittest.TestCase):
    def test_atempo_filter_supports_large_speedups(self):
        self.assertEqual(_atempo_filter(1.5), "atempo=1.500000")
        self.assertEqual(
            _atempo_filter(4.5),
            "atempo=2.000000,atempo=2.000000,atempo=1.125000",
        )

    def test_long_complete_take_is_fitted_without_clipping_the_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            source = work / "source.wav"
            target = work / "fitted.wav"
            sample_rate = 24000
            source_duration = 2.8
            with wave.open(str(source), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(sample_rate)
                stream.writeframes(
                    b"".join(
                        struct.pack(
                            "<h",
                            int(4000 * math.sin(2 * math.pi * 440 * i / sample_rate)),
                        )
                        for i in range(int(sample_rate * source_duration))
                    )
                )

            _fit_audio_to_window(
                source,
                target,
                duration=source_duration,
                window=1.7,
            )

            fitted_duration = probe_video_duration(target)
            self.assertIsNotNone(fitted_duration)
            self.assertLessEqual(fitted_duration, 1.72)
            self.assertGreater(fitted_duration, 1.4)


if __name__ == "__main__":
    unittest.main()
