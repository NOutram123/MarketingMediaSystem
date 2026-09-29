"""Foundation providers. Health checks never submit a paid generation."""
from typing import Protocol
import httpx
from pydantic import BaseModel
from .config import Settings


class Health(BaseModel):
    provider: str
    status: str
    detail: str


class Provider(Protocol):
    async def health_check(self) -> Health: ...
    def get_capabilities(self) -> list[str]: ...


class ComfyProvider:
    def __init__(self, settings: Settings):
        self.url = settings.comfyui_url

    def get_capabilities(self):
        return ['workflow_submission', 'history', 'queue']

    async def health_check(self):
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(self.url + '/system_stats')
                response.raise_for_status()
                body = response.json()
            if not body.get('devices'):
                return Health(provider='comfyui', status='UNAVAILABLE', detail='No devices reported')
            return Health(provider='comfyui', status='REACHABLE', detail='API reachable; generation requires a separate benchmark')
        except (httpx.HTTPError, ValueError):
            return Health(provider='comfyui', status='UNAVAILABLE', detail='ComfyUI API did not respond successfully')

    async def submit(self, workflow: dict, client_id: str):
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(self.url + '/prompt', json={'prompt': workflow, 'client_id': client_id})
            response.raise_for_status()
            return response.json()

    async def history(self, prompt_id: str):
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(self.url + '/history/' + prompt_id)
            response.raise_for_status()
            return response.json()


class HiggsfieldProvider:
    """Server-side Higgsfield REST client. Status never submits a generation."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def get_capabilities(self):
        return ['estimate', 'reference_upload', 'seedance_2_5', 'request_status']

    def credential(self):
        complete = self.settings.hf_key.get_secret_value().strip()
        if complete:
            return complete
        key_id = self.settings.hf_api_key_id.get_secret_value().strip()
        secret = self.settings.hf_api_key_secret.get_secret_value().strip()
        if key_id and ':' in key_id and not secret:
            return key_id
        return f'{key_id}:{secret}' if key_id and secret else ''

    def headers(self):
        credential = self.credential()
        if not credential:
            raise ValueError('Set HF_KEY in .env and reload the studio page')
        return {'Authorization': f'Key {credential}'}

    async def health_check(self):
        configured = bool(self.credential())
        return Health(provider='higgsfield', status='CONFIGURED_UNVERIFIED' if configured else 'NOT_CONFIGURED',
                      detail='Authentication and API balance not yet verified' if configured else 'Set HF_KEY in .env')

    async def estimate(self, model_path: str, payload: dict):
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(f'https://api.higgsfield.ai/estimate/{model_path}',
                                         json=payload, headers=self.headers())
            response.raise_for_status()
            return response.json()

    async def upload_image(self, path, content_type: str):
        from urllib.parse import urlparse
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            response = await client.post('https://api.higgsfield.ai/files/generate-upload-url',
                                         json={'content_type': content_type}, headers=self.headers())
            response.raise_for_status()
            ticket = response.json()
            upload_url = ticket['upload_url']
            if urlparse(upload_url).scheme != 'https' or urlparse(ticket['public_url']).scheme != 'https':
                raise ValueError('Higgsfield returned a non-HTTPS upload URL')
            # Signed storage URLs are secrets. Never include them in errors or logs.
            try:
                put = await client.put(upload_url, content=path.read_bytes(), headers=ticket['upload_headers'])
                put.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError('Reference upload to Higgsfield failed') from None
            return ticket['public_url']

    async def submit(self, model_path: str, payload: dict):
        async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
            response = await client.post(f'https://api.higgsfield.ai/{model_path}',
                                         json=payload, headers=self.headers())
            response.raise_for_status()
            return response.json()

    async def request_status(self, request_id: str):
        from uuid import UUID
        request_id = str(UUID(request_id))
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.get(f'https://api.higgsfield.ai/requests/{request_id}/status', headers=self.headers())
            response.raise_for_status()
            return response.json()


class ElevenLabsProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def get_capabilities(self):
        return []

    async def health_check(self):
        configured = bool(self.settings.elevenlabs_api_key.get_secret_value())
        return Health(provider='elevenlabs', status='CONFIGURED_UNVERIFIED' if configured else 'NOT_CONFIGURED',
                      detail='Optional premium voice; live synthesis not yet validated')
