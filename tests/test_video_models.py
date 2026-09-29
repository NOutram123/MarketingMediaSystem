import json

from backend.config import ROOT, Settings
from backend.schemas import BrandKit
from backend.store import Store
from backend.video_models import VIDEO_MODELS, require_video_model, video_model_status


def test_model_catalog_requires_complete_files(tmp_path, monkeypatch):
    fixture_files = {'diffusion_models/fixture.safetensors': 4,
                     'text_encoders/fixture.safetensors': 5,
                     'vae/fixture.safetensors': 6}
    monkeypatch.setitem(VIDEO_MODELS, 'wan-5b', {**VIDEO_MODELS['wan-5b'], 'required': fixture_files})
    settings = Settings(_env_file=None, comfyui_models_dir=tmp_path)
    assert all(not item['installed'] for item in video_model_status(settings))
    for name, size in fixture_files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * size)
    assert require_video_model('wan-5b', settings)['width'] == 800
    assert next(item for item in video_model_status(settings) if item['id'] == 'wan-5b')['installed']


def test_switching_video_model_retires_clips_and_cut_but_keeps_frames_and_voice(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Model trial', 'Fifteen-second film', BrandKit(product_name='Berry').model_dump())
    project_id = project['id']
    store.review_gate(project_id, 'brief', True)
    store.set_plan(project_id, {'concept': 'Berry', 'script': 'Berry.', 'shots': [{'purpose': 'Hero'}]})
    store.review_gate(project_id, 'concept', True)
    shot = store.set_shots(project_id, [{'purpose': 'Hero', 'duration_seconds': 15}])['shots'][0]
    store.review_gate(project_id, 'storyboard', True)
    root = store.project_dir(project)
    for kind, relative, shot_id, metadata in (
        ('storyboard_frame', 'local_drafts/images/frame.png', shot['id'], None),
        ('draft_clip', 'local_drafts/video/clip.mp4', shot['id'], {'model_id': 'ltx-2b'}),
        ('narration', 'local_drafts/audio/voice.wav', None, None),
        ('rough_cut', 'local_drafts/video/rough.mp4', None, None),
    ):
        path = root / relative
        path.write_bytes(b'fixture')
        store.add_asset(project_id, kind, 'fixture', path.relative_to(root), shot_id=shot_id, metadata=metadata)
    store.review_gate(project_id, 'rough_cut', True)
    store.reset_video_drafts_for_model(project_id, 'wan-5b')
    assets = {item['kind']: item for item in store.get_project(project_id)['assets']}
    assert assets['draft_clip']['status'] == assets['rough_cut']['status'] == 'SUPERSEDED'
    assert assets['storyboard_frame']['status'] == assets['narration']['status'] == 'CREATED'
    assert store.get_project(project_id)['approvals']['rough_cut']['status'] == 'PENDING'


def test_wan_workflow_uses_supported_dimensions_and_local_weights():
    workflow = json.loads((ROOT / 'workflows/wan_22_5b_i2v_draft.json').read_text(encoding='utf-8'))
    assert workflow['7']['inputs']['width'] % 32 == 0
    assert workflow['7']['inputs']['height'] % 32 == 0
    assert workflow['1']['inputs']['unet_name'] == VIDEO_MODELS['wan-5b']['checkpoint']
    assert workflow['7']['inputs']['start_image'] == ['13', 0]
