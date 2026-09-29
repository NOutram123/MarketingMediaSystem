"""Validated project, brand, and creative plan contracts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrandKit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_name: str = Field(min_length=1, max_length=120)
    description: str = ''
    logos: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    typography: list[str] = Field(default_factory=list)
    approved_wording: list[str] = Field(default_factory=list)
    prohibited_wording: list[str] = Field(default_factory=list)
    approved_claims: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    required_disclaimers: list[str] = Field(default_factory=list)
    reference_people: list[str] = Field(default_factory=list)
    voice: str = 'warm, clear English narration'
    visual_style: str = 'cinematic product photography'
    cta: str = ''
    website: str = ''


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=2, max_length=120)
    brief: str = Field(min_length=10, max_length=12000)
    treatment_notes: str = Field(default='', max_length=30000)
    brand: BrandKit
    profile_id: str = 'astra-medium'
    target_duration_seconds: Literal[15, 30, 45, 60] | None = None


class GateReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approve: bool
    note: str = Field(default='', max_length=2000)


class BriefUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    brief: str = Field(min_length=10, max_length=12000)


class InputUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    brief: str = Field(min_length=10, max_length=12000)
    treatment_notes: str = Field(default='', max_length=30000)
    brand: BrandKit
    target_duration_seconds: Literal[15, 30, 45, 60]


class ReferenceMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['character', 'product', 'style', 'location', 'other']
    description: str = Field(default='', max_length=2000)


class ScriptUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    script: str = Field(min_length=20, max_length=1000)


class DirectionUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    concept: str = Field(min_length=3, max_length=4000)
    script: str = Field(min_length=20, max_length=4000)


class ClaimCandidates(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidates: list[str] = Field(max_length=10)


class VoiceUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    voice_id: str = Field(min_length=3, max_length=40)


class ShotPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    purpose: str
    visual: str
    camera: str
    duration_seconds: float = Field(ge=2, le=30)
    narration: str
    image_prompt: str
    video_prompt: str
    negative_prompt: str = ''


class ShotUpdate(ShotPlan):
    purpose: str = Field(min_length=1, max_length=300)
    visual: str = Field(min_length=1, max_length=4000)
    camera: str = Field(min_length=1, max_length=1000)
    narration: str = Field(max_length=1000)
    image_prompt: str = Field(min_length=1, max_length=4000)
    video_prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str = Field(default='', max_length=2000)


class CampaignPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    concept: str
    target_audience: str
    key_message: str
    script: str
    claims_used: list[str]
    shots: list[ShotPlan] = Field(min_length=1, max_length=20)


class MasterCampaignPlan(CampaignPlan):
    pass


class HalfMinuteCampaignPlan(CampaignPlan):
    pass


class ThreeQuarterMinuteCampaignPlan(CampaignPlan):
    pass


def claim_warnings(plan: CampaignPlan, brand: BrandKit) -> list[str]:
    allowed = {claim.strip().casefold() for claim in brand.approved_claims}
    prohibited = {claim.strip().casefold() for claim in brand.prohibited_claims}
    warnings = []
    for claim in plan.claims_used:
        normalized = claim.strip().casefold()
        if normalized in prohibited:
            warnings.append(f'Prohibited claim listed: {claim}')
        elif normalized not in allowed:
            warnings.append(f'Unapproved claim listed: {claim}')
    return warnings
