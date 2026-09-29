"""Generate and validate one real ComfyUI image; keep output and timings."""
import json
import secrets
import struct
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psutil

from backend.config import ROOT, Settings
from backend.providers import ComfyProvider
import asyncio


def gpu_memory_mib():
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True)
        return int(result.stdout.strip().splitlines()[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


async def main():
    settings = Settings()
    if not settings.local_drafts_noncommercial:
        raise RuntimeError('Local draft non-commercial policy must be enabled')
    provider = ComfyProvider(settings)
    workflow = json.loads((ROOT / 'workflows/flux_schnell_draft.json').read_text())
    workflow['5']['inputs']['seed'] = secrets.randbits(32)
    output_dir = settings.data_dir / 'benchmarks'
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    initial_vram = gpu_memory_mib()
    peak_vram = initial_vram
    peak_ram = psutil.virtual_memory().used
    submitted = await provider.submit(workflow, str(uuid4()))
    prompt_id = submitted['prompt_id']
    if submitted.get('node_errors'):
        raise RuntimeError(f'ComfyUI workflow rejected: {submitted["node_errors"]}')
    while time.monotonic() - started < 900:
        await asyncio.sleep(2)
        current_vram = gpu_memory_mib()
        if current_vram is not None:
            peak_vram = max(peak_vram or 0, current_vram)
        peak_ram = max(peak_ram, psutil.virtual_memory().used)
        history = (await provider.history(prompt_id)).get(prompt_id)
        if not history:
            continue
        if history.get('status', {}).get('status_str') == 'error':
            raise RuntimeError(f'ComfyUI generation failed: {history["status"].get("messages", [])[-2:]}')
        images = history.get('outputs', {}).get('7', {}).get('images', [])
        if images:
            info = images[0]
            async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
                response = await client.get(settings.comfyui_url + '/view', params={'filename': info['filename'], 'subfolder': info.get('subfolder', ''), 'type': info.get('type', 'output')})
                response.raise_for_status()
                data = response.content
            if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) < 1000:
                raise RuntimeError('ComfyUI returned an invalid or empty PNG')
            width, height = struct.unpack('>II', data[16:24])
            if (width, height) != (512, 512):
                raise RuntimeError(f'Unexpected image dimensions: {width}x{height}')
            image_path = output_dir / 'flux_schnell_storyboard_001.png'
            image_path.write_bytes(data)
            report = {'provider': 'ComfyUI', 'model': workflow['1']['inputs']['ckpt_name'], 'prompt_id': prompt_id,
                      'seed': workflow['5']['inputs']['seed'],
                      'width': width, 'height': height, 'duration_seconds': round(time.monotonic() - started, 2),
                      'vram_initial_mib': initial_vram, 'vram_peak_mib': peak_vram, 'ram_peak_bytes': peak_ram,
                      'output': str(image_path), 'bytes': len(data),
                      'classification': 'DRAFT', 'commercial_use': False, 'status': 'PASS'}
            (output_dir / 'flux_schnell_benchmark.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
            return
    raise TimeoutError('ComfyUI did not finish within 15 minutes')


if __name__ == '__main__':
    asyncio.run(main())
