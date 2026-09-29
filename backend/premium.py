"""Quoted, resumable Higgsfield Seedance 2.5 scene generation."""
import asyncio
import hashlib
import ipaddress
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_UP
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import Settings
from .providers import HiggsfieldProvider
from .store import Store


MODEL_LABEL = 'Seedance 2.5 via Higgsfield API'
TEXT_MODEL = 'bytedance/seedance-2.5/text-to-video'
REFERENCE_MODEL = 'bytedance/seedance-2.5/reference-to-video'
CONTENT_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
RESOLUTIONS = {'480p': (854, 480), '720p': (1280, 720)}


def fingerprint(project, resolution='720p'):
    if resolution not in RESOLUTIONS:
        raise ValueError('Choose 480p or 720p for Higgsfield')
    assets = {asset['id']: asset for asset in project['assets']}
    material = {
        'duration': project['target_duration_seconds'],
        'brand': project['brand'],
        'script': (project.get('plan') or {}).get('script', ''),
        'narration_voice': project.get('narration_voice', ''),
        'shots': [{'id': shot['id'], 'ordinal': shot['ordinal'], 'data': shot['data']} for shot in project['shots']],
        'references': [{'shot_id': link['shot_id'], 'asset_id': link['asset_id'], 'guidance': link['guidance'],
                        'sha256': (assets.get(link['asset_id'], {}).get('metadata') or {}).get('sha256'),
                        'role': (assets.get(link['asset_id'], {}).get('metadata') or {}).get('role'),
                        'description': (assets.get(link['asset_id'], {}).get('metadata') or {}).get('description')}
                       for link in project['shot_references']],
    }
    base = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    # Preserve the identity of existing 720p quotes while binding new 480p
    # quotes to their resolution as well as their storyboard and references.
    return base if resolution == '720p' else hashlib.sha256(f'{base}:{resolution}'.encode()).hexdigest()


def run_resolution(run):
    resolutions = {scene['payload'].get('resolution', '720p') for scene in run['scenes']}
    if len(resolutions) != 1 or not resolutions.issubset(RESOLUTIONS):
        raise ValueError('Higgsfield quote has inconsistent resolutions')
    return resolutions.pop()


def run_fingerprint(project, run):
    return fingerprint(project, run_resolution(run))


def scene_prompt(project, shot, linked):
    data = shot['data']
    brand = project['brand']
    parts = [
        f"Landscape 16:9 evaluation scene {shot['ordinal']} of {len(project['shots'])}.",
        f"Product: {brand.get('product_name', '')}. {brand.get('description', '')}",
        f"Visual style: {brand.get('visual_style', '')}",
        f"Scene purpose: {data.get('purpose', '')}",
        f"Scene visual: {data.get('visual', '')}",
        f"Camera: {data.get('camera', '')}",
        f"Action and motion: {data.get('video_prompt', '')}",
    ]
    for asset, guidance in linked:
        meta = asset.get('metadata') or {}
        parts.append(f"Reference image ({meta.get('role', 'reference')}): {meta.get('description', '')}. "
                     f"Use the depicted subject as a visual identity reference; follow this direction: {guidance or 'preserve its distinguishing appearance'}. "
                     "Stage the scene in the setting described above; the reference photo's background is not automatically the scene setting.")
    if data.get('negative_prompt'):
        parts.append(f"Avoid: {data['negative_prompt']}")
    parts.append('No subtitles or generated spoken dialogue; a continuous narration track will be added in editing.')
    return '\n'.join(part for part in parts if part.strip())


