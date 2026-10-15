"""Approval cannot survive changed inputs, mismatched media or partial reviews."""
import copy
import shutil
import subprocess
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from scail2_mlx.utils.cases import initialize, record, review_template, evaluate


@pytest.fixture
def case(tmp_path):
    source, candidate, reference = (tmp_path/n for n in ('source.mp4','candidate.mp4','reference.png'))
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=64x96:r=30:d=1',
                    '-f','lavfi','-i','sine=frequency=440:duration=1',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
    shutil.copyfile(source,candidate)
    Image.new('RGB',(64,96),'white').save(reference)
    directory = tmp_path/'case'
    initialize(directory,source,reference,'Synthetic test fixture')
    settings = dict(backend='test',model='synthetic',model_revision='test-v1',code_revision='test-v1',
                    native_size=[64,96],source_start_frame=0,frame_count=30,
                    parameters={},prompt='synthetic test',hypothesis='media validation')
    return directory,source,candidate,reference,settings


def approved_review(directory,run_id='r001'):
    # Synthetic fixtures only: exercise the review contract, not real visual approval.
    review = review_template(directory,run_id)
    review.update(reviewer='pytest fixture',watched_entire_clip=True,inspected_frames=[0,7,14,22,29])
    for item in review['checks'].values():
        item.update(status='pass',evidence='Synthetic test fixture observation')
    return review


def test_complete_review_and_exact_media_can_pass(case):
    directory,_,candidate,_,settings = case
    record(directory,'r001','final',candidate,settings)
    result = evaluate(directory,'r001',approved_review(directory))
    assert result['technical_checks']['audio_packets']
    assert result['eligible_for_delivery']


def test_metadata_alone_never_approves_visual_quality(case):
    directory,_,candidate,_,settings = case
    record(directory,'r001','final',candidate,settings)
    result = evaluate(directory,'r001')
    assert result['technical_pass']
    assert not result['visual_pass']
    assert not result['eligible_for_delivery']


@pytest.mark.parametrize('defect',['face','pending','no_playback','no_reviewer','missing_critical_frame','stale_review'])
def test_incomplete_or_failed_reviews_cannot_pass(case,defect):
    directory,_,candidate,_,settings = case
    record(directory,'r001','final',candidate,settings)
    review = approved_review(directory)
    if defect == 'face': review['checks']['identity_face']['status'] = 'fail'
    if defect == 'pending': review['checks']['hands_fingers']['status'] = 'pending'
    if defect == 'no_playback': review['watched_entire_clip'] = False
    if defect == 'no_reviewer': review['reviewer'] = ''
    if defect == 'missing_critical_frame': review['inspected_frames'] = [0,14,29]
    if defect == 'stale_review': review['candidate_sha256'] = 'different'
    assert not evaluate(directory,'r001',review)['eligible_for_delivery']


@pytest.mark.parametrize('target',['source','reference','candidate','conditioning'])
def test_changed_files_invalidate_review(case,target):
    directory,source,candidate,reference,settings = case
    conditioning = directory/'mask.bin'
    conditioning.write_bytes(b'mask v1')
    settings['conditioning_files'] = {'mask':str(conditioning)}
    record(directory,'r001','final',candidate,settings)
    review = approved_review(directory)
    path = {'source':source,'candidate':candidate,'reference':reference,'conditioning':conditioning}[target]
    with path.open('ab') as f: f.write(b'changed')
    result = evaluate(directory,'r001',review)
    assert not result['technical_checks'][target+'_unchanged']
    assert not result['eligible_for_delivery']


def test_wrong_frame_count_and_audio_are_rejected(case):
    directory,_,candidate,_,settings = case
    candidate.unlink()
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=64x96:r=30:d=0.5',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(candidate)],check=True)
    record(directory,'r001','final',candidate,settings)
    result = evaluate(directory,'r001')
    assert not result['technical_checks']['frames']
    assert not result['technical_checks']['has_audio']


def test_preview_never_becomes_delivery_and_records_are_not_overwritten(case):
    directory,_,candidate,_,settings = case
    record(directory,'r001','preview',candidate,settings)
    result = evaluate(directory,'r001',approved_review(directory))
    assert result['technical_pass'] and result['visual_pass']
    assert not result['eligible_for_delivery']
    with pytest.raises(FileExistsError): record(directory,'r001','preview',candidate,settings)
    settings = copy.deepcopy(settings)
    settings['frame_count'] = 15
    with pytest.raises(ValueError): record(directory,'r002','final',candidate,settings)


def test_original_cannot_be_registered_as_candidate(case):
    directory,source,_,_,settings = case
    with pytest.raises(ValueError): record(directory,'r001','final',source,settings)


def test_same_audio_presence_does_not_hide_changed_sound(case):
    directory,_,candidate,_,settings = case
    candidate.unlink()
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=64x96:r=30:d=1',
                    '-f','lavfi','-i','sine=frequency=880:duration=1',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(candidate)],check=True)
    record(directory,'r001','final',candidate,settings)
    result = evaluate(directory,'r001',approved_review(directory))
    assert result['technical_checks']['has_audio']
    assert not result['technical_checks']['audio_packets']
    assert not result['eligible_for_delivery']


def test_review_sheet_uses_matching_source_offset(tmp_path):
    import av
    import numpy as np
    source,candidate = tmp_path/'motion.mp4',tmp_path/'slice.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=64x96:rate=30:duration=1',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(source),'-vf','trim=start_frame=10:end_frame=25,setpts=PTS-STARTPTS',
                    '-an','-r','30','-fps_mode','cfr','-c:v','libx264',str(candidate)],check=True)
    script = Path(__file__).resolve().parents[1]/'scripts/compare_candidate.py'
    review_dir = tmp_path/'review'
    subprocess.run([sys.executable,str(script),'--source',str(source),'--candidate',str(candidate),
                    '--source-start-frame','10','--output-dir',str(review_dir)],check=True,capture_output=True)
    with av.open(str(source)) as container:
        original = [f.to_ndarray(format='rgb24') for f in container.decode(video=0)]
    reviewed = np.asarray(Image.open(review_dir/'source-frame-0.png'))
    assert np.array_equal(reviewed,original[10])
    assert not np.array_equal(reviewed,original[0])
    assert json.loads((review_dir/'comparison.json').read_text())['source_start_frame'] == 10


def test_cli_delivery_gate_exits_nonzero_for_pending_review(case):
    directory,_,candidate,_,settings = case
    record(directory,'r001','final',candidate,settings)
    script = Path(__file__).resolve().parents[1]/'scripts/video_case.py'
    result = subprocess.run([sys.executable,str(script),'validate','--case',str(directory),
        '--run','r001','--output',str(directory/'validation.json'),'--require-delivery'],capture_output=True)
    assert result.returncode == 2
    assert not json.loads((directory/'validation.json').read_text())['eligible_for_delivery']
