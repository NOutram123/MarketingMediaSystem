from pathlib import Path
from decimal import Decimal
from pydantic import SecretStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from .local_paths import comfy_models, media_tool

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    openai_api_key: SecretStr = SecretStr('')
    openai_model: str = 'gpt-6-astra'
    openai_reasoning: str = 'medium'
    openai_timeout_seconds: int = Field(default=300, ge=30, le=600)
    # Complete credential copied from the Higgsfield API console. Legacy split
    # fields remain readable for existing local installations.
    hf_key: SecretStr = SecretStr('')
    hf_api_key_id: SecretStr = SecretStr('')
    hf_api_key_secret: SecretStr = SecretStr('')
    elevenlabs_api_key: SecretStr = SecretStr('')
    comfyui_url: str = 'http://127.0.0.1:8188'
    comfyui_models_dir: Path = Field(default_factory=comfy_models)
    ffmpeg_path: str = Field(default_factory=lambda: media_tool('ffmpeg'))
    ffprobe_path: str = Field(default_factory=lambda: media_tool('ffprobe'))
    auto_approve_below_usd: Decimal = Field(default=Decimal('0'), ge=0)
    local_drafts_noncommercial: bool = True
    data_dir: Path = ROOT / 'data'

    @field_validator('comfyui_url')
    @classmethod
    def local_url(cls, value):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('ComfyUI must use a loopback HTTP address')
        return value.rstrip('/')

    @field_validator('data_dir')
    @classmethod
    def absolute_data(cls, value):
        return value if value.is_absolute() else ROOT / value