def preflight(project, resolution='480p'):
    if resolution not in RESOLUTIONS:
        raise ValueError('Choose 480p or 720p for Higgsfield')
    errors = []
    if project['approvals']['storyboard']['status'] != 'APPROVED':
        errors.append('Approve the storyboard before requesting a Higgsfield estimate.')
    if not project['shots']:
        errors.append('Add at least one storyboard scene.')
    if not (project.get('plan') or {}).get('script', '').strip():
        errors.append('A continuous narration script is required for this evaluation.')
    total = sum(float(shot['data'].get('duration_seconds') or 0) for shot in project['shots'])
    if abs(total - project['target_duration_seconds']) > 0.05:
        errors.append('Scene durations must add up to the target film length.')
    assets = {asset['id']: asset for asset in project['assets']}
    scenes = []
    for shot in project['shots']:
        duration = float(shot['data'].get('duration_seconds') or 0)
        if not duration.is_integer() or not 4 <= duration <= 30:
            errors.append(f"Scene {shot['ordinal']} must be 4–30 whole seconds for Seedance 2.5.")
        links = [link for link in project['shot_references'] if link['shot_id'] == shot['id']]
        if len(links) > 30:
            errors.append(f"Scene {shot['ordinal']} has more than 30 image references.")
        linked = []
        for link in links:
            asset = assets.get(link['asset_id'])
            if not asset or asset['kind'] != 'reference_image':
                errors.append(f"Scene {shot['ordinal']} has an unavailable reference.")
            else:
                linked.append((asset, link['guidance']))
        scenes.append({'ordinal': shot['ordinal'], 'shot_id': shot['id'], 'duration_seconds': duration,
                       'model_label': MODEL_LABEL,
                       'model_path': REFERENCE_MODEL if linked else TEXT_MODEL,
                       'reference_ids': [asset['id'] for asset, _ in linked],
                       'prompt': scene_prompt(project, shot, linked)})
    return {'model': MODEL_LABEL, 'resolution': resolution, 'aspect_ratio': '16:9',
            'generate_audio': False, 'target_duration_seconds': project['target_duration_seconds'],
            'fingerprint': fingerprint(project, resolution), 'scenes': scenes, 'errors': errors}


def _usd(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('Higgsfield estimate did not return a USD amount') from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError('Higgsfield estimate returned an invalid USD amount')
    return amount


def _estimated_usd(result, payload):
    if 'usd' in result:
        return _usd(result['usd'])
    description = result.get('pricing_description')
    resolution = payload.get('resolution')
    if (result.get('type') != 'description' or not isinstance(description, str)
            or resolution not in RESOLUTIONS or payload.get('video_urls')
            or 'per second of generated video' not in description
            or 'without video input' not in description):
        raise ValueError('Higgsfield estimate did not return a usable USD price')
    rate_description = description.split('Each 1,000 video tokens')[0]
    match = re.search(r'\$([0-9]+(?:\.[0-9]+)?)[^$]*?\bat\s+' + re.escape(resolution) + r'\b', rate_description)
    if not match:
        raise ValueError(f'Higgsfield estimate did not include the {resolution} per-second rate')
    rate = _usd(match.group(1))
    duration = Decimal(str(payload['duration']))
    return (rate * duration).quantize(Decimal('0.01'), rounding=ROUND_UP)


async def create_quote(store: Store, project_id: str, provider: HiggsfieldProvider, resolution='480p'):
    project = store.get_project(project_id)
    preview = preflight(project, resolution)
    if preview['errors']:
        raise ValueError(' '.join(preview['errors']))
    if not provider.credential():
        raise ValueError('Set a new HF_KEY in .env and reload the studio page before estimating.')
    assets = {asset['id']: asset for asset in project['assets']}
    uploaded = {}
    for scene in preview['scenes']:
        for asset_id in scene['reference_ids']:
            if asset_id in uploaded:
                continue
            asset = assets[asset_id]
            path = (store.project_dir(project) / asset['relative_path']).resolve()
            root = store.project_dir(project).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Reference image file is unavailable')
            content_type = CONTENT_TYPES.get(path.suffix.lower())
            if not content_type:
                raise ValueError('Reference image format is unsupported by Higgsfield')
            uploaded[asset_id] = await provider.upload_image(path, content_type)
    quoted_scenes = []
    for scene in preview['scenes']:
        payload = {'prompt': scene['prompt'], 'duration': int(scene['duration_seconds']),
                   'resolution': resolution, 'aspect_ratio': '16:9', 'bitrate_mode': 'high',
                   'generate_audio': False}
        if scene['reference_ids']:
            payload['image_urls'] = [uploaded[asset_id] for asset_id in scene['reference_ids']]
        result = await provider.estimate(scene['model_path'], payload)
        quoted_scenes.append({'ordinal': scene['ordinal'], 'shot_id': scene['shot_id'],
                              'model_path': scene['model_path'], 'payload': payload,
                              'estimated_usd': str(_estimated_usd(result, payload))})
    if fingerprint(store.get_project(project_id), resolution) != preview['fingerprint']:
        raise ValueError('Storyboard changed while estimating; request a fresh estimate')
    return store.create_premium_quote(project_id, preview['fingerprint'], quoted_scenes)


def _safe_media_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Higgsfield returned an invalid media URL')
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if parsed.hostname.casefold() in ('localhost', 'localhost.localdomain'):
            raise ValueError('Higgsfield returned an invalid media host')
    else:
        if not address.is_global:
            raise ValueError('Higgsfield returned an invalid media host')
    return url


async def download_video(url, target: Path):
    _safe_media_url(url)
    part = target.with_suffix('.download')
    limit = 1024 * 1024 * 1024
    total = 0
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True, trust_env=False) as client:
            async with client.stream('GET', url) as response:
                response.raise_for_status()
                with part.open('wb') as handle:
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > limit:
                            raise ValueError('Higgsfield video exceeded the 1 GB download limit')
                        handle.write(chunk)
        if total < 1024:
            raise ValueError('Higgsfield video download was empty')
        part.replace(target)
    except Exception:
        part.unlink(missing_ok=True)
        raise


