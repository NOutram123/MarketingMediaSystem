from io import BytesIO
import asyncio

from fastapi.testclient import TestClient
from PIL import Image

from backend.local_media import reference_direction
from backend.jobs import JobRunner
from backend.config import Settings
from backend.main import app, get_store
from backend.schemas import BrandKit, ClaimCandidates, ShotUpdate
from backend.store import Store
from backend.treatment import extract_treatment


def scene(purpose, duration):
    return ShotUpdate(purpose=purpose, visual=f'{purpose} appears inside a vein', camera='Slow push',
                      duration_seconds=duration, narration='Continue the narration',
                      image_prompt=f'{purpose} inside a vein', video_prompt=f'Follow {purpose} inside a vein').model_dump()


def test_manual_direction_variable_scenes_reference_suggestion_and_revision(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        made = client.post('/api/projects', json={
            'title': 'Character film', 'brief': 'A 15-second story for adults.',
            'treatment_notes': 'Concept: PolyPhenol travels through a vein. Scene one: 6 seconds.',
            'brand': {'product_name': 'SpiceBerry'}}).json()
        pid = made['id']
        assert made['treatment_notes'].startswith('Concept:')
        assert client.post(f'/api/projects/{pid}/approvals/brief', json={'approve': True}).status_code == 200
        direction = client.put(f'/api/projects/{pid}/direction', json={
            'concept': 'A journey through a vein',
            'script': 'Meet PolyPhenol as she travels through the body and discovers the story behind SpiceBerry.'})
        assert direction.status_code == 200
        assert client.post(f'/api/projects/{pid}/approvals/concept', json={'approve': True}).status_code == 200

        shots = [scene('PolyPhenol', 6), scene('PolyPhenol', 9)]
        storyboard = client.put(f'/api/projects/{pid}/storyboard', json=shots)
        assert storyboard.status_code == 200
        assert client.post(f'/api/projects/{pid}/approvals/storyboard', json={'approve': True}).status_code == 200

        buffer = BytesIO()
        Image.new('RGB', (64, 64), '#8844aa').save(buffer, format='PNG')
        upload = client.post(f'/api/projects/{pid}/references',
                             files={'file': ('polyphenol.png', buffer.getvalue(), 'image/png')},
                             data={'role': 'character', 'description': 'PolyPhenol wearing a violet outfit'})
        assert upload.status_code == 201
        aid = upload.json()['id']
        suggestion = client.get(f'/api/projects/{pid}/reference-suggestions').json()
        shot_id = storyboard.json()['shots'][0]['id']
        assert suggestion[shot_id][0]['asset_id'] == aid
        assert store.get_project(pid)['shot_references'] == []  # suggestions never assign themselves
        attached = client.put(f'/api/projects/{pid}/shots/{shot_id}/references/{aid}',
                              params={'guidance': 'Keep her violet outfit.'})
        assert attached.status_code == 200
        assert 'violet outfit' in reference_direction(attached.json(), attached.json()['shots'][0])

        root = store.project_dir(made)
        old_file = root / 'local_drafts/video/old.mp4'
        old_file.write_bytes(b'old draft')
        old = store.add_asset(pid, 'draft_clip', 'fixture', old_file.relative_to(root), shot_id=shot_id)
        reopened = client.post(f'/api/projects/{pid}/approvals/concept', json={'approve': False})
        assert reopened.status_code == 200
        assert reopened.json()['shots'] == []
        assert next(a for a in reopened.json()['assets'] if a['id'] == old['id'])['status'] == 'SUPERSEDED'
        assert old_file.read_bytes() == b'old draft'

        changed = client.put(f'/api/projects/{pid}/direction', json={
            'concept': 'PolyPhenol and the product',
            'script': 'Meet PolyPhenol. She travels through the body and introduces the ingredients in SpiceBerry.'})
        assert changed.status_code == 200
        assert client.post(f'/api/projects/{pid}/approvals/concept', json={'approve': True}).status_code == 200
        replacement = client.put(f'/api/projects/{pid}/storyboard', json=[scene('PolyPhenol', 15)])
        assert replacement.status_code == 200
        assert len(replacement.json()['shots']) == 1
    finally:
        app.dependency_overrides.clear()


def test_delete_project_removes_records_and_files(tmp_path):
    store = Store(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        project = store.create_project('Disposable', 'A fifteen-second film.', BrandKit(product_name='Berry').model_dump())
        pid = project['id']
        root = store.project_dir(project)
        source = root / 'local_drafts/video/source.mp4'
        derived = root / 'local_drafts/video/derived.mp4'
        source.write_bytes(b'a')
        derived.write_bytes(b'b')
        first = store.add_asset(pid, 'rough_cut', 'fixture', source.relative_to(root))
        store.add_asset(pid, 'rough_cut', 'fixture', derived.relative_to(root), source_asset_id=first['id'])
        assert client.delete(f'/api/projects/{pid}').status_code == 204
        assert client.get(f'/api/projects/{pid}').status_code == 404
        assert not root.exists()
    finally:
        app.dependency_overrides.clear()


def test_claim_suggestions_are_review_only(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Claim review', 'A 15-second advert about berry flavour.',
                                   BrandKit(product_name='SpiceBerry', description='A berry-flavoured supplement.').model_dump())

    class MockOrchestrator:
        def structured(self, prompt, schema, profile):
            assert schema is ClaimCandidates
            assert 'berry-flavoured supplement' in prompt
            return {'result': ClaimCandidates(candidates=['Berry-flavoured supplement']),
                    'response_id': 'claims-mock', 'model': 'mock', 'usage': {}}

    job = store.create_job(project['id'], 'openai_claim_suggestions', {})
    asyncio.run(JobRunner(store, Settings(_env_file=None), MockOrchestrator()).run_job(store.claim_job()))
    updated = store.get_project(project['id'])
    assert store.get_job(job['id'])['result']['candidates'] == ['Berry-flavoured supplement']
    assert updated['brand']['approved_claims'] == []
    assert updated['approvals']['brief']['status'] == 'PENDING'


def test_explicit_treatment_sections_are_extracted_for_review():
    notes = '''## Core Idea
A berry character travels through the body.
---
## 1. OPEN
**0–6 sec**
The berry enters the bloodstream.
### Voiceover
> "Meet our berry character."
---
# 2. DISCOVERY
**6–15 sec**
The berry meets a product bottle.
### Voiceover
> "Discover the story behind the ingredients."
---
# Visual Direction
Deep purple colours.
'''
    extracted = extract_treatment(notes)
    assert extracted['concept'] == 'A berry character travels through the body.'
    assert [shot['duration_seconds'] for shot in extracted['shots']] == [6, 9]
    assert 'Meet our berry character' in extracted['script']
    assert 'Visual Direction' not in extracted['shots'][-1]['visual']
    assert extracted['warnings'] == []
