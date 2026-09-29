"""Read-only verification that interrupted Hugging Face files contain a contiguous prefix."""
from pathlib import Path

import httpx

from backend.config import ROOT
from scripts.install_ltx_models import SPECS


def main():
    cache = ROOT / 'data/hf_cache'
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        for spec in SPECS.values():
            candidates = [p for p in cache.rglob(spec['sha256'] + '.*.incomplete') if p.stat().st_size]
            if not candidates:
                print(spec['filename'], 'no nonempty partial')
                continue
            path = max(candidates, key=lambda p: p.stat().st_size)
            size = path.stat().st_size
            url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{spec['filename']}"
            checks = []
            for offset in (0, size // 2, max(0, size - 1024)):
                with path.open('rb') as stream:
                    stream.seek(offset)
                    local = stream.read(1024)
                response = client.get(url, headers={'Range': f'bytes={offset}-{offset + 1023}'})
                response.raise_for_status()
                checks.append(response.status_code == 206 and local == response.content)
            print(spec['filename'], 'partial_bytes=', size, 'range_checks=', checks)


if __name__ == '__main__':
    main()
