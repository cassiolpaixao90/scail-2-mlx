"""Reproducible video cases and evidence-bound reviews. No model imports."""
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .media import probe_video

CHECKS = ('identity_face', 'hands_fingers', 'body_anatomy', 'pose_timing',
          'camera_framing', 'background', 'temporal_consistency', 'image_detail')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def asset(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': digest(path)}


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')


def metadata(path):
    v = probe_video(path)
    return dict(width=v.width, height=v.height, fps=str(v.fps), frames=v.frames,
                duration_seconds=float(v.duration), has_audio=v.has_audio)


def initialize(case_dir, source, reference, name):
    from PIL import Image
    source_asset, reference_asset = asset(source), asset(reference)
    with Image.open(reference) as image:
        reference_asset['size'] = list(image.size)
        image.verify()
    info = metadata(source)
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=False)
    case = {'schema_version': 1, 'name': name,
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'source': source_asset, 'reference': reference_asset,
            'contract': info, 'background_policy': 'preserve_source',
            'critical_source_frames': sorted(set(round((info['frames']-1)*i/4) for i in range(5))),
            'critical_frames_note': 'Initial uniform sample; add exercise-specific occlusions and transitions before generation.'}
    write_new(case_dir/'case.json', case)
    return case


def record(case_dir, run_id, stage, candidate, settings):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', run_id):
        raise ValueError('Run ID must be a simple lowercase name')
    if stage not in ('smoke', 'preview', 'final'):
        raise ValueError('Unknown stage')
    required = {'backend', 'model', 'model_revision', 'code_revision', 'native_size',
                'source_start_frame', 'frame_count', 'parameters', 'prompt', 'hypothesis'}
    if required - settings.keys():
        raise ValueError(f'Missing settings: {sorted(required-settings.keys())}')
    case_dir = Path(case_dir)
    case = read(case_dir/'case.json')
    start, count = settings['source_start_frame'], settings['frame_count']
    if type(start) is not int or type(count) is not int or start < 0 or count < 1 or start+count > case['contract']['frames']:
        raise ValueError('Invalid source frame range')
    if len(settings['native_size']) != 2 or any(type(n) is not int or n <= 0 for n in settings['native_size']):
        raise ValueError('native_size must contain two positive integers')
    if stage == 'final' and (start != 0 or count != case['contract']['frames']):
        raise ValueError('Final runs must cover the entire source')
    candidate_asset = asset(candidate)
    if candidate_asset['path'] in (case['source']['path'], case['reference']['path']):
        raise ValueError('Candidate cannot be an input')
    conditions = {name: asset(path) for name, path in settings.get('conditioning_files', {}).items()}
    run = {'schema_version': 1, 'run_id': run_id, 'stage': stage,
           'case_sha256': digest(case_dir/'case.json'), 'candidate': candidate_asset,
           'candidate_metadata': metadata(candidate), 'settings': settings,
           'conditioning_assets': conditions}
    write_new(case_dir/'runs'/run_id/'run.json', run)
    return run


def review_template(case_dir, run_id):
    case_dir = Path(case_dir)
    case, run = read(case_dir/'case.json'), read(case_dir/'runs'/run_id/'run.json')
    checks = CHECKS + (('audio_sync',) if case['contract']['has_audio'] else ())
    return {'run_sha256': digest(case_dir/'runs'/run_id/'run.json'),
            'candidate_sha256': run['candidate']['sha256'], 'reviewer': '',
            'watched_entire_clip': False, 'inspected_frames': [],
            'checks': {key: {'status': 'pending', 'evidence': ''} for key in checks},
            'notes': 'Frame indices are relative to the candidate. Record actual observations; metadata cannot approve anatomy.'}


def unchanged(item):
    try:
        return digest(item['path']) == item['sha256']
    except OSError:
        return False


def audio_packets(path):
    return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
        '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], text=True).strip()


def evaluate(case_dir, run_id, review=None):
    case_dir = Path(case_dir)
    case_path, run_path = case_dir/'case.json', case_dir/'runs'/run_id/'run.json'
    case, run = read(case_path), read(run_path)
    expected, settings = case['contract'], run['settings']
    checks = {'case_unchanged': digest(case_path) == run['case_sha256'],
              'source_unchanged': unchanged(case['source']),
              'reference_unchanged': unchanged(case['reference']),
              'candidate_unchanged': unchanged(run['candidate']),
              'conditioning_unchanged': all(unchanged(a) for a in run['conditioning_assets'].values())}
    actual = metadata(run['candidate']['path'])
    for key in ('width', 'height', 'fps', 'has_audio'):
        checks[key] = actual[key] == expected[key]
    checks['frames'] = actual['frames'] == settings['frame_count']
    full = settings['source_start_frame'] == 0 and settings['frame_count'] == expected['frames']
    if full and expected['has_audio'] and checks['source_unchanged'] and actual['has_audio']:
        checks['audio_packets'] = audio_packets(case['source']['path']) == audio_packets(run['candidate']['path'])
    required = CHECKS + (('audio_sync',) if expected['has_audio'] else ())
    visual = {key: False for key in required}
    review_bound = False
    if review:
        frames = review.get('inspected_frames', [])
        valid_frames = all(type(f) is int and 0 <= f < actual['frames'] for f in frames)
        inspected = set(frames) if valid_frames else set()
        critical = {f-settings['source_start_frame'] for f in case['critical_source_frames']
                    if settings['source_start_frame'] <= f < settings['source_start_frame']+settings['frame_count']}
        review_bound = (review.get('run_sha256') == digest(run_path)
                        and review.get('candidate_sha256') == run['candidate']['sha256']
                        and bool(review.get('reviewer', '').strip())
                        and review.get('watched_entire_clip') is True
                        and valid_frames and len(inspected) >= min(3, actual['frames'])
                        and {0, actual['frames']-1}.issubset(inspected)
                        and critical.issubset(inspected))
        for key in required:
            item = review.get('checks', {}).get(key, {})
            visual[key] = item.get('status') == 'pass' and bool(item.get('evidence', '').strip())
    technical_pass = all(checks.values())
    visual_pass = review_bound and all(visual.values())
    return {'run_id': run_id, 'stage': run['stage'], 'technical_checks': checks,
            'technical_pass': technical_pass, 'review_bound': review_bound,
            'visual_checks': visual, 'visual_pass': visual_pass,
            'eligible_for_delivery': run['stage'] == 'final' and full and technical_pass and visual_pass,
            'note': 'Eligibility depends on the named reviewer observations; this is not automated pose or identity verification.'}
