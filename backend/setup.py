"""Local onboarding, protected configuration writes, and bounded background tasks."""
import asyncio
import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import psutil
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, SecretStr

from .config import ROOT, Settings
from .local_paths import pterm_path, pinokio_home, pinokio_access
from .providers import HiggsfieldProvider
from .setup_assets import destination, installed, install_all, manifest, storage_plan, valid

router = APIRouter(prefix='/api/setup', tags=['setup'])
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()
task = {'status': 'IDLE', 'message': 'No setup task is running.', 'current_bytes': 0, 'total_bytes': 0}


def state_path():
    return Settings().data_dir / 'setup/state.json'


def read_state():
    try:
        return json.loads(state_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def write_state(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2), encoding='utf-8')
    os.replace(temp, path)


def protect(request: Request):
    origin = request.headers.get('origin')
    if origin and origin not in (str(request.base_url).rstrip('/'), 'http://127.0.0.1:8787', 'http://localhost:8787',
                                  'http://127.0.0.1:5173', 'http://localhost:5173'):
        raise HTTPException(403, 'Setup changes must come from the local studio.')
    if not secrets.compare_digest(request.headers.get('x-setup-token', ''), TOKEN):
        raise HTTPException(403, 'Reload Setup & Diagnostics before making changes.')


def command(args, timeout=10):
    with subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Stop only this helper and its children, never the separately managed Pinokio app.
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
            else:
                process.kill()
            process.communicate()
            raise ValueError('Setup helper timed out. Check Pinokio for an installation prompt or a running job, then retry.') from None
        if process.returncode:
            raise ValueError('Command failed. Check the prerequisite or its Pinokio terminal and retry.')
        return stdout.strip()


def windows_supported():
    return sys.platform == 'win32' and sys.getwindowsversion().build >= 22000


