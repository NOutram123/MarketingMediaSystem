"""Restartable, non-commercial local storyboard and rough-cut production."""
import asyncio
import json
import math
import secrets
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
import soundfile as sf
from PIL import Image

from .config import ROOT, Settings
from .providers import ComfyProvider
from .store import Store
from .voices import DEFAULT_VOICE, voice_language
from .video_models import DEFAULT_VIDEO_MODEL, require_video_model
from .local_paths import whisper_model


def probe(path: Path, settings: Settings):
    result = subprocess.run([settings.ffprobe_path, '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True,
                            check=True, timeout=30)
    return json.loads(result.stdout)


def run_ffmpeg(settings: Settings, args, timeout=180):
    result = subprocess.run([settings.ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-y', *args],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'FFmpeg failed: {result.stderr[-1000:]}')


def existing_asset(project, kind, shot_id=None):
    return next((asset for asset in reversed(project['assets'])
                 if asset['kind'] == kind and asset['shot_id'] == shot_id and asset['status'] == 'CREATED'), None)


def next_version(project, kind, shot_id=None):
    return max((asset['version'] for asset in project['assets']
                if asset['kind'] == kind and asset['shot_id'] == shot_id), default=0) + 1


def remember_workflow(manifest_path, key, workflow):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    if key not in manifest:
        manifest[key] = workflow
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def validate_animated_preview(animated, expected_size, model_id):
    # Animated WebP may coalesce visually identical frames in a nearly static shot.
    # Its stored frame count is therefore not required to equal the sampler length.
    if animated.format != 'WEBP' or animated.size != expected_size or animated.n_frames < 1:
        raise RuntimeError(
            f'ComfyUI returned an invalid {model_id} video '
            f'(format={animated.format}, size={animated.size}, frames={animated.n_frames})')


def reference_direction(project, shot):
    instructions = []
    for link in project['shot_references']:
        if link['shot_id'] != shot['id']:
            continue
        asset = next((item for item in project['assets'] if item['id'] == link['asset_id']), None)
        if not asset:
            continue
        metadata = asset.get('metadata') or {}
        role = metadata.get('role', 'reference')
        description = metadata.get('description') or metadata.get('original_name') or ''
        instructions.append(f'{role}: {description}. {link["guidance"]}'.strip())
    return ' Consistency references: ' + ' '.join(instructions) if instructions else ''


class LocalDraftGenerator:
    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings
        self.comfy = ComfyProvider(settings)

    async def _result(self, workflow, manifest_path, key, output_node):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
        prompt_id = manifest.get(key)
        if not prompt_id:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                queue = (await client.get(self.settings.comfyui_url + '/queue')).json()
            if queue.get('queue_running') or queue.get('queue_pending'):
                raise RuntimeError('ComfyUI is busy with another job; retry this local draft later')
            submitted = await self.comfy.submit(workflow, str(uuid4()))
            if submitted.get('node_errors'):
                raise RuntimeError(f'ComfyUI rejected workflow: {submitted["node_errors"]}')
            prompt_id = submitted['prompt_id']
            manifest[key] = prompt_id
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        for _ in range(900):
            history = (await self.comfy.history(prompt_id)).get(prompt_id)
            if history:
                status = history.get('status', {})
                if status.get('status_str') == 'error':
                    manifest.pop(key, None)
                    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                    raise RuntimeError(f'ComfyUI generation failed: {status.get("messages", [])[-2:]}')
                output = history.get('outputs', {}).get(output_node, {})
                media = output.get('images', []) or output.get('gifs', [])
                if media:
                    item = media[0]
                    async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
                        response = await client.get(self.settings.comfyui_url + '/view', params={
                            'filename': item['filename'], 'subfolder': item.get('subfolder', ''),
                            'type': item.get('type', 'output')})
                        response.raise_for_status()
                    return response.content, prompt_id
            await asyncio.sleep(2)
        raise TimeoutError(f'ComfyUI prompt {prompt_id} did not finish within 30 minutes')

    async def image(self, project, shot):
        root = self.store.project_dir(project)
        ordinal = shot['ordinal']
        current = existing_asset(project, 'storyboard_frame', shot['id'])
        version = next_version(project, 'storyboard_frame', shot['id']) if not current else current['version']
        target = root / (current['relative_path'] if current else f'local_drafts/images/shot_{ordinal:02d}_{shot["id"][:8]}_v{version:03d}.png')
        if current and target.is_file():
            return target
        manifest = root / f'manifests/shot_{shot["id"][:8]}.json'
        workflow_key = f'image_workflow_v{version:03d}'
        prompt_key = f'image_prompt_id_v{version:03d}'
        image_prompt = shot['data']['image_prompt'] + reference_direction(project, shot)
        if not target.is_file():
            workflow = json.loads((ROOT / 'workflows/flux_schnell_draft.json').read_text(encoding='utf-8'))
            workflow['2']['inputs']['text'] = image_prompt
            workflow['5']['inputs']['seed'] = secrets.randbits(32)
            workflow['7']['inputs']['filename_prefix'] = f'MediaStudio_{project["id"][:8]}_shot_{ordinal:02d}'
            remember_workflow(manifest, workflow_key, workflow)
            data, prompt_id = await self._result(workflow, manifest, prompt_key, '7')
            with Image.open(BytesIO(data)) as image:
                if image.format != 'PNG' or image.size != (512, 512):
                    raise RuntimeError('ComfyUI returned an invalid storyboard image')
            target.write_bytes(data)
        else:
            prompt_id = json.loads(manifest.read_text(encoding='utf-8')).get(prompt_key) if manifest.exists() else None
        if not existing_asset(project, 'storyboard_frame', shot['id']):
            saved = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
            self.store.add_asset(project['id'], 'storyboard_frame', 'comfyui_flux_schnell',
                                 target.relative_to(root), shot_id=shot['id'],
                                 prompt=image_prompt,
                                 settings={'workflow': saved.get(workflow_key)},
                                 metadata={'prompt_id': prompt_id, 'model': 'flux1-schnell-fp8.safetensors'})
        return target

    async def upload_to_comfy(self, path):
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            with path.open('rb') as handle:
                response = await client.post(self.settings.comfyui_url + '/upload/image',
                                             files={'image': (f'mediastudio_{uuid4().hex}{path.suffix}', handle)})
            response.raise_for_status()
            return response.json()['name']

    async def video(self, project, shot, storyboard_image, model_id=DEFAULT_VIDEO_MODEL):
        spec = require_video_model(model_id, self.settings)
        root = self.store.project_dir(project)
        ordinal = shot['ordinal']
        current = existing_asset(project, 'draft_clip', shot['id'])
        version = next_version(project, 'draft_clip', shot['id']) if not current else current['version']
        target = root / (current['relative_path'] if current else f'local_drafts/video/shot_{ordinal:02d}_{shot["id"][:8]}_v{version:03d}.mp4')
        if current and target.is_file():
            return target
        links = [link for link in project['shot_references'] if link['shot_id'] == shot['id']]
        video_prompt = shot['data']['video_prompt'] + reference_direction(project, shot)
        manifest = root / f'manifests/shot_{shot["id"][:8]}.json'
        workflow_key = f'video_workflow_v{version:03d}'
        prompt_key = f'video_prompt_id_v{version:03d}'
        if not target.is_file():
            workflow = json.loads((ROOT / 'workflows' / spec['workflow']).read_text(encoding='utf-8'))
            workflow['3']['inputs']['text'] = video_prompt
            workflow['4']['inputs']['text'] = shot['data'].get('negative_prompt') or 'distorted, flicker, text, logo'
            workflow['11']['inputs']['filename_prefix'] = f'MediaStudio_{project["id"][:8]}_shot_{ordinal:02d}'
            workflow['13'] = {'class_type': 'LoadImage', 'inputs': {'image': await self.upload_to_comfy(storyboard_image)}}
            frames = min(81, max(49, 8 * math.ceil(float(shot['data'].get('duration_seconds', 3)) * 2) + 1))
            if model_id == 'wan-5b':
                workflow['7']['inputs']['length'] = frames
                workflow['8']['inputs']['seed'] = secrets.randbits(32)
            else:
                workflow['1']['inputs']['ckpt_name'] = spec['checkpoint']
                workflow['9']['inputs']['noise_seed'] = secrets.randbits(32)
                workflow['12'] = {'class_type': 'LTXVImgToVideo', 'inputs': {
                    'positive': ['5', 0], 'negative': ['5', 1], 'vae': ['1', 2], 'image': ['13', 0],
                    'width': spec['width'], 'height': spec['height'], 'length': frames,
                    'batch_size': 1, 'strength': 0.8}}
                workflow['9']['inputs'].update({'positive': ['12', 0], 'negative': ['12', 1],
                                                 'latent_image': ['12', 2]})
                workflow.pop('6')
            remember_workflow(manifest, workflow_key, workflow)
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                queue = (await client.get(self.settings.comfyui_url + '/queue')).json()
                if queue.get('queue_running') or queue.get('queue_pending'):
                    raise RuntimeError('ComfyUI is busy with another job; retry this local draft later')
                free = await client.post(self.settings.comfyui_url + '/free',
                                         json={'unload_models': True, 'free_memory': True})
                free.raise_for_status()
            await asyncio.sleep(2)
            data, prompt_id = await self._result(workflow, manifest, prompt_key, '11')
            with Image.open(BytesIO(data)) as animated:
                validate_animated_preview(animated, (spec['width'], spec['height']), model_id)
                with tempfile.TemporaryDirectory(dir=root / 'local_drafts/video') as temp:
                    for index in range(animated.n_frames):
                        animated.seek(index)
                        animated.convert('RGB').save(Path(temp) / f'frame_{index:04d}.png')
                    run_ffmpeg(self.settings, ['-framerate', str(spec['fps']), '-i', str(Path(temp) / 'frame_%04d.png'),
                                               '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                                               '-movflags', '+faststart', '-metadata',
                                               'comment=AI-generated DRAFT; non-commercial previsualisation only',
                                               str(target)])
        else:
            prompt_id = json.loads(manifest.read_text(encoding='utf-8')).get(prompt_key) if manifest.exists() else None
        media = probe(target, self.settings)
        video = next((stream for stream in media['streams'] if stream['codec_type'] == 'video'), None)
        if not video or (video['width'], video['height']) != (spec['width'], spec['height']):
            raise RuntimeError(f'Invalid {model_id} MP4 clip')
        if not existing_asset(project, 'draft_clip', shot['id']):
            saved = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
            self.store.add_asset(project['id'], 'draft_clip', spec['provider'], target.relative_to(root),
                                 shot_id=shot['id'], prompt=video_prompt,
                                 settings={'workflow': saved.get(workflow_key)},
                                 source_asset_id=existing_asset(project, 'storyboard_frame', shot['id'])['id'],
                                 metadata={'prompt_id': prompt_id, 'reference_ids': [link['asset_id'] for link in links],
                                           'image_conditioned': True,
                                           'reference_mode': 'text_guidance_from_selected_images',
                                           'model': spec['checkpoint'], 'model_id': model_id})
        return target

    def narration(self, project):
        from kokoro_onnx import Kokoro
        root = self.store.project_dir(project)
        current = existing_asset(project, 'narration')
        version = next_version(project, 'narration') if not current else current['version']
        target = root / (current['relative_path'] if current else f'local_drafts/audio/narration_v{version:03d}.wav')
        if not target.is_file():
            model_dir = ROOT / 'data/models/kokoro'
            voice = Kokoro(str(model_dir / 'kokoro-v1.0.onnx'), str(model_dir / 'voices-v1.0.bin'))
            script = project['plan']['script'].strip()
            if not script:
                raise ValueError('The campaign plan needs a continuous voiceover script')
            voice_id = project.get('narration_voice', DEFAULT_VOICE)
            language = voice_language(voice_id)
            if language is None:
                raise ValueError(f'Narration voice {voice_id} is not installed')
            samples, sample_rate = voice.create(script, voice=voice_id, speed=1.0, lang=language)
            duration = len(samples) / sample_rate
            target_duration = project.get('target_duration_seconds', 15)
            if duration < target_duration * 0.81:
                speed = max(0.85, duration / (target_duration * 0.88))
                samples, sample_rate = voice.create(script, voice=voice_id, speed=speed, lang=language)
                duration = len(samples) / sample_rate
            if duration > target_duration * 0.98:
                speed = min(1.35, duration / (target_duration * 0.95))
                samples, sample_rate = voice.create(script, voice=voice_id, speed=speed, lang=language)
                duration = len(samples) / sample_rate
            if duration > target_duration:
                raise ValueError(f'Continuous voiceover is too long for a {target_duration}-second cut; shorten the script')
            sf.write(target, samples, sample_rate)
        if not existing_asset(project, 'narration'):
            self.store.add_asset(project['id'], 'narration', 'kokoro_onnx', target.relative_to(root),
                                 prompt=project['plan']['script'],
                                 metadata={'voice': project.get('narration_voice', DEFAULT_VOICE), 'timing': 'one continuous take',
                                           'speech_duration_seconds': round(float(probe(target, self.settings)['format']['duration']), 2)})
        return target

    def captions(self, project, audio):
        from faster_whisper import WhisperModel
        root = self.store.project_dir(project)
        current = existing_asset(project, 'captions')
        version = next_version(project, 'captions') if not current else current['version']
        target = root / (current['relative_path'] if current else f'captions/rough_cut_v{version:03d}.srt')
        vtt = root / f'captions/rough_cut_v{version:03d}.vtt'
        if not target.is_file() or not vtt.is_file():
            model = WhisperModel(whisper_model(), device='cpu', compute_type='int8',
                                 download_root=str(ROOT / 'data/models/whisper'))
            segments, _ = model.transcribe(str(audio), language='en', beam_size=1)
            target_duration = project.get('target_duration_seconds', 15)
            parts = [(max(0, item.start), min(target_duration, item.end), item.text.strip()) for item in segments
                     if item.text.strip() and item.start < target_duration]
            if not parts:
                raise RuntimeError('Narration transcription produced no captions')

            def timestamp(value, separator):
                milliseconds = round(value * 1000)
                hours, remain = divmod(milliseconds, 3_600_000)
                minutes, remain = divmod(remain, 60_000)
                seconds, millis = divmod(remain, 1000)
                return f'{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}'

            target.write_text('\n\n'.join(f'{index}\n{timestamp(start, ",")} --> {timestamp(end, ",")}\n{text}'
                                          for index, (start, end, text) in enumerate(parts, 1)) + '\n', encoding='utf-8')
            vtt.write_text('WEBVTT\n\n' + '\n\n'.join(
                f'{timestamp(start, ".")} --> {timestamp(end, ".")}\n{text}' for start, end, text in parts) + '\n', encoding='utf-8')
        if not existing_asset(project, 'captions'):
            self.store.add_asset(project['id'], 'captions', 'faster_whisper', target.relative_to(root),
                                 metadata={'language': 'en', 'webvtt_path': str(vtt.relative_to(root))})
        if not existing_asset(self.store.get_project(project['id']), 'captions_vtt'):
            self.store.add_asset(project['id'], 'captions_vtt', 'faster_whisper', vtt.relative_to(root),
                                 metadata={'language': 'en'})
        return target

    def assemble(self, project, clips, audio, captions):
        root = self.store.project_dir(project)
        current = existing_asset(project, 'rough_cut')
        version = next_version(project, 'rough_cut') if not current else current['version']
        target = root / (current['relative_path'] if current else f'local_drafts/video/rough_cut_v{version:03d}.mp4')
        if not target.is_file():
            args = []
            for clip in clips:
                args.extend(['-i', str(clip)])
            args.extend(['-i', str(audio), '-i', str(captions)])
            filters = ';'.join(
                f'[{index}:v]setpts=(PTS-STARTPTS)*{float(shot["data"].get("duration_seconds", 3)) / float(probe(clip, self.settings)["format"]["duration"]):.8f},'
                f'fps=16,tpad=stop_mode=clone:stop_duration=1,trim=duration={float(shot["data"].get("duration_seconds", 3))},'
                f'setpts=PTS-STARTPTS,scale=1280:720,format=yuv420p[v{index}]'
                for index, (clip, shot) in enumerate(zip(clips, project['shots'])))
            filters += ';' + ''.join(f'[v{index}]' for index in range(len(clips)))
            filters += f'concat=n={len(clips)}:v=1:a=0[v]'
            target_duration = project.get('target_duration_seconds', 15)
            args.extend(['-filter_complex', filters, '-map', '[v]', '-map', f'{len(clips)}:a:0',
                         '-map', f'{len(clips)+1}:s:0', '-t', str(target_duration), '-af', 'apad',
                         '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                         '-c:a', 'aac', '-c:s', 'mov_text', '-movflags', '+faststart',
                         '-metadata', 'comment=AI-generated DRAFT; non-commercial previsualisation only',
                         str(target)])
            run_ffmpeg(self.settings, args, timeout=300)
        media = probe(target, self.settings)
        streams = media['streams']
        video = next((item for item in streams if item['codec_type'] == 'video'), None)
        target_duration = project.get('target_duration_seconds', 15)
        if not video or (video['width'], video['height']) != (1280, 720) or not target_duration - 0.5 <= float(media['format']['duration']) <= target_duration + 0.5:
            raise RuntimeError('Rough cut failed duration or aspect-ratio validation')
        if not any(item['codec_type'] == 'audio' for item in streams) or not any(item['codec_type'] == 'subtitle' for item in streams):
            raise RuntimeError('Rough cut must contain narration and captions')
        if not existing_asset(project, 'rough_cut'):
            inputs = [existing_asset(project, 'draft_clip', shot['id'])['id'] for shot in project['shots']]
            self.store.add_asset(project['id'], 'rough_cut', 'local_ffmpeg', target.relative_to(root),
                                 metadata={'duration_seconds': float(media['format']['duration']),
                                           'width': 1280, 'height': 720, 'captions': True,
                                           'clip_asset_ids': inputs,
                                           'narration_asset_id': existing_asset(project, 'narration')['id'],
                                           'caption_asset_id': existing_asset(project, 'captions')['id']})
        return target

    async def generate(self, project_id, model_id=DEFAULT_VIDEO_MODEL):
        if not self.settings.local_drafts_noncommercial:
            raise ValueError('Local generated media must remain non-commercial drafts')
        require_video_model(model_id, self.settings)
        project = self.store.get_project(project_id)
        if project['approvals']['storyboard']['status'] != 'APPROVED':
            raise ValueError('Storyboard approval is required')
        target_duration = project.get('target_duration_seconds', 15)
        if not project['shots'] or abs(sum(float(shot['data'].get('duration_seconds', 3)) for shot in project['shots']) - target_duration) > 0.05:
            raise ValueError('Scene durations must sum to the project target')
        self.store.reset_video_drafts_for_model(project_id, model_id)
        project = self.store.get_project(project_id)
        clips = []
        for shot in project['shots']:
            project = self.store.get_project(project_id)
            frame = await self.image(project, shot)
            project = self.store.get_project(project_id)
            clips.append(await self.video(project, shot, frame, model_id))
        project = self.store.get_project(project_id)
        narration = await asyncio.to_thread(self.narration, project)
        project = self.store.get_project(project_id)
        captions = await asyncio.to_thread(self.captions, project, narration)
        project = self.store.get_project(project_id)
        output = await asyncio.to_thread(self.assemble, project, clips, narration, captions)
        return {'relative_path': str(output.relative_to(self.store.project_dir(project))),
                'asset_id': existing_asset(self.store.get_project(project_id), 'rough_cut')['id']}
