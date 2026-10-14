"""Audit a real source without inference. Local paths/media stay in ignored output.

This roundtrip is NOT a generated human candidate or a motion-quality approval.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import av
import numpy as np
from PIL import Image, ImageDraw

from scail2_mlx.utils.media import export_candidate, fit_box, probe_video
from scail2_mlx.utils.segments import plan_segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    info = probe_video(args.source)
    before = hashlib.sha256(args.source.read_bytes()).hexdigest()
    chosen = sorted(set([0, info.frames - 1] + [round((info.frames - 1) * i / 11) for i in range(12)]))
    thumbs, frames = [], []
    # Moderate resolution for media-contract verification; never claimed as final quality.
    model_w, model_h = 288, 512
    box = fit_box(info.width, info.height, model_w, model_h)
    left, top, width, height = box
    with av.open(str(args.source)) as container:
        for i, frame in enumerate(container.decode(video=0)):
            image = frame.to_image().convert("RGB")
            resized = Image.new("RGB", (model_w, model_h))
            resized.paste(image.resize((width, height)), (left, top))
            frames.append(np.asarray(resized))
            if i in chosen:
                thumb = image.copy()
                thumb.thumbnail((180, 320))
                tile = Image.new("RGB", (180, 344), "#202020")
                tile.paste(thumb, ((180 - thumb.width) // 2, 0))
                ImageDraw.Draw(tile).text((6, 324), f"frame {i} | {float(i / info.fps):.3f}s", fill="white")
                thumbs.append(tile)
    sheet = Image.new("RGB", (180 * 6, 344 * 2), "#202020")
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((i % 6) * 180, (i // 6) * 344))
    sheet.save(args.output_dir / "source-contact-sheet.png")
    output = args.output_dir / "technical-roundtrip-NOT-human.mp4"
    actual = export_candidate(np.stack(frames), output, args.source, info, box)
    def audio_hash(path):
        return hashlib.sha256(subprocess.check_output([
            "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "adts", "-"
        ])).hexdigest()
    report = {
        "validation": "media contract only; no generative model executed",
        "human_candidate_generated": False, "motion_quality_approved": False,
        "source_sha256": before, "source_unchanged": before == hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "frames": actual.frames, "fps": str(actual.fps), "duration": float(actual.duration),
        "dimensions": [actual.width, actual.height], "audio_present": actual.has_audio,
        "aac_payload_identical": audio_hash(args.source) == audio_hash(output) if info.has_audio else None,
        "segments": [{"start": s.start, "end": s.end, "padding": s.padding} for s in plan_segments(info.frames)],
        "source_contact_sheet": str(args.output_dir / "source-contact-sheet.png")
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
