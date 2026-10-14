"""Source-preserving media contracts. No MLX or model imports."""
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: Fraction
    frames: int
    has_audio: bool

    @property
    def duration(self):
        return Fraction(self.frames, 1) / self.fps


def probe_video(path):
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(path)
    ]))
    streams = data["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    fps = Fraction(video["avg_frame_rate"])
    if fps <= 0 or fps != Fraction(video["r_frame_rate"]):
        raise ValueError("Only constant frame rate sources are supported")
    if video.get("sample_aspect_ratio", "1:1") not in ("1:1", "N/A"):
        raise ValueError("Non-square pixel sources need explicit normalization")
    if any(s.get("rotation", 0) for s in video.get("side_data_list", [])):
        raise ValueError("Rotated sources need explicit normalization")
    return VideoInfo(video["width"], video["height"], fps,
                     int(video["nb_read_frames"]), any(s["codec_type"] == "audio" for s in streams))


def ensure_new_output(output, inputs):
    output = Path(output).resolve()
    if output.exists() or output in [Path(p).resolve() for p in inputs]:
        raise FileExistsError("Output must be a new candidate, separate from every input")
    if output.suffix.lower() != ".mp4":
        raise ValueError("Candidate output must have an .mp4 extension")
    return output


def fit_box(source_w, source_h, target_w, target_h):
    """Letterbox geometry: do not crop limbs or stretch the source."""
    if min(source_w, source_h, target_w, target_h) <= 0:
        raise ValueError("Dimensions must be positive")
    scale = min(target_w / source_w, target_h / source_h)
    w, h = max(1, round(source_w * scale)), max(1, round(source_h * scale))
    return ((target_w - w) // 2, (target_h - h) // 2, w, h)


def export_candidate(frames, output, source, info, content_box, preserve_audio=True):
    """Encode at rational source FPS; remux audio; publish without overwriting."""
    import numpy as np
    from PIL import Image

    output = ensure_new_output(output, [source])
    count = len(frames)
    if not 0 < count <= info.frames:
        raise ValueError("Candidate frame count must be within the source")
    output.parent.mkdir(parents=True, exist_ok=True)
    left, top, width, height = content_box
    with tempfile.TemporaryDirectory(prefix=".candidate-", dir=output.parent) as tmp:
        silent = Path(tmp) / "silent.mp4"
        final = Path(tmp) / "final.mp4"
        command = ["ffmpeg", "-v", "error", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s", f"{info.width}x{info.height}", "-r", str(info.fps), "-i", "pipe:0",
                   "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(silent)]
        with tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=stderr)
            try:
                for frame in frames:
                    image = Image.fromarray(np.asarray(frame, dtype=np.uint8))
                    image = image.crop((left, top, left + width, top + height))
                    image = image.resize((info.width, info.height), Image.Resampling.LANCZOS)
                    process.stdin.write(image.tobytes())
                process.stdin.close()
                if process.wait() != 0:
                    stderr.seek(0)
                    raise RuntimeError(stderr.read().decode(errors="replace"))
            except BaseException:
                process.kill()
                process.wait()
                raise
        duration = float(Fraction(count, 1) / info.fps)
        command = ["ffmpeg", "-v", "error", "-n", "-i", str(silent)]
        if preserve_audio and info.has_audio:
            command += ["-i", str(source), "-map", "0:v:0", "-map", "1:a:0", "-c", "copy"]
        else:
            command += ["-map", "0:v:0", "-c:v", "copy", "-an"]
        command += ["-t", f"{duration:.12f}", "-movflags", "+faststart", str(final)]
        subprocess.run(command, check=True)
        actual = probe_video(final)
        if (actual.width, actual.height, actual.fps, actual.frames, actual.has_audio) != (
            info.width, info.height, info.fps, count, preserve_audio and info.has_audio
        ):
            raise RuntimeError("Encoded candidate failed the media contract")
        # Both paths are on the same filesystem. link fails if output appeared meanwhile.
        os.link(final, output)
    return actual
