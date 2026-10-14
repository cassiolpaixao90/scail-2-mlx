"""No model weights required: exact timeline, geometry, audio and source safety."""
import hashlib
import subprocess
from fractions import Fraction

import numpy as np
import pytest

from scail2_mlx.utils.media import ensure_new_output, export_candidate, fit_box, probe_video
from scail2_mlx.utils.segments import plan_segments


@pytest.mark.parametrize("count", [1, 2, 4, 5, 64, 65, 80, 81, 82, 156, 157, 158, 197, 198, 199, 1000])
def test_every_source_frame_survives_once(count):
    result = []
    for i, segment in enumerate(plan_segments(count)):
        assert (segment.padded_length - 1) % 4 == 0
        assert 0 <= segment.padding < 4
        frames = list(range(segment.start, segment.end))
        decoded = frames + [frames[-1]] * segment.padding
        decoded = decoded[:segment.end - segment.start]
        result.extend(decoded[5:] if i else decoded)
    assert result == list(range(count))


def test_billgym_198_frames_including_tail():
    assert [(s.start, s.end, s.padding) for s in plan_segments(198)] == [
        (0, 81, 0), (76, 157, 0), (152, 198, 3)
    ]


@pytest.mark.parametrize("args", [(0, 81, 5), (198, 80, 5), (198, 81, 4), (198, 81, 81)])
def test_invalid_temporal_shapes_rejected(args):
    with pytest.raises(ValueError):
        plan_segments(*args)


def test_portrait_is_padded_not_cropped():
    assert fit_box(720, 1280, 736, 1280) == (8, 0, 720, 1280)
    assert fit_box(720, 1280, 288, 512) == (0, 0, 288, 512)


def audio_hash(path):
    return hashlib.sha256(subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "adts", "-"
    ])).hexdigest()


@pytest.mark.parametrize("fps", ["30", "30000/1001"])
@pytest.mark.parametrize("audio", [True, False])
def test_real_encode_preserves_timing_audio_and_source(tmp_path, fps, audio):
    source, output = tmp_path / "source.mp4", tmp_path / "candidate.mp4"
    command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=red:s=64x96:r={fps}:d=1"]
    if audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)]
    subprocess.run(command, check=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    info = probe_video(source)
    frames = np.zeros((info.frames, 96, 64, 3), dtype=np.uint8)
    frames[:, :, :, 0] = 255
    actual = export_candidate(frames, output, source, info, (0, 0, 64, 96))
    assert actual == info
    assert actual.fps == Fraction(fps)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    if audio:
        assert audio_hash(output) == audio_hash(source)
    with pytest.raises(FileExistsError):
        export_candidate(frames, output, source, info, (0, 0, 64, 96))


def test_input_alias_rejected(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")
    alias = tmp_path / "alias.mp4"
    alias.symlink_to(source)
    with pytest.raises(FileExistsError):
        ensure_new_output(alias, [source])
    assert source.read_bytes() == b"original"


def test_mask_resize_preserves_labels():
    from scripts.generate import _resize
    labels = np.zeros((1, 64, 32, 3), dtype=np.uint8)
    labels[:, :, 16:, 0] = 255
    resized = _resize(labels, 96, 64, mask=True)
    assert set(map(tuple, resized.reshape(-1, 3))) == {(0, 0, 0), (255, 0, 0)}
