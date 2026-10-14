"""Source-preserving SCAIL-2 MLX CLI. --preflight never imports the model."""
import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "refs" / "mlx-video"))

from scail2_mlx.utils.media import ensure_new_output, export_candidate, fit_box, probe_video
from scail2_mlx.utils.segments import plan_segments


def _resize(frames, target_h, target_w, mask=False):
    import numpy as np
    from PIL import Image
    _, h, w, _ = frames.shape
    left, top, width, height = fit_box(w, h, target_w, target_h)
    output = np.zeros((len(frames), target_h, target_w, 3), dtype=np.uint8)
    method = Image.Resampling.NEAREST if mask else Image.Resampling.BICUBIC
    for i, frame in enumerate(frames):
        output[i, top:top + height, left:left + width] = np.asarray(
            Image.fromarray(frame).resize((width, height), method)
        )
    return output


def _load_image(path, h, w, mask=False):
    import numpy as np
    from PIL import Image
    with Image.open(path) as image:
        frames = np.asarray(image.convert("RGB"))[None]
    image = _resize(frames, h, w, mask)[0]
    return (image.astype(np.float32).transpose(2, 0, 1) - 127.5) / 127.5


def _load_video(path, h, w, count, mask=False):
    import av
    import numpy as np
    frames = []
    with av.open(str(path)) as container:
        for frame in container.decode(video=0):
            frames.append(frame.to_ndarray(format="rgb24"))
            if len(frames) == count:
                break
    if len(frames) != count:
        raise ValueError(f"Expected {count} frames in {path}, decoded {len(frames)}")
    frames = _resize(np.stack(frames), h, w, mask)
    return (frames.astype(np.float32).transpose(0, 3, 1, 2) - 127.5) / 127.5


def preflight(args):
    source = Path(args.source_video or args.pose)
    inputs = [source, args.image, args.mask_image, args.pose, args.mask_video]
    for path in inputs:
        if not Path(path).is_file():
            raise FileNotFoundError(path)
    ensure_new_output(args.save_file, inputs)
    if min(args.target_h, args.target_w) <= 0 or args.target_h % 32 or args.target_w % 32:
        raise ValueError("Target dimensions must be positive multiples of 32")
    if args.sample_steps < 1 or not 0 < args.memory_limit_gb <= 64:
        raise ValueError("Positive steps and an MLX memory limit in (0, 64] GiB are required")
    if not 0 <= args.cache_limit_gb <= args.memory_limit_gb:
        raise ValueError("Cache limit must be within the MLX memory limit")
    info, pose, mask = (probe_video(path) for path in [source, args.pose, args.mask_video])
    for name, control in [("pose", pose), ("mask", mask)]:
        if (control.frames, control.fps, control.width, control.height) != (
            info.frames, info.fps, info.width, info.height
        ):
            raise ValueError(f"{name} must match source frame count, FPS and dimensions")
    from PIL import Image
    with Image.open(args.image) as image, Image.open(args.mask_image) as image_mask:
        if image.size != image_mask.size:
            raise ValueError("Reference image and reference mask dimensions differ")
    count = info.frames if args.max_frames is None else args.max_frames
    if not 0 < count <= info.frames:
        raise ValueError("max-frames must be positive and no larger than the source")
    segments = plan_segments(count, args.segment_len, args.segment_overlap)
    report = {
        "source": str(source.resolve()), "source_width": info.width, "source_height": info.height,
        "fps": str(info.fps), "frames": count, "duration": float(count / info.fps),
        "source_frames": info.frames, "source_has_audio": info.has_audio,
        "preserve_audio": not args.no_audio, "model_size": [args.target_w, args.target_h],
        "content_box": fit_box(info.width, info.height, args.target_w, args.target_h),
        "segments": [asdict(segment) for segment in segments],
        "memory_limit_gib": args.memory_limit_gb,
        "weights_present": all((Path(args.weights_dir) / n).is_file() for n in
                               ["dit.safetensors", "umt5.safetensors", "clip.safetensors", "vae.safetensors"]),
        "visual_approval": False, "note": "Technical preflight only; poses and masks require visual review."
    }
    return source, info, count, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--weights-dir", default="weights/mlx")
    p.add_argument("--tokenizer-dir", default="weights/SCAIL-2/umt5-xxl")
    for name in ["image", "mask-image", "pose", "mask-video"]:
        p.add_argument("--" + name, required=True)
    p.add_argument("--source-video", help="Original video providing timing, dimensions and audio")
    p.add_argument("--prompt", default="")
    p.add_argument("--replace-flag", action="store_true")
    p.add_argument("--target-h", type=int, required=True)
    p.add_argument("--target-w", type=int, required=True)
    p.add_argument("--sample-solver", default="unipc", choices=["unipc", "dpm++"])
    p.add_argument("--sample-steps", type=int, default=40)
    p.add_argument("--sample-shift", type=float, default=5.0)
    p.add_argument("--sample-guide-scale", type=float, default=5.0)
    p.add_argument("--segment-len", type=int, default=81)
    p.add_argument("--segment-overlap", type=int, default=5)
    p.add_argument("--base-seed", type=int, default=42)
    p.add_argument("--max-frames", type=int)
    p.add_argument("--save-file", default="scail2_out.mp4")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--preflight", action="store_true", help="Validate inputs without loading MLX or weights")
    p.add_argument("--memory-limit-gb", type=float, default=56)
    p.add_argument("--cache-limit-gb", type=float, default=2)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    source, info, count, report = preflight(args)
    print(json.dumps(report, indent=2))
    if args.preflight:
        return

    import mlx.core as mx
    import numpy as np
    from scail2_mlx.configs import scail_14B
    from scail2_mlx.scail import SCAIL2Pipeline

    mx.set_memory_limit(int(args.memory_limit_gb * 2**30))
    mx.set_cache_limit(int(args.cache_limit_gb * 2**30))
    try:
        image = _load_image(args.image, args.target_h, args.target_w)
        image_mask = _load_image(args.mask_image, args.target_h, args.target_w, mask=True)
        pose = _load_video(args.pose, args.target_h, args.target_w, count)
        mask = _load_video(args.mask_video, args.target_h, args.target_w, count, mask=True)
        pipeline = SCAIL2Pipeline(scail_14B, args.weights_dir, tokenizer_dir=args.tokenizer_dir)
        video = pipeline.generate(
            args.prompt, mx.array(image), ref_mask_img=mx.array(image_mask),
            pose_video=mx.array(pose), driving_mask_video=mx.array(mask.transpose(1, 0, 2, 3)),
            replace_flag=args.replace_flag, shift=args.sample_shift, sample_solver=args.sample_solver,
            segment_len=args.segment_len, segment_overlap=args.segment_overlap,
            sampling_steps=args.sample_steps, guide_scale=args.sample_guide_scale, seed=args.base_seed,
            cache_limit_bytes=int(args.cache_limit_gb * 2**30),
        )
        out = ((np.array(video).transpose(1, 2, 3, 0) + 1) * 127.5).clip(0, 255).astype(np.uint8)
        if len(out) != count:
            raise RuntimeError("Generation changed the requested number of frames")
        export_candidate(out, args.save_file, source, info, report["content_box"], not args.no_audio)
        logging.info("Saved unreviewed candidate: %s", args.save_file)
        print(f"peak MLX memory: {mx.get_peak_memory() / 2**30:.1f} GiB")
    finally:
        mx.clear_cache()


if __name__ == "__main__":
    main()
