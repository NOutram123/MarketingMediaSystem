from fastapi.testclient import TestClient

from backend.main import app, get_store
from backend.schemas import BrandKit
from backend.store import Store
from backend.voices import english_voices, voice_language


def test_installed_english_voices_and_project_choice(tmp_path):
    options = english_voices()
    assert any(item['id'] == 'af_sarah' and item['language'] == 'en-us' for item in options)
    assert any(item['id'] == 'bf_emma' and item['language'] == 'en-gb' for item in options)
    assert any(item['id'] == 'bm_george' and item['language'] == 'en-gb' for item in options)
    assert voice_language('not_installed') is None

    store = Store(tmp_path)
    project = store.create_project('Voice test', 'A short berry advertisement.',
                                   BrandKit(product_name='Berry').model_dump())
    root = store.project_dir(project)
    for kind, relative in [('draft_clip', 'local_drafts/video/clip.mp4'),
                           ('narration', 'local_drafts/audio/narration.wav'),
                           ('captions', 'captions/current.srt'),
                           ('rough_cut', 'local_drafts/video/current.mp4')]:
        (root / relative).write_bytes(b'fixture')
        store.add_asset(project['id'], kind, 'fixture', relative)

    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        assert any(item['id'] == 'bf_emma' for item in client.get('/api/voices').json())
        response = client.put(f'/api/projects/{project["id"]}/voice', json={'voice_id': 'bf_emma'})
        assert response.status_code == 200
        updated = response.json()
        assert updated['narration_voice'] == 'bf_emma'
        assert next(a for a in updated['assets'] if a['kind'] == 'draft_clip')['status'] == 'CREATED'
        assert all(a['status'] == 'SUPERSEDED' for a in updated['assets'] if a['kind'] in
                   ('narration', 'captions', 'rough_cut'))
        assert client.put(f'/api/projects/{project["id"]}/voice',
                          json={'voice_id': 'not_installed'}).status_code == 409
    finally:
        app.dependency_overrides.clear()
