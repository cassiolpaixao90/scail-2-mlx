"""Create source/candidate visual review pairs without claiming pose equivalence."""
import argparse
import json
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scail2_mlx.utils.media import probe_video


def selected_frames(path, indices):
    result = {}
    with av.open(str(path)) as container:
        for i, frame in enumerate(container.decode(video=0)):
            if i in indices:
                result[i] = frame.to_image()
            if i >= max(indices):
                break
    if len(result) != len(indices):
        raise ValueError('Could not decode all requested review frames')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    source, candidate = probe_video(args.source), probe_video(args.candidate)
    if (source.width,source.height,source.fps) != (candidate.width,candidate.height,candidate.fps):
        raise ValueError('Candidate framing or FPS differs from source')
    if not 0 < candidate.frames <= source.frames:
        raise ValueError('Unexpected candidate length')
    out = Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=False)
    indices = sorted(set(np.linspace(0,candidate.frames-1,9).round().astype(int).tolist()))
    originals = selected_frames(args.source, indices)
    results = selected_frames(args.candidate, indices)
    thumb_w, thumb_h = 180, round(180*source.height/source.width)
    pair_w, pair_h = 2*thumb_w, thumb_h+28
    sheet = Image.new('RGB',(pair_w*3,pair_h*3),'#161616')
    draw = ImageDraw.Draw(sheet)
    for k,i in enumerate(indices):
        if k in (0,len(indices)//2,len(indices)-1):
            originals[i].save(out/f'source-frame-{i}.png')
            results[i].save(out/f'candidate-frame-{i}.png')
        x,y = (k%3)*pair_w,(k//3)*pair_h
        sheet.paste(originals[i].resize((thumb_w,thumb_h)),(x,y))
        sheet.paste(results[i].resize((thumb_w,thumb_h)),(x+thumb_w,y))
        draw.text((x+4,y+thumb_h+4),f'{i/source.fps:.2f}s | original / candidate',fill='white')
    sheet.save(out/'comparison-contact-sheet.png')
    report = {'source_frames':source.frames,'candidate_frames':candidate.frames,
        'fps':str(candidate.fps),'duration_seconds':float(candidate.duration),
        'dimensions':[candidate.width,candidate.height],'audio_present':candidate.has_audio,
        'review_frames':indices,'full_duration':candidate.frames==source.frames,
        'pose_fidelity_approved':False,'identity_approved':False,
        'note':'Metadata and visual review artifact only. Requires human/anatomy inspection.'}
    (out/'comparison.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
