import hashlib
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from backend import setup
from backend.config import Settings
from backend.main import app
from backend.setup_assets import download, storage_plan


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, data_dir=tmp_path, openai_api_key='', hf_key='', hf_api_key_id='', hf_api_key_secret='')
    monkeypatch.setattr(setup, 'Settings', lambda **kw: settings)
    monkeypatch.setattr(setup, 'task', {'status': 'IDLE', 'message': '', 'current_bytes': 0, 'total_bytes': 0})
    async def ready():
        return {'ready': True, 'checks': [], 'assets': [], 'models_dir': 'C:/private/models'}
    monkeypatch.setattr(setup, 'local_status', ready)
    monkeypatch.setattr(setup, 'fingerprint', lambda: 'test-fingerprint')
    return TestClient(app), settings


def headers():
    return {'X-Setup-Token': setup.TOKEN, 'Origin': 'http://127.0.0.1:8787'}


def test_completion_requires_real_local_test_and_explicit_api_choices(client):
    web, _ = client
    assert web.post('/api/setup/complete', headers=headers()).status_code == 409
    setup.write_state({'local_test_fingerprint': 'test-fingerprint'})
    assert web.post('/api/setup/complete', headers=headers()).status_code == 409
    for provider in ('openai', 'higgsfield'):
        assert web.post('/api/setup/skip', json={'provider': provider}, headers=headers()).status_code == 200
    assert web.post('/api/setup/complete', headers=headers()).status_code == 200
    assert web.get('/api/setup/status').json()['completed']


def test_cannot_skip_or_complete_missing_local_stack(client, monkeypatch):
    web, _ = client
    assert web.post('/api/setup/skip', json={'provider': 'comfy'}, headers=headers()).status_code == 422
    setup.write_state({'local_test_fingerprint': 'test-fingerprint', 'skipped': ['openai', 'higgsfield']})
    async def missing():
        return {'ready': False}
    monkeypatch.setattr(setup, 'local_status', missing)
    assert web.post('/api/setup/complete', headers=headers()).status_code == 409


def test_csrf_and_validation_do_not_echo_credentials(client):
    web, _ = client
    secret = 'private-secret-123'
    assert web.post('/api/setup/credentials', json={'provider': 'openai', 'value': secret}).status_code == 403
    assert web.post('/api/setup/credentials', json={'provider': 'openai', 'value': secret}, headers={**headers(), 'Origin': 'https://evil.example'}).status_code == 403
    response = web.post('/api/setup/credentials', json={'provider': 'openai', 'value': {'bad': secret}}, headers=headers())
    assert response.status_code == 422
    assert secret not in response.text


def test_secret_save_is_masked_and_clears_old_verification(client, monkeypatch):
    web, _ = client
    saved, reloaded = {}, []
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(setup, 'save_env', lambda values: saved.update(values))
    monkeypatch.setattr(setup, 'reload_runner', lambda runner: reloaded.append(True))
    setup.write_state({'providers': {'openai': {'status': 'old'}}, 'skipped': ['openai']})
    response = web.post('/api/setup/credentials', json={'provider': 'openai', 'value': 'new-test-secret'}, headers=headers())
    assert response.status_code == 200 and 'new-test-secret' not in response.text
    assert saved == {'OPENAI_API_KEY': 'new-test-secret'} and reloaded
    assert setup.read_state()['providers'] == {} and setup.read_state()['skipped'] == []


