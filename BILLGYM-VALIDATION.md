# BillGym: realistic exercise replacement on Apple MLX

The target case is a 720×1280, 30 FPS abdominal exercise: 198 frames, 6.6
seconds, with AAC audio. The character starts lying on a mat and repeatedly
raises the torso and arms. A standing portrait supplies appearance only;
the source video supplies motion, camera and framing.

## Changes

- Process every source frame, including the final partial segment. For this
  case the windows are `[0,81)`, `[76,157)`, `[152,198)`. The last window is
  padded by repeating its last frame three times before the causal VAE and
  trimmed after decoding. Five-frame clean history remains between windows.
- Preserve rational source FPS, original output dimensions and source audio.
  Resizing for inference uses letterboxing and reverses it on export.
  A small inference resolution exported at 720×1280 is still a low-resolution
  preview, not native 720p detail.
- Resize semantic masks with nearest-neighbor sampling.
- Reject mismatched control videos, overwritten inputs/outputs, rotated
  sources and unsupported timing/aspect conventions. Publish a new MP4 only
  after checking its metadata.
- Provide preflight without importing MLX or loading weights, and a separate
  process supervisor for memory and elapsed-time limits. MLX's own memory
  limit is advisory, not a hard cap. Supervisor polling is once per second
  and cannot prevent instantaneous allocation peaks.

## Reproduce

Use the upstream setup and install `.[validation,parity]`. `ffmpeg` and
`ffprobe` must be on PATH. The local validation environment uses Python
3.13.5 and MLX 0.32.4; upstream's recommended Python range may differ.

```sh
python scripts/validate_case.py --source ORIGINAL.mp4 --output-dir validation-local/contract
python scripts/prepare_billgym_case.py --source ORIGINAL.mp4 --reference CHARACTER.png \
  --output-dir validation-local/inputs
```

The preparation script is specifically tuned to the supplied pale mannequin
on a dark mat and the supplied portrait. It is not a general segmentation
model. Review both contact sheets before using a different source. It uses
red for the matching character, white for visible driving background, and
black for the unrelated portrait background, following SCAIL-2 mask semantics.

```sh
python scripts/generate.py \
  --image validation-local/inputs/reference.png \
  --mask-image validation-local/inputs/reference-mask.png \
  --pose ORIGINAL.mp4 --mask-video validation-local/inputs/driving-mask.mp4 \
  --weights-dir weights/SCAIL-2-bf16 --tokenizer-dir weights/umt5-tokenizer \
  --target-w 288 --target-h 512 --max-frames 49 --replace-flag \
  --sample-solver dpm++ --sample-steps 16 \
  --save-file validation-local/preview/candidate.mp4 --preflight
```

For inference, remove `--preflight`, add a detailed description of the
resulting exercise using `--prompt`, and wrap the command in:

```sh
python scripts/run_guarded.py --report validation-local/preview/resources.json \
  --max-rss-gb 64 --min-available-gb 20 --max-swap-growth-gb 2 \
  --timeout-seconds 1800 -- python scripts/generate.py ...
```

The 49-frame preview is a 1.63-second execution/pose test. Full visual approval
requires longer coverage of arm transitions and all 198 frames at an
appropriate native inference resolution. Use a new output name per attempt.

## Evidence and limitations

- Technical roundtrip of the actual source passed: 198 frames, 30 FPS,
  720×1280, source SHA-256 unchanged, and identical extracted AAC payload.
  `technical-roundtrip-NOT-human.mp4` is deliberately not a human candidate.
- 51 parity/media tests passed and 3 VAE checkpoint-dependent tests were
  skipped. Five additional tests exercise the production segment loop with
  lightweight stand-ins, including the 198-frame tail and clean history.
- Local CPU JIT linking failed because the installed linker cannot parse the
  macOS 27 SDK architecture entries. Tests were rerun with
  `mlx.core.disable_compile()`; no tolerances were relaxed. This workaround
  affects the test invocation, not the production GPU configuration.
- Masks were visually inspected at 12 points covering the source. Their
  geometry tracks the mannequin; this does not establish motion fidelity of
  generated humans.
- Human generation and visual approval remain separate gates. Metadata or
  numerical parity cannot prove stable fingers, identity or exact motion.
- This port does not implement the official DPO/relighting LoRA integration.
  It remains an experimental base, not a guarantee of production quality or
  fast generation on an M4 Max.

Base revisions: `xocialize/scail-2-mlx@9ca63749ff9ff261451fc2681c1bd84799950d2a`
and `zai-org/SCAIL-2@78fe19576bb06be96c2375e088574a262a300edb`.
