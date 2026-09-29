import asyncio
from io import BytesIO
import pytest

from PIL import Image

from backend.config import Settings
from backend.premium import PremiumRenderer, _estimated_usd, create_quote, fingerprint, preflight, run_resolution
from backend.schemas import BrandKit
from backend.store import Store
from backend.uploads import save_reference


def project_with_storyboard(store):
    project = store.create_project('Cloud evaluation', 'A 15-second product film with three scenes.',
                                   BrandKit(product_name='SpiceBerry', description='A red supplement bottle').model_dump())
    pid = project['id']
    store.review_gate(pid, 'brief', True)
    shots = [{'purpose': f'Scene {n}', 'visual': 'Bottle and a recurring character', 'camera': 'slow push',
              'duration_seconds': 5, 'narration': '', 'image_prompt': 'Bottle',
              'video_prompt': 'The character holds the bottle'} for n in range(3)]
    store.set_plan(pid, {'concept': 'Product story', 'script': 'A continuous product story with one voice.', 'shots': shots})
    store.review_gate(pid, 'concept', True)
    store.set_shots(pid, shots)
    store.review_gate(pid, 'storyboard', True)
    return pid


class FakeProvider:
    def __init__(self):
        self.uploads = 0
        self.estimates = []
        self.submissions = 0

    def credential(self):
        return 'configured'

    async def upload_image(self, path, content_type):
        self.uploads += 1
        assert path.is_file() and content_type == 'image/png'
        return 'https://cdn.example.org/reference.png'

    async def estimate(self, model_path, payload):
        self.estimates.append((model_path, payload))
        return {'usd': '1.25'}

    async def submit(self, model_path, payload):
        self.submissions += 1
        raise AssertionError('An existing request must be polled, not resubmitted')

    async def request_status(self, request_id):
        assert request_id == 'd7e6c0f3-6699-4f6c-bb45-2ad7fd9158ff'
        return {'status': 'completed', 'video': {'url': 'https://cdn.example.org/video.mp4'}}


def test_description_estimate_is_indicative_and_rounded_up():
    result = {'type': 'description', 'pricing_description':
              'For 16:9 video without video input, your request costs roughly $0.2056 per second of generated video at 480p, $0.4622 at 720p, and $1.1372 at 1080p. Actual pricing depends on output dimensions and billable duration.'}
    assert str(_estimated_usd(result, {'resolution': '720p', 'duration': 6, 'image_urls': ['https://example.com/reference.webp']})) == '2.78'
    assert str(_estimated_usd(result, {'resolution': '480p', 'duration': 6, 'image_urls': ['https://example.com/reference.webp']})) == '1.24'
    with pytest.raises(ValueError, match='usable USD price'):
        _estimated_usd(result, {'resolution': '720p', 'duration': 6, 'video_urls': ['https://example.com/clip.mp4']})


def test_quote_uses_real_references_and_needs_approval(tmp_path):
    store = Store(tmp_path)
    pid = project_with_storyboard(store)
    image = Image.new('RGB', (64, 64), 'red')
    data = BytesIO()
    image.save(data, format='PNG')
    asset = save_reference(store, pid, data.getvalue(), 'product.png', 'product', 'Red bottle on white')
    first_shot = store.get_project(pid)['shots'][0]
    store.attach_reference(pid, first_shot['id'], asset['id'], 'Keep the bottle shape')
    store.review_gate(pid, 'storyboard', True)
    provider = FakeProvider()
    quote = asyncio.run(create_quote(store, pid, provider, '480p'))
    assert quote['estimated_usd'] == '3.75'
    assert provider.uploads == 1
    assert quote['scenes'][0]['model_path'].endswith('/reference-to-video')
    assert quote['scenes'][0]['payload']['image_urls'] == ['https://cdn.example.org/reference.png']
    assert all(scene['payload']['resolution'] == '480p' for scene in quote['scenes'])
    assert run_resolution(quote) == '480p'
    assert quote['fingerprint'] != fingerprint(store.get_project(pid), '720p')
    assert all(scene['model_path'].endswith('/text-to-video') for scene in quote['scenes'][1:])
    assert store.get_project(pid)['approvals']['rough_cut']['status'] == 'PENDING'
    approved = store.approve_premium_run(pid, quote['id'], fingerprint(store.get_project(pid), '480p'))
    assert approved['status'] == 'APPROVED'
    assert store.get_project(pid)['approvals']['premium_spend']['status'] == 'APPROVED'
    store.update_shot(pid, first_shot['id'], {**first_shot['data'], 'visual': 'Different scene'})
    assert preflight(store.get_project(pid))['fingerprint'] != quote['fingerprint']


