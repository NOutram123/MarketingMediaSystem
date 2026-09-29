"""Download the approved low-VRAM LTX weights from official repositories.

Verify upstream SHA-256 before linking into the existing ComfyUI model folders.
Never replace an existing model file.
"""
import argparse
import hashlib
import os
from pathlib import Path

from huggingface_hub import hf_hub_download

from backend.config import ROOT, Settings

COMFY_MODELS = Settings().comfyui_models_dir
SPECS = {
    'ltx': {
        'repo': 'Lightricks/LTX-Video',
        'revision': '8984fa25007f376c1a299016d0957a37a2f797bb',
        'filename': 'ltxv-2b-0.9.8-distilled-fp8.safetensors',
        'sha256': 'd6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15',
        'folder': 'checkpoints',
    },
    't5': {
        'repo': 'Comfy-Org/mochi_preview_repackaged',
        'revision': 'ed4b8585dc4d3204397291c35e100884686178d6',
        'filename': 'split_files/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors',
        'sha256': 'a498f0485dc9536735258018417c3fd7758dc3bccc0a645feaa472b34955557a',
        'folder': 'text_encoders',
    },
}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def install(name):
    spec = SPECS[name]
    destination = COMFY_MODELS / spec['folder'] / Path(spec['filename']).name
    if destination.exists():
        if digest(destination) != spec['sha256']:
            raise RuntimeError(f'Existing file differs from expected checksum: {destination}')
        print(f'{name}: already installed and verified at {destination}', flush=True)
        return
    cached = Path(hf_hub_download(repo_id=spec['repo'], filename=spec['filename'],
                                  revision=spec['revision'], cache_dir=ROOT / 'data/hf_cache'))
    actual_hash = digest(cached)
    if actual_hash != spec['sha256']:
        raise RuntimeError(f'{name}: hash mismatch; expected {spec["sha256"]}, got {actual_hash}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(cached, destination)
    except OSError:
        import shutil
        shutil.copy2(cached, destination)
    print(f'{name}: installed {destination} ({destination.stat().st_size} bytes, SHA256 {actual_hash})', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', choices=SPECS)
    install(parser.parse_args().model)
