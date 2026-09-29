from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from backend.jobs import plan_prompt
from backend.main import app, get_store
from backend.premium import fingerprint
from backend.schemas import BrandKit
from backend.store import Store


def image_bytes():
    output = BytesIO()
    Image.new('RGB', (64, 48), '#834c91').save(output, format='PNG')
    return output.getvalue()


def test_upload_reference_can_guide_plan_and_be_attached_to_a_shot(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        project = store.create_project('Reference Campaign', 'A fifteen-second advert with our existing character.',
                                       BrandKit(product_name='SpiceBerry').model_dump())
        project_id = project['id']
        uploaded = client.post(f'/api/projects/{project_id}/references',
                               files={'file': ('mascot.png', image_bytes(), 'image/png')},
                               data={'role': 'character', 'description': 'Purple owl mascot with round glasses.'})
        assert uploaded.status_code == 201
        asset = uploaded.json()
        assert asset['classification'] == 'SOURCE' and asset['ai_generated'] is False
        assert asset['metadata']['role'] == 'character'
        assert client.get(f'/api/projects/{project_id}/assets/{asset["id"]}/file').content == image_bytes()
        assert 'Purple owl mascot' in plan_prompt(store.get_project(project_id))

        store.review_gate(project_id, 'brief', True)
        store.set_plan(project_id, {'concept': 'Owl', 'shots': [{'purpose': 'Introduce owl', 'duration_seconds': 15}]})
        store.review_gate(project_id, 'concept', True)
        shot_id = store.set_shots(project_id, [{'purpose': 'Introduce owl', 'duration_seconds': 15}])['shots'][0]['id']
        linked = client.put(f'/api/projects/{project_id}/shots/{shot_id}/references/{asset["id"]}',
                            params={'guidance': 'Use at opening.'})
        assert linked.status_code == 200
        assert linked.json()['shot_references'][0]['guidance'] == 'Use at opening.'
        assert Store(tmp_path).get_project(project_id)['shot_references'][0]['asset_id'] == asset['id']

        store.review_gate(project_id, 'storyboard', True)
        root = store.project_dir(project)
        clip_path = root / 'local_drafts/video/shot_01_v001.mp4'
        cut_path = root / 'local_drafts/video/rough_cut_v001.mp4'
        clip_path.write_bytes(b'prior clip')
        cut_path.write_bytes(b'prior cut')
        clip = store.add_asset(project_id, 'draft_clip', 'local_fixture', clip_path.relative_to(root), shot_id=shot_id)
        cut = store.add_asset(project_id, 'rough_cut', 'local_fixture', cut_path.relative_to(root))
        store.review_gate(project_id, 'rough_cut', True)

        other = store.create_project('Other Campaign', 'An unrelated fifteen-second advert.',
                                     BrandKit(product_name='Other').model_dump())
        assert client.put(f'/api/projects/{other["id"]}/shots/{shot_id}/references/{asset["id"]}').status_code == 409
        removed = client.delete(f'/api/projects/{project_id}/shots/{shot_id}/references/{asset["id"]}')
        assert removed.status_code == 200 and removed.json()['shot_references'] == []
        revised = removed.json()
        assert revised['approvals']['storyboard']['status'] == 'PENDING'
        assert revised['approvals']['rough_cut']['status'] == 'PENDING'
        assert next(item for item in revised['assets'] if item['id'] == clip['id'])['status'] == 'SUPERSEDED'
        assert next(item for item in revised['assets'] if item['id'] == cut['id'])['status'] == 'SUPERSEDED'
        assert clip_path.read_bytes() == b'prior clip' and cut_path.read_bytes() == b'prior cut'
        next_clip = root / 'local_drafts/video/shot_01_v002.mp4'
        next_clip.write_bytes(b'new clip')
        assert store.add_asset(project_id, 'draft_clip', 'local_fixture', next_clip.relative_to(root), shot_id=shot_id)['version'] == 2
    finally:
        app.dependency_overrides.clear()


def test_reference_upload_rejects_nonimage_and_wrong_role(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        project = store.create_project('Validation', 'An advert with existing imagery.',
                                       BrandKit(product_name='Product').model_dump())
        url = f'/api/projects/{project["id"]}/references'
        assert client.post(url, files={'file': ('bad.png', b'not an image', 'image/png')}).status_code == 422
        assert client.post(url, files={'file': ('good.png', image_bytes(), 'image/png')},
                           data={'role': 'executable'}).status_code == 422
        assert store.get_project(project['id'])['assets'] == []
    finally:
        app.dependency_overrides.clear()


def test_edit_and_delete_reference_updates_scene_links_and_invalidates_quote(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        project = store.create_project('Edit References', 'A fifteen-second advert with a recurring mascot.',
                                       BrandKit(product_name='SpiceBerry').model_dump())
        pid = project['id']
        first = client.post(f'/api/projects/{pid}/references',
                            files={'file': ('mascot.png', image_bytes(), 'image/png')},
                            data={'role': 'character', 'description': 'Purple mascot'}).json()
        second = client.post(f'/api/projects/{pid}/references',
                             files={'file': ('product.png', image_bytes(), 'image/png')},
                             data={'role': 'product', 'description': 'Bottle'}).json()
        image_path = store.project_dir(project) / first['relative_path']
        store.review_gate(pid, 'brief', True)
        store.set_plan(pid, {'concept': 'Mascot', 'script': 'A short continuous voiceover about the product.'})
        store.review_gate(pid, 'concept', True)
        shot = store.set_shots(pid, [{'purpose': 'Introduce mascot', 'duration_seconds': 15}])['shots'][0]
        store.attach_reference(pid, shot['id'], first['id'], 'Keep the same face')
        store.review_gate(pid, 'storyboard', True)
        before = fingerprint(store.get_project(pid), '480p')

        changed = client.put(f'/api/projects/{pid}/references/{first["id"]}',
                             json={'role': 'style', 'description': 'Purple illustrative mascot'}).json()
        edited = next(asset for asset in changed['assets'] if asset['id'] == first['id'])
        assert edited['metadata']['role'] == 'style'
        assert edited['metadata']['description'] == 'Purple illustrative mascot'
        assert edited['metadata']['original_name'] == 'mascot.png'
        assert image_path.is_file() and changed['shot_references'][0]['asset_id'] == first['id']
        assert changed['approvals']['storyboard']['status'] == 'PENDING'
        assert fingerprint(changed, '480p') != before
        assert client.put(f'/api/projects/{pid}/references/{first["id"]}',
                          json={'role': 'invalid', 'description': 'bad'}).status_code == 422

        deleted = client.delete(f'/api/projects/{pid}/references/{first["id"]}')
        assert deleted.status_code == 200
        assert all(asset['id'] != first['id'] for asset in deleted.json()['assets'])
        assert any(asset['id'] == second['id'] for asset in deleted.json()['assets'])
        assert deleted.json()['shot_references'] == []
        assert not image_path.exists()
        assert client.get(f'/api/projects/{pid}/assets/{first["id"]}/file').status_code == 404
    finally:
        app.dependency_overrides.clear()
