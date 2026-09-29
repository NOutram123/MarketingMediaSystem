import asyncio
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.config import Settings
from backend.main import app
from backend.providers import HiggsfieldProvider, ElevenLabsProvider, ComfyProvider
from backend.orchestration import load_profiles, OpenAIOrchestrator, ValidationProbe


def test_defaults_and_secrets():
    s = Settings(_env_file=None, openai_api_key='test-secret')
    assert s.openai_model == 'gpt-6-astra'
    assert s.openai_reasoning == 'medium'
    assert s.auto_approve_below_usd == 0
    assert s.local_drafts_noncommercial is True
    assert 'test-secret' not in s.model_dump_json()


@pytest.mark.parametrize('url', ['http://0.0.0.0:8188', 'https://example.com', 'file:///etc/passwd'])
def test_comfy_must_be_local(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, comfyui_url=url)


def test_no_negative_spend_threshold():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auto_approve_below_usd=-1)


def test_missing_credentials_are_not_failures():
    s = Settings(_env_file=None, hf_api_key_id='', hf_api_key_secret='', elevenlabs_api_key='')
    for provider in (HiggsfieldProvider(s), ElevenLabsProvider(s)):
        assert asyncio.run(provider.health_check()).status == 'NOT_CONFIGURED'


def test_configured_is_not_authenticated():
    s = Settings(_env_file=None, hf_api_key_id='id', hf_api_key_secret='secret')
    assert asyncio.run(HiggsfieldProvider(s).health_check()).status == 'CONFIGURED_UNVERIFIED'


def test_complete_higgsfield_credential_in_key_id_field():
    s = Settings(_env_file=None, hf_key='', hf_api_key_id='example-id:example-secret', hf_api_key_secret='')
    provider = HiggsfieldProvider(s)
    assert provider.credential() == 'example-id:example-secret'
    assert asyncio.run(provider.health_check()).status == 'CONFIGURED_UNVERIFIED'


def test_health_schema_and_host_protection():
    client = TestClient(app)
    assert client.get('/api/health').json()['phase_1_complete'] is True
    assert client.get('/api/health').json()['phase_complete'] is True
    assert client.get('/api/health').json()['phase_2_complete'] is True
    assert client.get('/api/health').json()['local_drafts_noncommercial'] is True
    assert client.get('/api/health', headers={'host': 'evil.example'}).status_code == 400
    assert client.get('/openapi.json').status_code == 200


def test_openai_profiles_are_editable_and_default_matches_brief():
    catalog = load_profiles()
    assert catalog.get().model == 'gpt-6-astra'
    assert catalog.get().reasoning_effort == 'medium'
    assert catalog.get('sol-high').reasoning_effort == 'high'


def test_responses_api_invocation_with_mock_client():
    class MockUsage:
        def model_dump(self):
            return {'input_tokens': 5, 'output_tokens': 4}

    class MockResponses:
        def parse(self, **kwargs):
            assert kwargs['model'] == 'gpt-6-astra'
            assert kwargs['reasoning'] == {'effort': 'medium'}
            assert kwargs['store'] is False
            assert kwargs['text_format'] is ValidationProbe
            return type('Result', (), {'output_parsed': ValidationProbe(ok=True, note='tested'), 'usage': MockUsage(), 'id': 'resp_test', 'model': 'gpt-6-astra'})()

    mock = type('Client', (), {'responses': MockResponses()})()
    result = OpenAIOrchestrator(Settings(_env_file=None, openai_api_key='test-key'), client=mock).structured('test', ValidationProbe)
    assert result['usage']['input_tokens'] == 5
