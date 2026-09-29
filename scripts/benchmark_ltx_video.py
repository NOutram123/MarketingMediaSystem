"""Generate a real 3 s non-commercial LTX draft and validate its playable MP4."""
import argparse
import asyncio
import json
import secrets
import subprocess
import tempfile
import time
from uuid import uuid4

import httpx
import psutil
from PIL import Image

from backend.config import ROOT, Settings
from backend.providers import ComfyProvider
from scripts.benchmark_comfy_image import gpu_memory_mib


def probe(path, settings):
    result = subprocess.run([settings.ffprobe_path, '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(result.stdout)


async def main(width=512, height=320):
    settings = Settings()
    if not settings.local_drafts_noncommercial:
        raise RuntimeError('Local draft non-commercial policy must be enabled')
    if width % 32 or height % 32 or width < 256 or height < 256:
        raise ValueError('LTX benchmark dimensions must be at least 256 and divisible by 32')
    workflow = json.loads((ROOT / 'workflows/ltx_2b_098_distilled_draft.json').read_text())
    workflow['6']['inputs'].update(width=width, height=height)
    workflow['9']['inputs']['noise_seed'] = secrets.randbits(32)
    suffix = '' if (width, height) == (512, 320) else f'_{width}x{height}'
    workflow['11']['inputs']['filename_prefix'] += suffix
    provider = ComfyProvider(settings)
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        queue_response = await client.get(settings.comfyui_url + '/queue')
        queue_response.raise_for_status()
        queue = queue_response.json()
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise RuntimeError('ComfyUI has another job; LTX benchmark will not interrupt it')
        free_response = await client.post(settings.comfyui_url + '/free',
                                          json={'unload_models': True, 'free_memory': True})
        free_response.raise_for_status()
    await asyncio.sleep(2)
    output_dir = settings.data_dir / 'benchmarks'
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    initial_vram = gpu_memory_mib()
    peak_vram = initial_vram or 0
    peak_ram = psutil.virtual_memory().used
    submitted = await provider.submit(workflow, str(uuid4()))
    if submitted.get('node_errors'):
        raise RuntimeError(f'ComfyUI workflow rejected: {submitted["node_errors"]}')
    prompt_id = submitted['prompt_id']
    print(f'Submitted LTX prompt {prompt_id}', flush=True)
    while time.monotonic() - started < 1800:
        await asyncio.sleep(2)
        peak_vram = max(peak_vram, gpu_memory_mib() or 0)
        peak_ram = max(peak_ram, psutil.virtual_memory().used)
        history = (await provider.history(prompt_id)).get(prompt_id)
        if not history:
            continue
        status = history.get('status', {})
        if status.get('status_str') == 'error':
            raise RuntimeError(f'ComfyUI LTX failed: {status.get("messages", [])[-2:]}')
        saved = history.get('outputs', {}).get('11', {})
        media = saved.get('gifs', []) or saved.get('images', [])
        if not media:
            continue
        info = media[0]
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.get(settings.comfyui_url + '/view', params={
                'filename': info['filename'], 'subfolder': info.get('subfolder', ''),
                'type': info.get('type', 'output')})
            response.raise_for_status()
        webp = output_dir / f'ltx_draft{suffix}.webp'
        webp.write_bytes(response.content)
        if not response.content.startswith(b'RIFF') or b'WEBP' not in response.content[:16]:
            raise RuntimeError('ComfyUI returned invalid WebP')
        with Image.open(webp) as image:
            frame_count = image.n_frames
            if image.size != (width, height) or frame_count != 49:
                raise RuntimeError(f'Invalid WebP dimensions/frame count: {image.size}, {frame_count}')
            with tempfile.TemporaryDirectory(dir=output_dir) as temp_dir:
                for index in range(frame_count):
                    image.seek(index)
                    image.convert('RGB').save(f'{temp_dir}/frame_{index:04d}.png')
                mp4 = output_dir / f'ltx_draft{suffix}.mp4'
                subprocess.run([settings.ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-y',
                                '-framerate', '16', '-i', f'{temp_dir}/frame_%04d.png', '-an',
                                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                                '-metadata', 'comment=AI-generated DRAFT; non-commercial previsualisation only',
                                str(mp4)], check=True, timeout=120)
        metadata = probe(mp4, settings)
        video = next((s for s in metadata['streams'] if s['codec_type'] == 'video'), None)
        duration = float(metadata['format']['duration'])
        if not video or video['width'] != width or video['height'] != height or not 2.8 <= duration <= 3.5:
            raise RuntimeError(f'Invalid LTX MP4 dimensions/duration: {video}, {duration}')
        if int(video.get('nb_frames', 0)) < 45:
            raise RuntimeError(f'Too few LTX frames: {video.get("nb_frames")}')
        messages = status.get('messages', [])
        events = {kind: payload['timestamp'] for kind, payload in messages
                  if kind in {'execution_start', 'execution_success'} and 'timestamp' in payload}
        comfy_seconds = round((events['execution_success'] - events['execution_start']) / 1000, 2) \
            if {'execution_start', 'execution_success'} <= events.keys() else None
        report = {'provider': 'ComfyUI LTX', 'model': workflow['1']['inputs']['ckpt_name'],
                  'seed': workflow['9']['inputs']['noise_seed'],
                  'prompt_id': prompt_id, 'width': video['width'], 'height': video['height'],
                  'frames': int(video['nb_frames']), 'duration_seconds': round(duration, 2),
                  'comfy_execution_seconds': comfy_seconds,
                  'generation_and_conversion_seconds': round(time.monotonic() - started, 2),
                  'vram_initial_mib': initial_vram, 'vram_peak_mib': peak_vram,
                  'ram_peak_bytes': peak_ram, 'output': str(mp4), 'bytes': mp4.stat().st_size,
                  'classification': 'AI-generated DRAFT', 'commercial_use': False, 'status': 'PASS'}
        (output_dir / f'ltx_benchmark{suffix}.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return
    raise TimeoutError('ComfyUI LTX did not finish within 30 minutes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--width', type=int, default=512)
    parser.add_argument('--height', type=int, default=320)
    args = parser.parse_args()
    asyncio.run(main(args.width, args.height))