def test_interrupted_submission_needs_review_not_replay(tmp_path):
    store = Store(tmp_path)
    pid = project_with_storyboard(store)
    project = store.get_project(pid)
    scenes = [{'ordinal': shot['ordinal'], 'shot_id': shot['id'],
               'model_path': 'bytedance/seedance-2.5/text-to-video',
               'payload': {'prompt': 'Bottle', 'duration': 5}, 'estimated_usd': '1.25'}
              for shot in project['shots']]
    run = store.create_premium_quote(pid, fingerprint(project), scenes)
    store.approve_premium_run(pid, run['id'], fingerprint(project))
    job = store.create_job(pid, 'premium_render', {'run_id': run['id']})
    store.claim_job()
    store.update_premium_scene(pid, run['id'], 1, 'SUBMITTING')
    store.requeue_interrupted_local_jobs()
    assert store.get_job(job['id'])['status'] == 'NEEDS_REVIEW'
    assert store.get_premium_run(pid, run['id'])['status'] == 'NEEDS_REVIEW'
    released = store.confirm_no_premium_submission(pid, run['id'], 1, fingerprint(store.get_project(pid)))
    assert released['status'] == 'APPROVED'
    assert released['scenes'][0]['status'] == 'PENDING'


def test_saved_request_resumes_polling_without_new_charge(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = project_with_storyboard(store)
    project = store.get_project(pid)
    shot = project['shots'][0]
    run = store.create_premium_quote(pid, fingerprint(project),
                                     [{'ordinal': shot['ordinal'], 'shot_id': shot['id'],
                                       'model_path': 'bytedance/seedance-2.5/text-to-video',
                                       'payload': {'prompt': 'Bottle', 'duration': 5}, 'estimated_usd': '1.25'}])
    store.approve_premium_run(pid, run['id'], fingerprint(project))
    store.update_premium_scene(pid, run['id'], 1, 'RUNNING',
                               request_id='d7e6c0f3-6699-4f6c-bb45-2ad7fd9158ff')
    provider = FakeProvider()

    async def fake_download(url, target):
        target.write_bytes(b'video' * 300)

    monkeypatch.setattr('backend.premium.download_video', fake_download)
    monkeypatch.setattr('backend.local_media.probe', lambda path, settings: {'streams': [{'codec_type': 'video'}]})
    monkeypatch.setattr(PremiumRenderer, 'assemble_evaluation', lambda self, project_id, run_id: {'id': 'assembled'})
    renderer = PremiumRenderer(store, Settings(_env_file=None), provider)
    result = asyncio.run(renderer.render(pid, run['id']))
    assert result['asset_id'] == 'assembled'
    assert provider.submissions == 0
    assert store.get_premium_run(pid, run['id'])['status'] == 'COMPLETED'


def test_price_increase_stops_before_submission(tmp_path):
    store = Store(tmp_path)
    pid = project_with_storyboard(store)
    project = store.get_project(pid)
    shot = project['shots'][0]
    run = store.create_premium_quote(pid, fingerprint(project),
                                     [{'ordinal': shot['ordinal'], 'shot_id': shot['id'],
                                       'model_path': 'bytedance/seedance-2.5/text-to-video',
                                       'payload': {'prompt': 'Bottle', 'duration': 5}, 'estimated_usd': '1.00'}])
    store.approve_premium_run(pid, run['id'], fingerprint(project))
    provider = FakeProvider()  # live estimate would now be USD 1.25
    renderer = PremiumRenderer(store, Settings(_env_file=None), provider)
    with pytest.raises(ValueError, match='price increased'):
        asyncio.run(renderer.render(pid, run['id']))
    assert provider.submissions == 0
    assert store.get_premium_run(pid, run['id'])['status'] == 'NEEDS_REVIEW'