async def local_status():
    settings = Settings()
    checks = []
    def add(name, ok, detail):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
    add('Windows 11', windows_supported(), ('Windows build ' + str(sys.getwindowsversion().build)) if sys.platform == 'win32' else platform.platform())
    try:
        gpu = await asyncio.to_thread(command, ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'])
    except (OSError, ValueError, subprocess.SubprocessError):
        gpu = ''
    add('NVIDIA driver', bool(gpu), gpu or 'Install the NVIDIA driver, restart Windows, then check again.')
    add('Pinokio', pterm_path() is not None, str(pinokio_home() or 'Install and open Pinokio, then choose its home folder.'))
    access, access_detail = pinokio_access()
    # An already-running CUDA service remains usable even if the studio is not elevated.
    comfy_ok = False
    try:
        async with httpx.AsyncClient(timeout=6, trust_env=False) as client:
            stats_response, nodes_response = await asyncio.gather(client.get(settings.comfyui_url + '/system_stats'), client.get(settings.comfyui_url + '/object_info'))
            stats_response.raise_for_status()
            nodes_response.raise_for_status()
            stats, nodes = stats_response.json(), nodes_response.json()
        required = set()
        for filename in ('flux_schnell_draft.json', 'ltx_2b_098_distilled_draft.json'):
            required.update(node['class_type'] for node in json.loads((ROOT / 'workflows' / filename).read_text()).values())
        missing = sorted(required - set(nodes))
        cuda = any(device.get('type') == 'cuda' for device in stats.get('devices', []))
        comfy_ok = cuda and not missing
        detail = 'CUDA active; required workflow nodes available.' if comfy_ok else 'CUDA is unavailable or workflow nodes are missing: ' + ', '.join(missing)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        detail = 'Start ComfyUI in Pinokio, then check again. Expected ' + settings.comfyui_url
    add('ComfyUI with CUDA', comfy_ok, detail)
    add('Pinokio runtime access', access or comfy_ok, 'ComfyUI is running with CUDA.' if comfy_ok else access_detail)
    for name in ('ffmpeg', 'ffprobe'):
        try:
            output = await asyncio.to_thread(command, [getattr(settings, name + '_path'), '-version'])
            ok = output.lower().startswith(name + ' version')
        except (OSError, ValueError, subprocess.SubprocessError):
            ok = False
        add(name.upper(), ok, 'Available' if ok else 'Run Install FFmpeg, or rerun the bootstrap installer.')
    assets = []
    for spec in manifest():
        path = destination(spec, settings)
        ok = installed(spec, path)
        assets.append({'label': spec['label'], 'installed': ok, 'bytes': spec['bytes'], 'path': str(path)})
        add(spec['label'], ok, 'Installed; integrity and generation are checked by the local test.' if ok else 'Required download missing or incomplete.')
    return {'ready': all(item['ok'] for item in checks if item['name'] != 'Pinokio runtime access'), 'checks': checks, 'assets': assets,
            'storage': storage_plan(settings), 'ram_gb': round(psutil.virtual_memory().total / 1024**3, 1),
            'models_dir': str(settings.comfyui_models_dir), 'comfyui_url': settings.comfyui_url}


def fingerprint():
    settings = Settings()
    values = [str(settings.comfyui_models_dir), settings.comfyui_url, settings.ffmpeg_path, settings.ffprobe_path]
    for spec in manifest():
        path = destination(spec, settings)
        values.append((str(path), path.stat().st_size, path.stat().st_mtime_ns) if path.exists() else str(path))
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


@router.get('/status')
async def status():
    local = await local_status()
    state, settings = read_state(), Settings()
    tested = state.get('local_test_fingerprint') == fingerprint()
    configured = {'openai': bool(settings.openai_api_key.get_secret_value()),
                  'higgsfield': bool(HiggsfieldProvider(settings).credential())}
    return {'token': TOKEN, 'local': local, 'tested': tested,
            'completed': bool(state.get('completed')) and tested,
            'providers': {name: {'configured': present, 'skipped': name in state.get('skipped', []),
                                 'verification': state.get('providers', {}).get(name)} for name, present in configured.items()},
            'task': task.copy()}


@router.get('/task')
def task_status():
    return task.copy()


def ensure_idle(request):
    if task['status'] == 'RUNNING':
        raise HTTPException(409, 'Wait for the current setup task.')
    runner = getattr(request.app.state, 'job_runner', None)
    if runner:
        with runner.store.connection() as conn:
            if conn.execute("SELECT 1 FROM jobs WHERE status IN ('QUEUED','RUNNING') LIMIT 1").fetchone():
                raise HTTPException(409, 'Wait for studio generation jobs before changing setup.')
    return runner


def save_env(values, path=None):
    path = path or ROOT / '.env'
    text = path.read_text(encoding='utf-8-sig') if path.exists() else (ROOT / '.env.example').read_text(encoding='utf-8')
    for key, value in values.items():
        if any(ord(char) < 32 for char in value) or "'" in value:
            raise ValueError('Use a single-line value without quotes.')
        line = key + "='" + value + "'"
        pattern = r'(?m)^\s*(?:export\s+)?' + re.escape(key) + r'\s*=.*$'
        text, count = re.subn(pattern, lambda _: line, text)
        if not count:
            text += '\n' + line + '\n'
    temp = path.with_name('.env.setup-tmp')
    try:
        temp.write_text(text, encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def reload_runner(runner):
    if runner:
        from .orchestration import OpenAIOrchestrator
        from .local_media import LocalDraftGenerator
        from .premium import PremiumRenderer
        runner.settings = Settings()
        runner.orchestrator = OpenAIOrchestrator(runner.settings)
        runner.local_generator = LocalDraftGenerator(runner.store, runner.settings)
        runner.premium_renderer = PremiumRenderer(runner.store, runner.settings)


class Credential(BaseModel):
    provider: str
    value: SecretStr


@router.post('/credentials', dependencies=[Depends(protect)])
async def credentials(body: Credential, request: Request):
    with LOCK:
        runner = ensure_idle(request)
        key = {'openai': 'OPENAI_API_KEY', 'higgsfield': 'HF_KEY'}.get(body.provider)
        value = body.value.get_secret_value().strip()
        if not key or not value or len(value) > 1024 or re.search(r"[\s'\"\\$]", value):
            raise HTTPException(422, 'Enter a valid single-line credential; saved keys remain unchanged.')
        if body.provider == 'higgsfield' and (value.count(':') != 1 or not all(value.split(':'))):
            raise HTTPException(422, 'Paste the complete Higgsfield key-id:key-secret credential.')
        if key in os.environ:
            raise HTTPException(409, 'This key is set by the server environment. Remove that override and restart before using the wizard.')
        save_env({key: value})
        state = read_state()
        state['skipped'] = [name for name in state.get('skipped', []) if name != body.provider]
        state.setdefault('providers', {}).pop(body.provider, None)
        write_state(state)
        reload_runner(runner)
    return {'saved': True}


class ProviderChoice(BaseModel):
    provider: str


@router.post('/skip', dependencies=[Depends(protect)])
async def skip(body: ProviderChoice):
    if body.provider not in ('openai', 'higgsfield'):
        raise HTTPException(422, 'The local stack is required and cannot be skipped.')
    with LOCK:
        state = read_state()
        state['skipped'] = sorted(set(state.get('skipped', []) + [body.provider]))
        write_state(state)
    return {'skipped': body.provider}


@router.post('/verify', dependencies=[Depends(protect)])
async def verify_provider(body: ProviderChoice):
    if body.provider not in ('openai', 'higgsfield'):
        raise HTTPException(422, 'Unknown provider.')
    settings = Settings()
    # Bind the saved result to the credential checked; a concurrent replacement must not inherit it.
    checked_credential = settings.openai_api_key.get_secret_value() if body.provider == 'openai' else HiggsfieldProvider(settings).credential()
    if body.provider == 'higgsfield':
        result = {'status': 'CONFIGURED_UNVERIFIED' if HiggsfieldProvider(settings).credential() else 'NOT_CONFIGURED',
                  'detail': 'No supported free authentication/balance probe has been verified. Review the API console; the normal quote/render flow verifies access.',
                  'balance': None, 'billing_url': 'https://cloud.higgsfield.ai/'}
    else:
        key = settings.openai_api_key.get_secret_value()
        result = {'status': 'NOT_CONFIGURED', 'detail': 'Enter an OpenAI API key.', 'balance': None,
                  'billing_url': 'https://platform.openai.com/settings/organization/billing/overview'}
        if key:
            try:
                async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                    response = await client.get('https://api.openai.com/v1/models/' + quote(settings.openai_model, safe=''), headers={'Authorization': 'Bearer ' + key})
                code = response.status_code
                result.update(status='ACCESS_VERIFIED' if code == 200 else 'CHECK_FAILED', detail={200: 'Authentication and configured model access verified. Generation and available credit are not verified.',
                    401: 'Authentication failed. Replace the key.', 403: 'This key lacks permission for the model check.',
                    404: 'Configured model is not available to this key.', 429: 'Provider rate or quota limit; check the API dashboard.'}.get(code, 'Provider check failed; try again later.'))
            except httpx.HTTPError:
                result.update(status='UNREACHABLE', detail='Could not reach OpenAI. Check the connection and retry.')
    with LOCK:
        current = Settings()
        current_credential = current.openai_api_key.get_secret_value() if body.provider == 'openai' else HiggsfieldProvider(current).credential()
        if current_credential != checked_credential:
            raise HTTPException(409, 'The credential changed during verification. Check again.')
        state = read_state()
        state.setdefault('providers', {})[body.provider] = result
        write_state(state)
    return result


class Paths(BaseModel):
    models_dir: str
    comfyui_url: str


@router.post('/paths', dependencies=[Depends(protect)])
async def paths(body: Paths, request: Request):
    with LOCK:
        runner = ensure_idle(request)
        candidate = Path(body.models_dir)
        if 'COMFYUI_MODELS_DIR' in os.environ or 'COMFYUI_URL' in os.environ:
            raise HTTPException(409, 'Remove the server environment path override and restart before editing paths here.')
        if not candidate.is_absolute() or not candidate.is_dir() or candidate.name.lower() != 'models':
            raise HTTPException(422, 'Choose the existing ComfyUI models folder. Set Pinokio home in Pinokio before installing ComfyUI.')
        try:
            checked = Settings(comfyui_url=body.comfyui_url)
            save_env({'COMFYUI_MODELS_DIR': str(candidate), 'COMFYUI_URL': checked.comfyui_url})
        except ValueError:
            raise HTTPException(422, 'Use a local HTTP ComfyUI address and a path without quotes or line breaks.') from None
        state = read_state()
        state.pop('local_test_fingerprint', None)
        state['completed'] = False
        write_state(state)
        reload_runner(runner)
    return {'saved': True}


def progress(message, current=0, total=0):
    with LOCK:
        task.update(message=message, current_bytes=current, total_bytes=total)


def local_test():
    settings = Settings()
    for spec in manifest():
        progress('Checking integrity: ' + spec['label'])
        if not valid(spec, destination(spec, settings)):
            raise ValueError('A required model failed checksum validation: ' + spec['label'])
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.get(settings.comfyui_url + '/queue')
        response.raise_for_status()
        queue = response.json()
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise ValueError('ComfyUI is busy. Let its jobs finish before running the test.')
    for name, label in [('benchmark_tts', 'Narration'), ('benchmark_transcription', 'Transcription'),
                        ('benchmark_comfy_image', 'FLUX storyboard'), ('benchmark_assembly', 'FFmpeg assembly'),
                        ('benchmark_ltx_video', 'LTX video')]:
        progress('Testing ' + label + ' locally. This may take several minutes.')
        command([sys.executable, '-m', 'scripts.' + name], timeout=2100)
    with LOCK:
        state = read_state()
        state['local_test_fingerprint'] = fingerprint()
        state['local_test_at'] = time.time()
        write_state(state)


def run_action(action):
    try:
        if action == 'models':
            install_all(Settings(), progress)
        elif action == 'test':
            local_test()
        else:
            progress('Working through Pinokio; open its terminal for detailed progress.' if action == 'comfy' else 'Installing FFmpeg through Windows Package Manager.')
            args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'scripts/setup-local.ps1'), '-Action', action]
            selected = Settings().comfyui_models_dir.parent.parent
            if action == 'comfy' and (selected / 'pinokio.js').is_file():
                args.extend(['-ComfyDirectory', str(selected)])
            command(args, timeout=180 if action == 'comfy' else 1800)
        progress('Finished. Check readiness again. Restart ComfyUI in Pinokio after new model downloads.' if action == 'models' else
                 'ComfyUI dispatched to Pinokio. Follow its installation/startup there, then check readiness.' if action == 'comfy' else 'Finished. Check readiness again.')
        with LOCK:
            task['status'] = 'DONE'
    except Exception as exc:
        with LOCK:
            # Only our own curated ValueError messages are safe for the browser.
            stage = task['message']
            task.update(status='FAILED', message=(stage + ' ' + str(exc)) if isinstance(exc, ValueError) else
                        f'{type(exc).__name__}: setup could not finish. Check connectivity, available disk space and the Pinokio terminal; retry to resume.')