class PremiumRenderer:
    def __init__(self, store: Store, settings: Settings, provider=None):
        self.store = store
        self.settings = settings
        self.dynamic_credentials = provider is None
        self.provider = provider or HiggsfieldProvider(settings)

    async def render(self, project_id, run_id):
        from .local_media import probe

        if self.dynamic_credentials:
            self.provider = HiggsfieldProvider(Settings())

        run = self.store.get_premium_run(project_id, run_id)
        project = self.store.get_project(project_id)
        if run['status'] == 'COMPLETED':
            prior = next((asset for asset in project['assets'] if asset['kind'] == 'premium_evaluation'
                          and (asset.get('metadata') or {}).get('run_id') == run_id), None)
            if prior:
                return {'run_id': run_id, 'scenes_ready': len(run['scenes']), 'asset_id': prior['id']}
        if run['status'] not in ('APPROVED', 'RUNNING', 'SCENES_READY', 'COMPLETED'):
            raise ValueError('Approve the Higgsfield estimate before rendering')
        if run['fingerprint'] != run_fingerprint(project, run):
            raise ValueError('Storyboard or references changed after approval; request a new estimate')
        self.store.update_premium_run(project_id, run_id, 'RUNNING')
        root = self.store.project_dir(project)
        for scene in run['scenes']:
            ordinal = scene['ordinal']
            if scene['status'] == 'COMPLETED':
                continue
            target = root / f'premium_generations/higgsfield/{run_id}_scene_{ordinal:02d}.mp4'
            if scene['status'] == 'SUBMITTING' and not scene['request_id']:
                self.store.update_premium_run(project_id, run_id, 'NEEDS_REVIEW',
                                              'A scene submission may have been accepted; check Higgsfield before retrying')
                raise ValueError('Higgsfield submission outcome is uncertain; check the API console')
            request_id = scene['request_id']
            if not request_id:
                estimate = await self.provider.estimate(scene['model_path'], scene['payload'])
                if _estimated_usd(estimate, scene['payload']) > _usd(scene['estimated_usd']):
                    self.store.update_premium_run(project_id, run_id, 'NEEDS_REVIEW',
                                                  'Higgsfield price increased after approval; request a new estimate')
                    raise ValueError('Higgsfield price increased after approval; request a new estimate')
                self.store.update_premium_scene(project_id, run_id, ordinal, 'SUBMITTING')
                try:
                    accepted = await self.provider.submit(scene['model_path'], scene['payload'])
                    request_id = accepted['request_id']
                except Exception:
                    self.store.update_premium_run(project_id, run_id, 'NEEDS_REVIEW',
                                                  'Submission outcome is uncertain; check Higgsfield before retrying')
                    raise ValueError('Higgsfield submission outcome is uncertain; check the API console') from None
                self.store.update_premium_scene(project_id, run_id, ordinal, 'RUNNING', request_id=request_id)
            for attempt in range(360):
                status = await self.provider.request_status(request_id)
                state = status.get('status')
                if state == 'completed':
                    url = status.get('video', {}).get('url')
                    if not url:
                        raise ValueError('Higgsfield completed without a video URL')
                    await download_video(url, target)
                    media = probe(target, self.settings)
                    if not any(stream['codec_type'] == 'video' for stream in media['streams']):
                        raise ValueError('Higgsfield output has no video stream')
                    self.store.update_premium_scene(project_id, run_id, ordinal, 'COMPLETED',
                                                    output_url=url, relative_path=str(target.relative_to(root)))
                    latest = self.store.get_project(project_id)
                    if not any(asset['kind'] == 'premium_clip' and asset['shot_id'] == scene['shot_id']
                               and (asset.get('metadata') or {}).get('run_id') == run_id for asset in latest['assets']):
                        self.store.add_asset(project_id, 'premium_clip', 'higgsfield_seedance_2_5',
                                             target.relative_to(root), shot_id=scene['shot_id'],
                                             prompt=scene['payload']['prompt'], settings=scene['payload'],
                                             metadata={'run_id': run_id, 'request_id': request_id,
                                                       'estimated_usd': scene['estimated_usd'],
                                                       'model_path': scene['model_path']}, commercial_use=False)
                    break
                if state in ('failed', 'nsfw', 'canceled'):
                    self.store.update_premium_scene(project_id, run_id, ordinal, 'FAILED',
                                                    error=f'Higgsfield request {state}')
                    self.store.update_premium_run(project_id, run_id, 'FAILED', f'Scene {ordinal}: {state}')
                    raise ValueError(f'Higgsfield scene {ordinal} {state}')
                await asyncio.sleep(min(5 + attempt // 10, 20))
            else:
                self.store.update_premium_run(project_id, run_id, 'NEEDS_REVIEW',
                                              'Polling timed out; provider request is still saved for recovery')
                raise ValueError('Higgsfield polling timed out; do not submit the scene again')
        self.store.update_premium_run(project_id, run_id, 'SCENES_READY')
        asset = await asyncio.to_thread(self.assemble_evaluation, project_id, run_id)
        self.store.update_premium_run(project_id, run_id, 'COMPLETED')
        return {'run_id': run_id, 'scenes_ready': len(run['scenes']), 'asset_id': asset['id']}

    def assemble_evaluation(self, project_id, run_id):
        from .local_media import LocalDraftGenerator, existing_asset, probe, run_ffmpeg

        run = self.store.get_premium_run(project_id, run_id)
        project = self.store.get_project(project_id)
        if any(scene['status'] != 'COMPLETED' for scene in run['scenes']):
            raise ValueError('All Higgsfield scenes must finish before assembly')
        root = self.store.project_dir(project)
        for scene in run['scenes']:
            if not any(asset['kind'] == 'premium_clip' and asset['shot_id'] == scene['shot_id']
                       and (asset.get('metadata') or {}).get('run_id') == run_id for asset in project['assets']):
                path = root / scene['relative_path']
                self.store.add_asset(project_id, 'premium_clip', 'higgsfield_seedance_2_5',
                                     path.relative_to(root), shot_id=scene['shot_id'],
                                     prompt=scene['payload']['prompt'], settings=scene['payload'],
                                     metadata={'run_id': run_id, 'request_id': scene['request_id'],
                                               'estimated_usd': scene['estimated_usd'],
                                               'model_path': scene['model_path']}, commercial_use=False)
                project = self.store.get_project(project_id)
        prior = next((asset for asset in project['assets'] if asset['kind'] == 'premium_evaluation'
                      and (asset.get('metadata') or {}).get('run_id') == run_id), None)
        if prior:
            return prior
        local = LocalDraftGenerator(self.store, self.settings)
        audio = local.narration(project)
        project = self.store.get_project(project_id)
        captions = local.captions(project, audio)
        project = self.store.get_project(project_id)
        clips = [root / scene['relative_path'] for scene in run['scenes']]
        target = root / f'premium_generations/higgsfield/{run_id}_evaluation.mp4'
        args = []
        for clip in clips:
            args.extend(['-i', str(clip)])
        args.extend(['-i', str(audio), '-i', str(captions)])
        output_width, output_height = RESOLUTIONS[run_resolution(run)]
        filters = ';'.join(
            f'[{index}:v]setpts=(PTS-STARTPTS)*{float(shot["data"]["duration_seconds"]) / float(probe(clip, self.settings)["format"]["duration"]):.8f},'
            f'fps=24,tpad=stop_mode=clone:stop_duration=1,trim=duration={float(shot["data"]["duration_seconds"])},'
            f'setpts=PTS-STARTPTS,scale={output_width}:{output_height},format=yuv420p[v{index}]'
            for index, (clip, shot) in enumerate(zip(clips, project['shots'])))
        filters += ';' + ''.join(f'[v{index}]' for index in range(len(clips)))
        filters += f'concat=n={len(clips)}:v=1:a=0[v]'
        args.extend(['-filter_complex', filters, '-map', '[v]', '-map', f'{len(clips)}:a:0',
                     '-map', f'{len(clips)+1}:s:0', '-t', str(project['target_duration_seconds']),
                     '-af', 'apad', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21',
                     '-c:a', 'aac', '-c:s', 'mov_text', '-movflags', '+faststart',
                     '-metadata', 'comment=AI-generated DRAFT; non-commercial evaluation only', str(target)])
        run_ffmpeg(self.settings, args, timeout=600)
        media = probe(target, self.settings)
        streams = media['streams']
        if not any(item['codec_type'] == 'video' for item in streams) or not any(item['codec_type'] == 'audio' for item in streams):
            raise RuntimeError('Higgsfield evaluation must contain video and continuous narration')
        if abs(float(media['format']['duration']) - project['target_duration_seconds']) > 0.5:
            raise RuntimeError('Higgsfield evaluation duration does not match the project target')
        clip_ids = [(next(asset['id'] for asset in project['assets'] if asset['kind'] == 'premium_clip'
                          and asset['shot_id'] == scene['shot_id'] and
                          (asset.get('metadata') or {}).get('run_id') == run_id)) for scene in run['scenes']]
        return self.store.add_asset(project_id, 'premium_evaluation', 'higgsfield_ffmpeg',
                                    target.relative_to(root), commercial_use=False,
                                    metadata={'run_id': run_id, 'model': MODEL_LABEL,
                                              'fingerprint': run['fingerprint'],
                                              'clip_asset_ids': clip_ids,
                                              'narration_asset_id': existing_asset(project, 'narration')['id'],
                                              'caption_asset_id': existing_asset(project, 'captions')['id'],
                                              'estimated_usd': run['estimated_usd'],
                                              'duration_seconds': float(media['format']['duration'])})
