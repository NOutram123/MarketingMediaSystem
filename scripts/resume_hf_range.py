"""Resume verified model prefixes over HTTP Range after HF Xet restarts from zero."""
import argparse
import os
import re
import shutil
import time
from pathlib import Path

import httpx

from backend.config import ROOT
from scripts.install_ltx_models import COMFY_MODELS, SPECS, digest


def check_prefix(client, url, path):
    size = path.stat().st_size
    if not size:
        raise RuntimeError('No saved bytes to resume')
    for offset in (0, size // 2, max(0, size - 1024)):
        with path.open('rb') as stream:
            stream.seek(offset)
            local = stream.read(1024)
        response = client.get(url, headers={'Range': f'bytes={offset}-{offset + 1023}'})
        response.raise_for_status()
        if response.status_code != 206 or response.content != local:
            raise RuntimeError(f'Saved partial differs from upstream at offset {offset}')


def install(name):
    spec = SPECS[name]
    destination = COMFY_MODELS / spec['folder'] / Path(spec['filename']).name
    if destination.exists():
        if digest(destination) != spec['sha256']:
            raise RuntimeError(f'Existing destination differs: {destination}')
        print(f'Already installed and verified: {destination}', flush=True)
        return
    cache = ROOT / 'data/hf_cache'
    candidates = [p for p in cache.rglob(spec['sha256'] + '.*.incomplete') if p.stat().st_size]
    if not candidates:
        raise RuntimeError('No nonempty HF Xet partial found')
    partial = max(candidates, key=lambda p: p.stat().st_size)
    url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{spec['filename']}"
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(120, connect=20)) as client:
        check_prefix(client, url, partial)
        print(f'{name}: verified {partial.stat().st_size:,} saved bytes', flush=True)
        attempts = 0
        while True:
            offset = partial.stat().st_size
            try:
                with client.stream('GET', url, headers={'Range': f'bytes={offset}-'}) as response:
                    response.raise_for_status()
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('content-range', ''))
                    if response.status_code != 206 or not match or int(match.group(1)) != offset:
                        raise RuntimeError('Server did not honour the requested byte range')
                    total = int(match.group(3))
                    if shutil.disk_usage(cache).free < total - offset + 1024**3:
                        raise RuntimeError('Insufficient free disk for verified model download')
                    next_report = offset + 256 * 1024**2
                    with partial.open('ab') as stream:
                        for chunk in response.iter_bytes(chunk_size=8 * 1024**2):
                            stream.write(chunk)
                            if stream.tell() >= next_report:
                                print(f'{name}: {stream.tell():,}/{total:,} bytes', flush=True)
                                next_report += 256 * 1024**2
                if partial.stat().st_size == total:
                    break
                raise RuntimeError('Transfer ended before expected length')
            except (httpx.HTTPError, OSError) as exc:
                attempts += 1
                if attempts >= 8:
                    raise RuntimeError(f'{name}: repeated transfer failures at {partial.stat().st_size:,} bytes') from exc
                print(f'{name}: transfer interrupted at {partial.stat().st_size:,} bytes; retrying', flush=True)
                time.sleep(min(attempts * 2, 15))
    actual = digest(partial)
    if actual != spec['sha256']:
        raise RuntimeError(f'{name}: SHA-256 mismatch: {actual}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(partial, destination)
    except OSError:
        shutil.copy2(partial, destination)
    print(f'{name}: installed {destination} ({destination.stat().st_size:,} bytes, SHA-256 verified)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', choices=SPECS)
    install(parser.parse_args().model)
