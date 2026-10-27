import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.ffmpeg_util import require_ffmpeg
from app.services.ffmpeg_util import probe_video_duration
from app.services.proof_composite import composite_proof_windows


class ProofCompositeTests(unittest.TestCase):
    def test_exact_proof_windows_replace_video_and_keep_square_output(self):
        ffmpeg = require_ffmpeg()
        with tempfile.TemporaryDirectory(prefix="proof-composite-test-") as tmp:
            root = Path(tmp)
            base = root / "base.mp4"
            proof_a = root / "proof-a.png"
            proof_b = root / "proof-b.png"
            saved_output = root / "saved.mp4"
            Image.new("RGB", (640, 360), (220, 25, 25)).save(proof_a)
            Image.new("RGB", (640, 360), (25, 55, 220)).save(proof_b)
            proc = subprocess.run(
                [
                    ffmpeg, "-v", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=320x320:d=2",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-shortest", "-c:v", "libx264", "-c:a", "aac", str(base),
                ],
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="ignore"))

            by_url = {
                "/files/base.mp4": base,
                "/files/proof-a.png": proof_a,
                "/files/proof-b.png": proof_b,
            }

            def save_bytes(*, content, **_kwargs):
                saved_output.write_bytes(content)
                return {"file_url": "/files/saved.mp4"}

            with (
                patch(
                    "app.services.logo_overlay.file_url_to_local_path",
                    side_effect=lambda url: by_url.get(url),
                ),
                patch(
                    "app.services.file_service.file_service.save_bytes",
                    side_effect=save_bytes,
                ),
            ):
                output_url, count = composite_proof_windows(
                    video_url="/files/base.mp4",
                    proof_assets=[
                        {"url": "/files/proof-a.png", "role": "proof"},
                        {"url": "/files/proof-b.png", "role": "proof"},
                    ],
                    proof_scenes=[
                        {"start": 0.0, "end": 1.0, "type": "proof"},
                        {"start": 1.0, "end": 2.0, "type": "proof"},
                    ],
                    tenant_id="test",
                )

            self.assertEqual(output_url, "/files/saved.mp4")
            self.assertEqual(count, 2)
            self.assertTrue(saved_output.is_file())
            self.assertAlmostEqual(probe_video_duration(saved_output) or 0.0, 2.0, delta=0.15)
            frame_a = root / "frame-a.png"
            frame_b = root / "frame-b.png"
            for timestamp, frame in (("0.5", frame_a), ("1.5", frame_b)):
                extract = subprocess.run(
                    [
                        ffmpeg, "-v", "error", "-y", "-ss", timestamp,
                        "-i", str(saved_output), "-frames:v", "1", str(frame),
                    ],
                    capture_output=True,
                )
                self.assertEqual(extract.returncode, 0)
            image_a = Image.open(frame_a).convert("RGB")
            image_b = Image.open(frame_b).convert("RGB")
            self.assertEqual(image_a.size, (1080, 1080))
            self.assertGreater(image_a.getpixel((540, 540))[0], 180)
            self.assertGreater(image_b.getpixel((540, 540))[2], 180)


if __name__ == "__main__":
    unittest.main()
