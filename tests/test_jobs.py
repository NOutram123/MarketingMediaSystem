import asyncio

from backend.config import Settings
from backend.jobs import JobRunner
from backend.schemas import BrandKit, CampaignPlan, ShotPlan
from backend.store import Store


def make_project(store):
    project = store.create_project('Plan Test', 'Create a fifteen-second berry drink advert.',
                                   BrandKit(product_name='SpiceBerry', approved_claims=['Berry flavour']).model_dump())
    store.review_gate(project['id'], 'brief', True)
    return project['id']


def test_paid_plan_job_persists_usage_and_requires_concept_approval(tmp_path):
    store = Store(tmp_path)
    project_id = make_project(store)
    shot = ShotPlan(purpose='Introduce bottle', visual='Bottle on table', camera='slow push',
                    duration_seconds=3, narration='A bright berry moment.',
                    image_prompt='Bottle on wood table', video_prompt='Slow push toward bottle')
    plan = CampaignPlan(concept='Bright moment', target_audience='Adults', key_message='Berry flavour',
                        script='A bright berry moment.', claims_used=['Berry flavour'], shots=[shot] * 5)

    class MockOrchestrator:
        def structured(self, prompt, schema, profile):
            assert schema is CampaignPlan
            assert profile.id == 'astra-medium'
            assert 'SpiceBerry' in prompt
            assert 'one continuous' in prompt
            return {'result': plan, 'response_id': 'resp_mock_plan', 'model': 'gpt-6-astra',
                    'usage': {'input_tokens': 100, 'output_tokens': 50,
                              'output_tokens_details': {'reasoning_tokens': 12}}}

    runner = JobRunner(store, Settings(_env_file=None, openai_api_key='test'), MockOrchestrator())
    queued = store.create_job(project_id, 'openai_plan', {})
    asyncio.run(runner.run_job(store.claim_job()))
    finished = store.get_job(queued['id'])
    project = store.get_project(project_id)
    assert finished['status'] == 'SUCCEEDED'
    assert project['plan']['concept'] == 'Bright moment'
    assert project['approvals']['concept']['status'] == 'PENDING'
    with store.connection() as conn:
        usage = conn.execute('SELECT * FROM api_usage WHERE project_id=?', (project_id,)).fetchone()
    assert usage['input_tokens'] == 100 and usage['reasoning_tokens'] == 12


def test_uncertain_paid_request_is_held_for_review(tmp_path):
    store = Store(tmp_path)
    project_id = make_project(store)

    class TimeoutOrchestrator:
        def structured(self, prompt, schema, profile):
            raise TimeoutError('simulated provider timeout')

    runner = JobRunner(store, Settings(_env_file=None, openai_api_key='test'), TimeoutOrchestrator())
    job = store.create_job(project_id, 'openai_plan', {})
    asyncio.run(runner.run_job(store.claim_job()))
    assert store.get_job(job['id'])['status'] == 'NEEDS_REVIEW'
    assert store.claim_job() is None


def test_local_draft_job_is_restartable_and_records_result(tmp_path):
    store = Store(tmp_path)
    project_id = make_project(store)
    store.set_plan(project_id, {'concept': 'Berry', 'shots': [{'purpose': str(i)} for i in range(5)]})
    store.review_gate(project_id, 'concept', True)
    store.set_shots(project_id, [{'purpose': str(i)} for i in range(5)])
    store.review_gate(project_id, 'storyboard', True)

    class MockGenerator:
        async def generate(self, target_id, model_id):
            assert target_id == project_id
            assert model_id == 'ltx-2b'
            return {'relative_path': 'local_drafts/video/rough_cut_v001.mp4', 'asset_id': 'fixture'}

    job = store.create_job(project_id, 'local_draft', {})
    store.claim_job()
    store.requeue_interrupted_local_jobs()
    assert store.get_job(job['id'])['status'] == 'QUEUED'
    runner = JobRunner(store, Settings(_env_file=None), local_generator=MockGenerator())
    asyncio.run(runner.run_job(store.claim_job()))
    assert store.get_job(job['id'])['result']['asset_id'] == 'fixture'
    assert store.get_job(job['id'])['status'] == 'SUCCEEDED'