class Action(BaseModel):
    action: str


@router.post('/action', dependencies=[Depends(protect)])
async def action(body: Action, request: Request):
    if body.action not in ('models', 'comfy', 'ffmpeg', 'test'):
        raise HTTPException(422, 'Unknown setup action.')
    if body.action == 'test' and not (await local_status())['ready']:
        raise HTTPException(409, 'Resolve all required local checks before running the generation test.')
    with LOCK:
        ensure_idle(request)
        if body.action == 'models' and not Settings().comfyui_models_dir.is_dir():
            raise HTTPException(409, 'Install ComfyUI and select its models folder first.')
        task.update(status='RUNNING', message='Starting ' + body.action, current_bytes=0, total_bytes=0)
        if body.action == 'test':
            state = read_state()
            state.pop('local_test_fingerprint', None)
            write_state(state)
        threading.Thread(target=run_action, args=(body.action,), daemon=True).start()
    return task.copy()


@router.post('/complete', dependencies=[Depends(protect)])
async def complete():
    local = await local_status()
    with LOCK:
        state = read_state()
        if task['status'] == 'RUNNING' or not local['ready'] or state.get('local_test_fingerprint') != fingerprint():
            raise HTTPException(409, 'The local stack is mandatory. Complete all checks and pass the local generation test first.')
        settings = Settings()
        for name, configured in [('openai', bool(settings.openai_api_key.get_secret_value())), ('higgsfield', bool(HiggsfieldProvider(settings).credential()))]:
            if not configured and name not in state.get('skipped', []):
                raise HTTPException(409, 'Configure or explicitly skip ' + name + '.')
        state['completed'] = True
        write_state(state)
    return {'completed': True}


@router.get('/diagnostics')
async def diagnostics():
    report = await status()
    report.pop('token', None)
    # Exclude local absolute paths/usernames and all credential values.
    for asset in report['local']['assets']:
        asset.pop('path', None)
    report['local'].pop('models_dir', None)
    for item in report['local']['checks']:
        if item['name'] == 'Pinokio':
            item['detail'] = 'Detected' if item['ok'] else 'Not detected'
    report['task'] = {'status': task['status']}
    return report


@router.get('/guide')
def guide():
    path = ROOT / 'output/pdf/easy-setup.pdf'
    if not path.is_file():
        raise HTTPException(404, 'See EASY_SETUP.md in the installation folder.')
    return FileResponse(path, filename='Marketing-Media-System-Easy-Setup.pdf')