def test_env_edit_preserves_existing_settings_and_does_not_expand_values(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# personal settings\nDATA_DIR=my-projects\nOPENAI_API_KEY=old\nHF_KEY=id:secret\n', encoding='utf-8')
    setup.save_env({'OPENAI_API_KEY': 'new-key'}, path)
    assert dotenv_values(path) == {'DATA_DIR': 'my-projects', 'OPENAI_API_KEY': 'new-key', 'HF_KEY': 'id:secret'}
    assert '# personal settings' in path.read_text()
    with pytest.raises(ValueError):
        setup.save_env({'OPENAI_API_KEY': 'bad\nINJECTED=1'}, path)
    assert dotenv_values(path)['OPENAI_API_KEY'] == 'new-key'


def spec_for(data):
    return {'label': 'fixture', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'url': 'https://example.com/pinned'}


@pytest.mark.parametrize('supports_range', [True, False])
def test_download_resumes_or_restarts_safely(tmp_path, supports_range):
    data = b'0123456789'
    target = tmp_path / 'model.bin'
    target.with_name('model.bin.partial').write_bytes(data[:4])
    def respond(request):
        assert request.headers['range'] == 'bytes=4-'
        return httpx.Response(206, headers={'Content-Range': 'bytes 4-9/10'}, content=data[4:]) if supports_range else httpx.Response(200, content=data)
    download(spec_for(data), target, lambda *args: None, httpx.Client(transport=httpx.MockTransport(respond)))
    assert target.read_bytes() == data
    assert not target.with_name('model.bin.partial').exists()


def test_download_preserves_existing_unknown_file(tmp_path):
    target = tmp_path / 'model.bin'
    target.write_bytes(b'unknown')
    with pytest.raises(ValueError, match='not overwritten'):
        download(spec_for(b'good-data'), target, lambda *args: None)
    assert target.read_bytes() == b'unknown'


def test_download_rejects_wrong_range_and_hash(tmp_path):
    target = tmp_path / 'model.bin'
    part = target.with_name('model.bin.partial')
    part.write_bytes(b'01')
    with pytest.raises(ValueError, match='byte range'):
        download(spec_for(b'012345'), target, lambda *args: None,
                 httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(206, headers={'Content-Range': 'bytes 0-3/6'}, content=b'2345'))))
    assert part.read_bytes() == b'01'
    with pytest.raises(ValueError, match='Checksum'):
        download(spec_for(b'012345'), target, lambda *args: None,
                 httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'broken'))))
    assert not target.exists()


def test_higgsfield_check_never_claims_verified_or_submits_generation(client):
    web, settings = client
    from pydantic import SecretStr
    settings.hf_key = SecretStr('test-id:test-secret')
    result = web.post('/api/setup/verify', json={'provider': 'higgsfield'}, headers=headers()).json()
    assert result['status'] == 'CONFIGURED_UNVERIFIED' and result['balance'] is None
    assert 'test-secret' not in str(result)


def test_openai_check_uses_get_only_and_reports_auth_failure(client, monkeypatch):
    web, settings = client
    from pydantic import SecretStr
    settings.openai_api_key = SecretStr('test-secret')
    real_client = httpx.AsyncClient
    def respond(request):
        assert request.method == 'GET' and request.url.path.startswith('/v1/models/')
        return httpx.Response(401, json={'error': {'message': 'test-secret must not leak'}})
    monkeypatch.setattr(setup.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(respond)))
    result = web.post('/api/setup/verify', json={'provider': 'openai'}, headers=headers()).json()
    assert result['status'] == 'CHECK_FAILED' and 'test-secret' not in str(result)


def test_diagnostics_excludes_token_and_paths(client):
    web, _ = client
    body = web.get('/api/setup/diagnostics').text
    assert setup.TOKEN not in body and 'private/models' not in body


def test_setup_task_blocks_competing_generation(client):
    web, _ = client
    setup.task['status'] = 'RUNNING'
    assert web.post('/api/projects/anything/plan').status_code == 409


def test_storage_preflight_blocks_before_download(tmp_path, monkeypatch):
    from backend import setup_assets
    settings = Settings(_env_file=None, comfyui_models_dir=tmp_path)
    monkeypatch.setattr(setup_assets, 'manifest', lambda: [{'label': 'huge', 'root': 'comfy', 'path': 'checkpoints/huge', 'bytes': 100}])
    monkeypatch.setattr(setup_assets.shutil, 'disk_usage', lambda path: type('Usage', (), {'free': 50})())
    assert storage_plan(settings)[0]['enough'] is False
    with pytest.raises(ValueError, match='Insufficient storage'):
        setup_assets.install_all(settings, lambda *args: None)
    assert not (tmp_path / 'checkpoints').exists()


def test_whisper_reuses_a_complete_snapshot_not_mixed_files(tmp_path, monkeypatch):
    from backend import setup_assets
    monkeypatch.setattr(setup_assets, 'ROOT', tmp_path)
    monkeypatch.setattr(setup_assets, 'manifest', lambda: [
        {'path': 'whisper/tiny.en/model.bin', 'bytes': 3},
        {'path': 'whisper/tiny.en/config.json', 'bytes': 2}])
    base = tmp_path / 'data/models/whisper'
    direct = base / 'tiny.en'
    direct.mkdir(parents=True)
    (direct / 'model.bin').write_bytes(b'abc')
    snapshot = base / 'models--Systran--faster-whisper-tiny.en/snapshots/test'
    snapshot.mkdir(parents=True)
    (snapshot / 'config.json').write_bytes(b'{}')
    assert setup_assets.whisper_directory() == direct
    (snapshot / 'model.bin').write_bytes(b'abc')
    assert setup_assets.whisper_directory() == snapshot
