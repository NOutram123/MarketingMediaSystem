import asyncio

from fastapi.testclient import TestClient

from backend.duration import detect_duration, infer_duration
from backend.jobs import JobRunner, plan_prompt
from backend.main import app, get_store
from backend.preflight import plan_preview
from backend.schemas import BrandKit, MasterCampaignPlan, ShotPlan
from backend.config import Settings
from backend.store import Store


def test_master_duration_inferred_ahead_of_cutdowns():
    brief = 'Primary duration: **45–60 seconds**\nCut-downs: 30 sec / 15 sec / 6 sec'
    assert infer_duration(brief)[0] == 60
    assert infer_duration('Create a 30-second master.')[0] == 30
    assert infer_duration('No running time specified')[0] == 15
    assert detect_duration('Target-45 second film\nAudience: salon owners')[0] == 45


def test_preflight_does_not_call_missing_brief_duration_a_mismatch(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('No duration in brief', 'Audience: salon owners',
                                   BrandKit(product_name='Berry').model_dump(), target_duration_seconds=45)
    preview = plan_preview(store.get_project(project['id']))
    assert preview['inferred_duration_seconds'] == 45
    assert not any(warning['code'] == 'duration_mismatch' for warning in preview['warnings'])

    store.update_brief(project['id'], 'Target-45 second film\nAudience: salon owners')
    matching = plan_preview(store.get_project(project['id']))
    assert not any(warning['code'] == 'duration_mismatch' for warning in matching['warnings'])

    store.update_brief(project['id'], 'Target: 30-second film')
    conflicting = plan_preview(store.get_project(project['id']))
    assert any(warning['code'] == 'duration_mismatch' for warning in conflicting['warnings'])


def test_project_duration_can_come_from_existing_treatment(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        made = TestClient(app).post('/api/projects', json={
            'title': 'Treatment duration', 'brief': 'A film about natural ingredients.',
            'treatment_notes': 'Primary duration: 60 seconds. Cut-down: 15 seconds.',
            'brand': {'product_name': 'Berry'}})
        assert made.status_code == 201
        assert made.json()['target_duration_seconds'] == 60
    finally:
        app.dependency_overrides.clear()


def test_project_preflight_blocks_conflicting_approved_claims_without_paid_call(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        made = client.post('/api/projects', json={'title': 'Master',
            'brief': 'Primary duration: 45–60 seconds. Cut-downs: 15 sec.',
            'brand': {'product_name': 'Berry', 'approved_claims': ['I would not use yet without checking']}})
        assert made.status_code == 201
        project_id = made.json()['id']
        assert made.json()['target_duration_seconds'] == 60
        preview = client.get(f'/api/projects/{project_id}/plan-preview').json()
        assert preview['expected_shots'] == 10
        assert any(w['code'] == 'approved_claims_conflict' for w in preview['warnings'])
        client.post(f'/api/projects/{project_id}/approvals/brief', json={'approve': True})
        assert client.post(f'/api/projects/{project_id}/plan').status_code == 409
        assert not store.get_project(project_id)['jobs']

        revised = client.put(f'/api/projects/{project_id}/input', json={
            'brief': 'Create a 45-second master film.', 'target_duration_seconds': 45,
            'brand': {'product_name': 'Berry', 'approved_claims': []}})
        assert revised.status_code == 200
        assert revised.json()['target_duration_seconds'] == 45
        assert revised.json()['approvals']['brief']['status'] == 'PENDING'
    finally:
        app.dependency_overrides.clear()


def test_sixty_second_plan_accepts_variable_scenes(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Master', 'Make a 60-second master film.',
        BrandKit(product_name='Berry').model_dump(), target_duration_seconds=60)
    store.review_gate(project['id'], 'brief', True)
    shot = ShotPlan(purpose='Moment', visual='Berry', camera='Pan', duration_seconds=6,
                    narration='A moment.', image_prompt='Berry', video_prompt='Camera pan')
    plan = MasterCampaignPlan(concept='A story', target_audience='Adults', key_message='Berry',
        script='A berry film with a continuous voiceover from start to end.', claims_used=[], shots=[shot] * 10)

    class MockOrchestrator:
        def structured(self, prompt, schema, profile):
            assert schema is MasterCampaignPlan
            assert 'approximately 10 creative scenes' in prompt
            return {'result': plan, 'response_id': 'mock-master', 'model': 'mock', 'usage': {}}

    runner = JobRunner(store, Settings(_env_file=None, openai_api_key='test'), MockOrchestrator())
    store.create_job(project['id'], 'openai_plan', {})
    asyncio.run(runner.run_job(store.claim_job()))
    assert len(store.get_project(project['id'])['plan']['shots']) == 10
    assert plan_preview(store.get_project(project['id']))['target_duration_seconds'] == 60
    assert '60-second' in plan_prompt(store.get_project(project['id']))
