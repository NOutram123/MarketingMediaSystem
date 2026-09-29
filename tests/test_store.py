import pytest
from fastapi.testclient import TestClient

from backend.main import app, get_store
from backend.schemas import BrandKit, CampaignPlan, ShotPlan, claim_warnings
from backend.store import Store


def test_project_approval_lineage_and_restart(tmp_path):
    store = Store(tmp_path)
    brand = BrandKit(product_name='SpiceBerry', approved_claims=['Bright berry flavour'])
    project = store.create_project('SpiceBerry Launch', 'Create a fifteen-second YouTube product advert.', brand.model_dump())
    project_id = project['id']
    folder = store.project_dir(project)
    assert (folder / 'project.json').is_file()
    assert (folder / 'brand/brand.json').is_file()
    assert project['approvals']['brief']['status'] == 'PENDING'
    with pytest.raises(ValueError):
        store.review_gate(project_id, 'concept', True)

    store.review_gate(project_id, 'brief', True)
    store.set_plan(project_id, {'concept': 'A berry moment', 'script': 'A bright berry moment.'})
    store.review_gate(project_id, 'concept', True)
    store.set_shots(project_id, [{'purpose': 'Hero', 'duration_seconds': 15}])
    store.review_gate(project_id, 'storyboard', True)
    with pytest.raises(ValueError):
        store.review_gate(project_id, 'rough_cut', True)

    first_file = folder / 'local_drafts/video/rough_v001.mp4'
    first_file.write_bytes(b'fixture video one')
    first = store.add_asset(project_id, 'rough_cut', 'local_ffmpeg', 'local_drafts/video/rough_v001.mp4')
    second_file = folder / 'local_drafts/video/rough_v002.mp4'
    second_file.write_bytes(b'fixture video two')
    second = store.add_asset(project_id, 'rough_cut', 'local_ffmpeg', 'local_drafts/video/rough_v002.mp4', source_asset_id=first['id'])
    assert (first['version'], second['version']) == (1, 2)
    assert second['source_asset_id'] == first['id']
    assert second['commercial_use'] is False
    with pytest.raises(ValueError):
        store.add_asset(project_id, 'rough_cut', 'local_ffmpeg', 'local_drafts/video/rough_v002.mp4', commercial_use=True)
    with pytest.raises(ValueError):
        store.add_asset(project_id, 'rough_cut', 'local_ffmpeg', '../outside.mp4')
    store.review_gate(project_id, 'rough_cut', True)

    reopened = Store(tmp_path).get_project(project_id)
    assert reopened['approvals']['rough_cut']['status'] == 'APPROVED'
    assert len(reopened['assets']) == 2
    scripted = store.update_script(project_id, 'A longer continuous voiceover for the whole film.')
    assert scripted['plan']['script'] == 'A longer continuous voiceover for the whole film.'
    assert scripted['approvals']['concept']['status'] == 'PENDING'
    assert scripted['approvals']['storyboard']['status'] == 'PENDING'
    assert all(asset['status'] == 'SUPERSEDED' for asset in scripted['assets'])
    assert first_file.is_file() and second_file.is_file()
    revised = Store(tmp_path).update_brand(project_id, BrandKit(product_name='SpiceBerry', cta='Try it').model_dump())
    assert revised['plan'] is None
    assert revised['approvals']['brief']['status'] == 'PENDING'
    assert len(revised['assets']) == 2  # approved history is retained


def test_local_job_survives_restart(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Restartable Project', 'Make a local draft advert for review.', BrandKit(product_name='Test').model_dump())
    job = store.create_job(project['id'], 'local_draft_image', {'shot_id': 'fixture'})
    assert store.create_job(project['id'], 'local_draft_image', {'shot_id': 'fixture'})['id'] == job['id']
    assert store.claim_job()['id'] == job['id']
    restarted = Store(tmp_path)
    restarted.requeue_interrupted_local_jobs()
    claimed = restarted.claim_job()
    assert claimed['id'] == job['id'] and claimed['attempts'] == 2
    assert restarted.finish_job(job['id'], result={'path': 'local_drafts/images/test.png'})['status'] == 'SUCCEEDED'
    assert restarted.claim_job() is None


def test_interrupted_paid_plan_is_not_automatically_replayed(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Paid Plan', 'Plan a fifteen-second berry advert.', BrandKit(product_name='Test').model_dump())
    job = store.create_job(project['id'], 'openai_plan', {})
    assert store.claim_job()['id'] == job['id']
    reopened = Store(tmp_path)
    reopened.requeue_interrupted_local_jobs()
    assert reopened.get_job(job['id'])['status'] == 'NEEDS_REVIEW'
    assert reopened.claim_job() is None


def test_claim_review_flags_unknown_and_prohibited_claims():
    brand = BrandKit(product_name='SpiceBerry', approved_claims=['Berry flavour'], prohibited_claims=['Cures disease'])
    shot = ShotPlan(purpose='Hero', visual='Bottle', camera='push in', duration_seconds=3,
                    narration='A bright berry moment.', image_prompt='Bottle on table', video_prompt='Camera pushes toward bottle')
    plan = CampaignPlan(concept='Taste', target_audience='Adults', key_message='Fruit flavour',
                        script='A bright berry moment.', claims_used=['Berry flavour', 'Cures disease', 'Boosts immunity'],
                        shots=[shot] * 5)
    warnings = claim_warnings(plan, brand)
    assert len(warnings) == 2
    assert 'Prohibited' in warnings[0]
    assert 'Unapproved' in warnings[1]


def test_project_api_persists_and_enforces_review_order(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        created = client.post('/api/projects', json={
            'title': 'API Project', 'brief': 'Create a fifteen-second advert for a berry drink.',
            'brand': {'product_name': 'SpiceBerry'}, 'profile_id': 'astra-medium',
        })
        assert created.status_code == 201
        project_id = created.json()['id']
        assert client.get(f'/api/projects/{project_id}').json()['title'] == 'API Project'
        assert client.get('/api/projects').json()[0]['id'] == project_id
        assert client.post(f'/api/projects/{project_id}/approvals/concept', json={'approve': True}).status_code == 409
        assert client.post(f'/api/projects/{project_id}/approvals/brief', json={'approve': True}).status_code == 200
        assert client.get('/api/model-profiles').json()['default'] == 'astra-medium'
        assert client.get('/api/projects/missing').status_code == 404
    finally:
        app.dependency_overrides.clear()
