"""Prepare reviewed, case-specific replacement masks without another ML model.

This heuristic is for the supplied light mannequin/dark mat footage only.
Inspect masks-contact-sheet.png before inference; it is not general segmentation.
"""
import argparse
import json
import subprocess
from pathlib import Path

import av
import cv2
import numpy as np
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True)
    p.add_argument('--reference', required=True)
    p.add_argument('--output-dir', required=True)
    args = p.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    ref = np.asarray(Image.open(args.reference).convert('RGB'))
    h, w = ref.shape[:2]
    # Polygon from the supplied reference, normalized to its 940x1672 canvas.
    points = np.array([(381,142),(450,118),(529,136),(554,203),(550,315),
        (607,353),(659,397),(684,563),(703,716),(697,844),(679,941),
        (645,946),(636,874),(639,769),(623,661),(624,758),(630,971),
        (599,1046),(601,1189),(610,1356),(637,1417),(630,1473),
        (564,1485),(543,1453),(538,1390),(545,1262),(515,1114),
        (483,1011),(446,1020),(412,1145),(400,1301),(396,1396),
        (373,1454),(324,1481),(278,1464),(283,1412),(320,1352),
        (325,1180),(327,1062),(284,980),(294,764),(287,641),
        (276,765),(279,869),(291,933),(257,945),(232,895),(227,796),
        (237,631),(251,447),(285,380),(353,344),(392,317),(381,245)])
    points = np.rint(points * [w / 940, h / 1672]).astype(np.int32)
    silhouette = np.zeros((h, w), np.uint8)
    cv2.fillPoly(silhouette, [points], 1)
    labels = np.where(silhouette, cv2.GC_PR_FGD, cv2.GC_BGD).astype(np.uint8)
    labels[cv2.erode(silhouette, np.ones((19, 19), np.uint8)) > 0] = cv2.GC_FGD
    cv2.grabCut(ref, labels, None, np.zeros((1,65)), np.zeros((1,65)), 3, cv2.GC_INIT_WITH_MASK)
    ref_fg = (labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)
    ref_mask = np.zeros_like(ref)
    ref_mask[ref_fg] = [255, 0, 0]  # no unrelated gym background
    Image.fromarray(ref_mask).save(out / 'reference-mask.png')
    Image.fromarray(ref).save(out / 'reference.png')
    encoder = None
    samples = []
    areas = []
    try:
        with av.open(args.source) as container:
            stream = container.streams.video[0]
            for i, frame in enumerate(container.decode(video=0)):
                rgb = frame.to_ndarray(format='rgb24')
                hh, ww = rgb.shape[:2]
                if encoder is None:
                    encoder = subprocess.Popen(['ffmpeg','-v','error','-n','-f','rawvideo',
                        '-pix_fmt','rgb24','-s',f'{ww}x{hh}','-r',str(stream.average_rate),
                        '-i','pipe:0','-an','-c:v','libx264rgb','-crf','0','-preset','fast',
                        str(out / 'driving-mask.mp4')], stdin=subprocess.PIPE)
                hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
                foreground = ((rgb.min(axis=2) > 100) | ((hsv[:,:,1] > 70) & (hsv[:,:,2] > 100)))
                foreground[:int(hh * .26)] = False  # exclude corner logo
                foreground[int(hh * .80):] = False
                mask = cv2.morphologyEx(foreground.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5,5), np.uint8))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                mask[:] = 0
                for contour in contours:
                    if cv2.contourArea(contour) > 70:
                        cv2.drawContours(mask, [contour], -1, 1, cv2.FILLED)
                # A little room for different physique/clothing while keeping the mat visible.
                mask = cv2.dilate(mask, np.ones((9,9), np.uint8)) > 0
                colored = np.full_like(rgb, 255)  # preserve driving background
                colored[mask] = [255,0,0]
                encoder.stdin.write(colored.tobytes())
                areas.append(float(mask.mean()))
                if i in [0,18,36,54,72,90,107,125,143,161,179,197]:
                    overlay = rgb.copy()
                    overlay[mask] = (rgb[mask] * .5 + np.array([255,0,0]) * .5).astype(np.uint8)
                    samples.append((i, Image.fromarray(overlay)))
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError('Mask encoding failed')
    finally:
        if encoder and encoder.poll() is None:
            encoder.kill()
            encoder.wait()
    sheet = Image.new('RGB', (6*180, 2*344), '#151515')
    draw = ImageDraw.Draw(sheet)
    for j, (index, im) in enumerate(samples):
        x, y = (j % 6)*180, (j//6)*344
        sheet.paste(im.resize((180,320)), (x,y))
        draw.text((x+4,y+324), f'frame {index}', fill='white')
    sheet.save(out / 'masks-contact-sheet.png')
    overlay = ref.copy()
    overlay[ref_fg] = (ref[ref_fg]*.5 + np.array([255,0,0])*.5).astype(np.uint8)
    Image.fromarray(overlay).resize((470,836)).save(out / 'reference-mask-review.png')
    (out / 'preparation.json').write_text(json.dumps({'frames':len(areas),
        'min_mask_fraction':min(areas),'max_mask_fraction':max(areas),
        'method':'case-specific color threshold plus reference polygon/GrabCut',
        'requires_visual_review':True}, indent=2))
    print(out.resolve())


if __name__ == '__main__':
    main()
