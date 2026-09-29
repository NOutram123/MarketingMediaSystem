"""Pinned, resumable model installation. Never overwrite existing model files."""
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import httpx
from .config import ROOT


def manifest():
    return json.loads((ROOT / 'config/setup-models.json').read_text(encoding='utf-8'))


def destination(spec, settings):
    base = settings.comfyui_models_dir if spec['root'] == 'comfy' else ROOT / 'data/models'
    path = base / spec['path']
    if spec['path'].startswith('whisper/tiny.en/'):
        return whisper_directory() / path.name
    return path


def whisper_directory():
    # Reuse one complete cache snapshot, never a mixture of files from different snapshots.
    base = ROOT / 'data/models/whisper'
    direct = base / 'tiny.en'
    required = {Path(spec['path']).name: spec['bytes'] for spec in manifest() if spec['path'].startswith('whisper/tiny.en/')}
    for folder in [direct, *sorted((base / 'models--Systran--faster-whisper-tiny.en/snapshots').glob('*'))]:
        if all((folder / name).is_file() and (folder / name).stat().st_size == size for name, size in required.items()):
            return folder
    return direct


def acceptable_sizes(spec):
    return [spec['bytes'], *[item['bytes'] for item in spec.get('accepted_existing', [])]]


def installed(spec, path):
    return path.is_file() and path.stat().st_size in acceptable_sizes(spec)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def valid(spec, path):
    return installed(spec, path) and sha256(path) in [spec['sha256'], *[item['sha256'] for item in spec.get('accepted_existing', [])]]


def storage_plan(settings):
    volumes = {}
    for spec in manifest():
        path = destination(spec, settings)
        if installed(spec, path):
            continue
        parent = path.parent
        while not parent.exists():
            parent = parent.parent
        volume = str(parent.resolve().anchor)
        item = volumes.setdefault(volume, {'volume': volume, 'needed_bytes': 0, 'free_bytes': shutil.disk_usage(parent).free})
        partial = path.with_name(path.name + '.partial')
        have = min(partial.stat().st_size, spec['bytes']) if partial.exists() else 0
        item['needed_bytes'] += spec['bytes'] - have
    for item in volumes.values():
        item['required_with_headroom_bytes'] = item['needed_bytes'] + 2 * 1024**3
        item['enough'] = item['free_bytes'] >= item['required_with_headroom_bytes']
    return list(volumes.values())


def download(spec, target: Path, progress, client=None):
    if target.exists():
        progress(f"Verifying {spec['label']}", 0, spec['bytes'])
        if not valid(spec, target):
            raise ValueError(f"Existing {spec['label']} differs from the approved file. Move it aside manually before retrying; it was not overwritten.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + '.partial')
    offset = part.stat().st_size if part.exists() else 0
    if offset > spec['bytes']:
        raise ValueError(f"Partial {spec['label']} is too large. Move that .partial file aside and retry.")
    if offset < spec['bytes']:
        with (client or httpx.Client(follow_redirects=True, timeout=60, trust_env=False)) as session:
            with session.stream('GET', spec['url'], headers={'Range': f'bytes={offset}-', 'Accept-Encoding': 'identity'}) as response:
                response.raise_for_status()
                if response.status_code == 206:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('content-range', ''))
                    if not match or int(match[1]) != offset or int(match[3]) != spec['bytes']:
                        raise ValueError('Download server returned an inconsistent byte range; retry later.')
                elif response.status_code == 200:
                    offset = 0  # Server does not support resuming; safely restart the partial only.
                else:
                    raise ValueError('Download server did not return file data.')
                with part.open('ab' if offset else 'wb') as output:
                    for chunk in response.iter_bytes(1024 * 1024):
                        if offset + len(chunk) > spec['bytes']:
                            raise ValueError('Download exceeded its pinned size.')
                        output.write(chunk)
                        offset += len(chunk)
                        progress(f"Downloading {spec['label']}", offset, spec['bytes'])
    progress(f"Verifying {spec['label']}", offset, spec['bytes'])
    if not valid(spec, part):
        raise ValueError(f"Checksum failed for {spec['label']}. Move its .partial file aside and retry.")
    # Windows rename refuses an existing destination, including one created while downloading.
    if target.exists():
        raise ValueError('Destination appeared during download; existing file preserved.')
    os.rename(part, target)


def install_all(settings, progress):
    if any(not item['enough'] for item in storage_plan(settings)):
        raise ValueError('Insufficient storage on a destination drive. Free space or choose another Pinokio home before installing.')
    for spec in manifest():
        download(spec, destination(spec, settings), progress)
