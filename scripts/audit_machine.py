"""Repeatable, read-only Phase 1 machine audit. Does not collect credentials."""
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

from backend.config import ROOT, Settings


def command(args, timeout=10):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def cuda_driver_version():
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=10, check=True)
        match = re.search(r'CUDA (?:UMD )?Version:\s*([\d.]+)', result.stdout)
        return match.group(1) if match else None
    except (OSError, subprocess.SubprocessError):
        return None


def main():
    settings = Settings()
    comfy_root = Path(r'C:\pinokio\api\comfy.git\app')
    manager = comfy_root / 'custom_nodes/ComfyUI-Manager'
    models_root = comfy_root / 'models'
    disks = {}
    for letter in 'CDE':
        drive = Path(f'{letter}:/')
        if drive.exists():
            usage = shutil.disk_usage(drive)
            disks[letter] = {'total_bytes': usage.total, 'free_bytes': usage.free}
    model_files = []
    for folder in ('checkpoints', 'text_encoders', 'clip', 'diffusion_models', 'vae', 'loras'):
        path = models_root / folder
        if path.exists():
            for item in path.iterdir():
                if item.is_file() and item.suffix.lower() in {'.safetensors', '.gguf', '.ckpt'}:
                    model_files.append({'folder': folder, 'name': item.name, 'bytes': item.stat().st_size})
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            comfy_stats = client.get(settings.comfyui_url + '/system_stats').json()
    except (httpx.HTTPError, ValueError):
        comfy_stats = None
    paths = {name: shutil.which(name) for name in ('python', 'py', 'node', 'npm', 'git', 'ffmpeg', 'pterm', 'nvidia-smi')}
    audit = {
        'at_utc': datetime.now(timezone.utc).isoformat(), 'os': platform.platform(),
        'cpu': platform.processor(), 'ram_total_bytes': psutil.virtual_memory().total,
        'disks': disks,
        'gpu': command(['nvidia-smi', '--query-gpu=name,memory.total,driver_version,temperature.gpu', '--format=csv,noheader,nounits']),
        'cuda_driver': cuda_driver_version(),
        'python': command(['python', '--version']) or platform.python_version(),
        'node': command(['node', '--version']), 'npm': command(['npm.cmd', '--version']),
        'git': command(['git', '--version']), 'ffmpeg': command([settings.ffmpeg_path, '-version']),
        'pinokio_installed': Path.home().joinpath('AppData/Local/Programs/Pinokio/Pinokio.exe').exists(),
        'pinokio_home_exists': Path('C:/pinokio').exists(),
        'comfyui_path': str(comfy_root) if comfy_root.exists() else None,
        'comfyui_git_revision': command(['git', '-C', str(comfy_root), 'rev-parse', 'HEAD']),
        'comfyui_api': comfy_stats,
        'manager_installed': manager.exists(),
        'manager_git_revision': command(['git', '-C', str(manager), 'rev-parse', 'HEAD']) if manager.exists() else None,
        'custom_nodes': sorted(p.name for p in (comfy_root / 'custom_nodes').iterdir() if p.is_dir() and p.name != '__pycache__') if (comfy_root / 'custom_nodes').exists() else [],
        'model_files': sorted(model_files, key=lambda x: (x['folder'], x['name'])),
        'path_entries': [entry for entry in os.environ.get('PATH', '').split(os.pathsep) if entry],
        'command_paths': paths,
        'api_credentials_present': {name: bool(getattr(settings, name).get_secret_value()) for name in ('openai_api_key', 'hf_api_key_id', 'hf_api_key_secret', 'elevenlabs_api_key')},
    }
    output = ROOT / 'docs/hardware_software_audit.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(f'Wrote {output}')


if __name__ == '__main__':
    main()
