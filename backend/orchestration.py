"""OpenAI Responses API orchestration, with configurable model profiles."""
import json
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from .config import ROOT, Settings


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    label: str
    model: str
    reasoning_effort: str


class ProfileCatalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    default: str
    profiles: list[ModelProfile]

    def get(self, profile_id: str | None = None) -> ModelProfile:
        target = profile_id or self.default
        for profile in self.profiles:
            if profile.id == target:
                return profile
        raise KeyError(f'Unknown model profile: {target}')


def load_profiles(path: Path = ROOT / 'config/model_profiles.json') -> ProfileCatalog:
    catalog = ProfileCatalog.model_validate(json.loads(path.read_text(encoding='utf-8')))
    if catalog.default not in {p.id for p in catalog.profiles}:
        raise ValueError('Default model profile is missing')
    if len({p.id for p in catalog.profiles}) != len(catalog.profiles):
        raise ValueError('Duplicate model profile ids')
    return catalog


class ValidationProbe(BaseModel):
    ok: bool
    note: str


class OpenAIOrchestrator:
    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self.settings = settings
        self.client = client

    def structured(self, prompt: str, schema: type[BaseModel], profile: ModelProfile | None = None):
        if not self.settings.openai_api_key.get_secret_value():
            raise RuntimeError('OPENAI_API_KEY is not configured')
        model = profile.model if profile else self.settings.openai_model
        reasoning = profile.reasoning_effort if profile else self.settings.openai_reasoning
        client = self.client or OpenAI(api_key=self.settings.openai_api_key.get_secret_value(),
                                      timeout=self.settings.openai_timeout_seconds, max_retries=0)
        response = client.responses.parse(model=model, reasoning={'effort': reasoning},
                                          input=prompt, text_format=schema, store=False)
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError('OpenAI returned no parsed structured output')
        usage = response.usage.model_dump() if response.usage else None
        return {'result': parsed, 'response_id': response.id, 'model': response.model, 'usage': usage}
