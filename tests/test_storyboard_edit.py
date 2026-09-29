from fastapi.testclient import TestClient

from backend.main import app, get_store
from backend.schemas import BrandKit, ShotUpdate
from backend.store import Store


def test_storyboard_text_edit_persists_and_requires_new_approval(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Storyboard', 'A fifteen-second berry film.',
                                   BrandKit(product_name='Berry').model_dump())
    project_id = project['id']
    store.review_gate(project_id, 'brief', True)
    original = ShotUpdate(purpose='Hero', visual='Berry on a table', camera='Slow push',
                          duration_seconds=15, narration='A berry moment',
                          image_prompt='Berry on table', video_prompt='Push toward berry')
    store.set_plan(project_id, {'concept': 'A berry', 'script': 'A berry moment.',
                                'shots': [original.model_dump()]})
    store.review_gate(project_id, 'concept', True)
    shot_id = store.set_shots(project_id, [original.model_dump()])['shots'][0]['id']
    store.review_gate(project_id, 'storyboard', True)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        changed = original.model_copy(update={'visual': 'Berry in morning light',
                                               'image_prompt': 'Berry in warm morning light'})
        response = client.put(f'/api/projects/{project_id}/shots/{shot_id}', json=changed.model_dump())
        assert response.status_code == 200
        updated = response.json()
        assert updated['shots'][0]['data']['visual'] == 'Berry in morning light'
        assert updated['plan']['shots'][0]['image_prompt'] == 'Berry in warm morning light'
        assert updated['approvals']['storyboard']['status'] == 'PENDING'
        assert store.get_project(project_id)['shots'][0]['data']['visual'] == 'Berry in morning light'

        image = store.project_dir(updated) / 'local_drafts/images/shot_01.png'
        image.write_bytes(b'existing draft')
        revised_again = client.put(f'/api/projects/{project_id}/shots/{shot_id}', json=original.model_dump())
        assert revised_again.status_code == 200
        assert store.get_project(project_id)['shots'][0]['data']['visual'] == 'Berry on a table'
    finally:
        app.dependency_overrides.clear()
