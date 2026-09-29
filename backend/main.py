import asyncio
from typing import Literal
from uuid import UUID
import shutil
import subprocess
import psutil
from contextlib import asynccontextmanager
from functools import lru_cache
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from .config import Settings, ROOT
from .providers import ComfyProvider, HiggsfieldProvider, ElevenLabsProvider, Health
from .orchestration import load_profiles
from .schemas import BrandKit, BriefUpdate, GateReview, ProjectCreate, InputUpdate, ReferenceMetadataUpdate, ScriptUpdate, DirectionUpdate, ShotUpdate, VoiceUpdate
from .reference_suggestions import suggest_references
from .treatment import extract_treatment
from .voices import english_voices
from .video_models import DEFAULT_VIDEO_MODEL, require_video_model, video_model_status
from pydantic import BaseModel
from .duration import infer_duration
from .preflight import plan_preview
from .store import Store
from .jobs import JobRunner
from .uploads import MAX_REFERENCE_BYTES, save_reference
from .premium import preflight as premium_preflight, create_quote as create_premium_quote, run_fingerprint as premium_run_fingerprint
from .setup import router as setup_router


@lru_cache
def get_store() -> Store:
    return Store(Settings().data_dir)


@asynccontextmanager
async def lifespan(application):
    runner = JobRunner(get_store(), Settings())
    await runner.start()
    application.state.job_runner = runner
    try:
        yield
    finally:
        await runner.stop()


app = FastAPI(title='Hybrid AI Media Studio', version='0.2.0', lifespan=lifespan)
app.include_router(setup_router)


@app.middleware('http')
async def avoid_generation_during_setup(request, call_next):
    from .setup import task
    if request.method == 'POST' and request.url.path.startswith('/api/projects/') and task['status'] == 'RUNNING':
        return JSONResponse(status_code=409, content={'detail': 'Wait for the local setup task before starting or changing generation.'})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, exc):
    # Never echo a malformed credential submission in a validation response.
    if request.url.path.startswith('/api/setup/'):
        return JSONResponse(status_code=422, content={'detail': 'Invalid setup request. Check the fields and try again.'})
    from fastapi.exception_handlers import request_validation_exception_handler
    return await request_validation_exception_handler(request, exc)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
                   allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Content-Type', 'X-Setup-Token'])


def project_or_404(store, project_id):
    try:
        return store.get_project(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail='Project not found') from None


def reviewed_or_409(operation):
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get('/api/health')
def health():
    return {'status': 'ok', 'phase': 2, 'phase_1_complete': True, 'phase_2_complete': True, 'phase_complete': True,
            'local_drafts_noncommercial': Settings().local_drafts_noncommercial}


@app.get('/api/providers', response_model=list[Health])
async def providers():
    settings = Settings()
    results = list(await asyncio.gather(*(p(settings).health_check() for p in (ComfyProvider, HiggsfieldProvider, ElevenLabsProvider))))
    openai_configured = bool(settings.openai_api_key.get_secret_value())
    validation_recorded = (ROOT / 'data/benchmarks/openai_benchmark.json').exists()
    results.append(Health(provider='openai', status='CONFIGURED' if openai_configured else 'NOT_CONFIGURED',
                          detail=('A live validation result is recorded locally' if validation_recorded else 'Run the live validation script')
                          if openai_configured else 'Set OPENAI_API_KEY in .env'))
    return results


@app.get('/api/resources')
def resources():
    settings = Settings()
    disk = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else settings.data_dir.parent)
    try:
        gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        gpu = None
    memory = psutil.virtual_memory()
    return {'gpu_csv': gpu, 'ram_total_bytes': memory.total, 'ram_available_bytes': memory.available, 'disk_free_bytes': disk.free}


@app.get('/api/model-profiles')
def model_profiles():
    return load_profiles().model_dump()


@app.get('/api/voices')
def voices():
    return english_voices()


@app.get('/api/local-video-models')
def local_video_models():
    return video_model_status(Settings())


class LocalDraftRequest(BaseModel):
    video_model: str = DEFAULT_VIDEO_MODEL


@app.post('/api/projects', status_code=201)
def create_project(body: ProjectCreate, store: Store = Depends(get_store)):
    try:
        load_profiles().get(body.profile_id)
    except KeyError:
        raise HTTPException(status_code=422, detail='Unknown model profile') from None
    duration = body.target_duration_seconds or infer_duration(body.brief + '\n' + body.treatment_notes)[0]
    return store.create_project(body.title, body.brief, body.brand.model_dump(), body.profile_id, duration,
                                body.treatment_notes)


@app.get('/api/projects')
def list_projects(store: Store = Depends(get_store)):
    return store.list_projects()


@app.get('/api/projects/{project_id}')
def get_project(project_id: str, store: Store = Depends(get_store)):
    return project_or_404(store, project_id)


@app.delete('/api/projects/{project_id}', status_code=204)
def delete_project(project_id: str, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    reviewed_or_409(lambda: store.delete_project(project_id))


@app.get('/api/projects/{project_id}/reference-suggestions')
def reference_suggestions(project_id: str, store: Store = Depends(get_store)):
    return suggest_references(project_or_404(store, project_id))


@app.get('/api/projects/{project_id}/treatment-extract')
def treatment_extract(project_id: str, store: Store = Depends(get_store)):
    return extract_treatment(project_or_404(store, project_id)['treatment_notes'])


@app.get('/api/projects/{project_id}/plan-preview')
def get_plan_preview(project_id: str, store: Store = Depends(get_store)):
    return plan_preview(project_or_404(store, project_id))


@app.put('/api/projects/{project_id}/input')
def update_input(project_id: str, body: InputUpdate, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.update_input(
        project_id, body.brief, body.brand.model_dump(), body.target_duration_seconds, body.treatment_notes))


@app.put('/api/projects/{project_id}/voice')
def update_voice(project_id: str, body: VoiceUpdate, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.update_voice(project_id, body.voice_id))


@app.post('/api/projects/{project_id}/references', status_code=201)
async def upload_reference(project_id: str, file: UploadFile = File(...),
                           role: str = Form('other'), description: str = Form(''),
                           store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    data = await file.read(MAX_REFERENCE_BYTES + 1)
    try:
        return save_reference(store, project_id, data, file.filename or '', role, description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put('/api/projects/{project_id}/references/{asset_id}')
def update_reference(project_id: str, asset_id: str, body: ReferenceMetadataUpdate,
                     store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.update_reference(project_id, asset_id, body.role, body.description))


@app.delete('/api/projects/{project_id}/references/{asset_id}')
def delete_reference(project_id: str, asset_id: str, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.delete_reference(project_id, asset_id))


@app.get('/api/projects/{project_id}/assets/{asset_id}/file')
def asset_file(project_id: str, asset_id: str, store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    asset = store.get_asset(project_id, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail='Asset not found')
    root = store.project_dir(project).resolve()
    path = (root / asset['relative_path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail='Asset file not found')
    return FileResponse(path)


@app.put('/api/projects/{project_id}/shots/{shot_id}')
def update_shot(project_id: str, shot_id: str, body: ShotUpdate, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.update_shot(project_id, shot_id, body.model_dump()))


@app.put('/api/projects/{project_id}/shots/{shot_id}/references/{asset_id}')
def attach_reference(project_id: str, shot_id: str, asset_id: str,
                     guidance: str = '', store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    if len(guidance) > 2000:
        raise HTTPException(status_code=422, detail='Guidance is too long')
    return reviewed_or_409(lambda: store.attach_reference(project_id, shot_id, asset_id, guidance))


@app.delete('/api/projects/{project_id}/shots/{shot_id}/references/{asset_id}')
def detach_reference(project_id: str, shot_id: str, asset_id: str, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.detach_reference(project_id, shot_id, asset_id))


@app.put('/api/projects/{project_id}/brand')
def update_brand(project_id: str, body: BrandKit, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return store.update_brand(project_id, body.model_dump())


@app.put('/api/projects/{project_id}/brief')
def update_brief(project_id: str, body: BriefUpdate, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return store.update_brief(project_id, body.brief)


@app.put('/api/projects/{project_id}/script')
def update_script(project_id: str, body: ScriptUpdate, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.update_script(project_id, body.script))


@app.put('/api/projects/{project_id}/direction')
def update_direction(project_id: str, body: DirectionUpdate, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.update_direction(project_id, body.concept, body.script))


@app.post('/api/projects/{project_id}/approvals/{gate}')
def review_gate(project_id: str, gate: str, body: GateReview, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    return reviewed_or_409(lambda: store.review_gate(project_id, gate, body.approve, body.note))


@app.post('/api/projects/{project_id}/storyboard')
def create_storyboard(project_id: str, store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    if not project['plan']:
        raise HTTPException(status_code=409, detail='Concept plan is missing')
    return reviewed_or_409(lambda: store.set_shots(project_id, project['plan']['shots']))


@app.put('/api/projects/{project_id}/storyboard')
def replace_storyboard(project_id: str, body: list[ShotUpdate], store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    if len(body) > 20:
        raise HTTPException(status_code=422, detail='Use at most 20 scenes')
    return reviewed_or_409(lambda: store.set_shots(project_id, [shot.model_dump() for shot in body]))


@app.post('/api/projects/{project_id}/plan', status_code=202)
def queue_plan(project_id: str, store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    preview = plan_preview(project)
    blockers = [warning['message'] for warning in preview['warnings'] if warning['severity'] == 'blocker']
    if blockers:
        raise HTTPException(status_code=409, detail=' '.join(blockers))
    if project['approvals']['brief']['status'] != 'APPROVED':
        raise HTTPException(status_code=409, detail='Creative brief approval is required')
    if not Settings().openai_api_key.get_secret_value():
        raise HTTPException(status_code=409, detail='OpenAI API key is not configured')
    return store.create_job(project_id, 'openai_plan', {'profile_id': project['profile_id']})


@app.post('/api/projects/{project_id}/claim-suggestions', status_code=202)
def queue_claim_suggestions(project_id: str, store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    if not Settings().openai_api_key.get_secret_value():
        raise HTTPException(status_code=409, detail='OpenAI API key is not configured')
    return store.create_job(project_id, 'openai_claim_suggestions', {'profile_id': project['profile_id']})


@app.post('/api/projects/{project_id}/local-draft', status_code=202)
def queue_local_draft(project_id: str, body: LocalDraftRequest = LocalDraftRequest(),
                      store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    if project['approvals']['storyboard']['status'] != 'APPROVED':
        raise HTTPException(status_code=409, detail='Storyboard approval is required')
    if not project['shots'] or abs(sum(float(shot['data'].get('duration_seconds', 3)) for shot in project['shots']) - project['target_duration_seconds']) > 0.05:
        raise HTTPException(status_code=409, detail='Scene durations must add up to the target film length')
    if not Settings().local_drafts_noncommercial:
        raise HTTPException(status_code=409, detail='Non-commercial draft policy is required')
    try:
        require_video_model(body.video_model, Settings())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return store.create_job(project_id, 'local_draft', {'video_model': body.video_model})


@app.get('/api/projects/{project_id}/premium/preflight')
def get_premium_preflight(project_id: str, resolution: Literal['480p', '720p'] = '480p',
                          store: Store = Depends(get_store)):
    return premium_preflight(project_or_404(store, project_id), resolution)


class PremiumEstimateRequest(BaseModel):
    resolution: Literal['480p', '720p'] = '480p'


@app.post('/api/projects/{project_id}/premium/estimate')
async def estimate_premium(project_id: str, body: PremiumEstimateRequest = PremiumEstimateRequest(),
                           store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    if any(job['kind'] == 'premium_render' and job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
        raise HTTPException(status_code=409, detail='Wait for the active Higgsfield render before estimating again')
    try:
        return await create_premium_quote(store, project_id, HiggsfieldProvider(Settings()), body.resolution)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        # Provider responses can contain request details. Keep them out of the UI.
        raise HTTPException(status_code=502, detail='Higgsfield estimate or reference upload failed; check API access and balance') from None


@app.get('/api/projects/{project_id}/premium/runs/{run_id}')
def get_premium_run(project_id: str, run_id: str, store: Store = Depends(get_store)):
    project_or_404(store, project_id)
    try:
        return store.get_premium_run(project_id, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail='Higgsfield run not found') from None


@app.post('/api/projects/{project_id}/premium/runs/{run_id}/approve')
def approve_premium(project_id: str, run_id: str, store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    run = store.get_premium_run(project_id, run_id)
    return reviewed_or_409(lambda: store.approve_premium_run(project_id, run_id, premium_run_fingerprint(project, run)))


@app.post('/api/projects/{project_id}/premium/runs/{run_id}/render', status_code=202)
def render_premium(project_id: str, run_id: str, store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    try:
        run = store.get_premium_run(project_id, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail='Higgsfield run not found') from None
    if run['status'] not in ('APPROVED', 'RUNNING', 'SCENES_READY'):
        raise HTTPException(status_code=409, detail='This Higgsfield run is not approved or needs manual review')
    if run['fingerprint'] != premium_run_fingerprint(project, run):
        raise HTTPException(status_code=409, detail='Storyboard or references changed; request a new estimate')
    if not HiggsfieldProvider(Settings()).credential():
        raise HTTPException(status_code=409, detail='Set a new HF_KEY in .env and reload the studio')
    return store.create_job(project_id, 'premium_render', {'run_id': run_id})


@app.post('/api/projects/{project_id}/premium/runs/{run_id}/retry', status_code=202)
def retry_premium(project_id: str, run_id: str, store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    if any(job['kind'] == 'premium_render' and job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
        raise HTTPException(status_code=409, detail='Wait for the active Higgsfield render')
    run = store.get_premium_run(project_id, run_id)
    reviewed_or_409(lambda: store.retry_failed_premium_run(project_id, run_id, premium_run_fingerprint(project, run)))
    return store.create_job(project_id, 'premium_render', {'run_id': run_id})


class PremiumReconcileRequest(BaseModel):
    ordinal: int
    request_id: str


@app.post('/api/projects/{project_id}/premium/runs/{run_id}/reconcile', status_code=202)
async def reconcile_premium(project_id: str, run_id: str, body: PremiumReconcileRequest,
                            store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    try:
        request_id = str(UUID(body.request_id))
    except ValueError:
        raise HTTPException(status_code=422, detail='Enter a valid Higgsfield request ID') from None
    provider = HiggsfieldProvider(Settings())
    try:
        await provider.request_status(request_id)
    except Exception:
        raise HTTPException(status_code=409, detail='That request ID could not be verified with Higgsfield') from None
    run = store.get_premium_run(project_id, run_id)
    reviewed_or_409(lambda: store.reconcile_premium_submission(
        project_id, run_id, body.ordinal, request_id, premium_run_fingerprint(project, run)))
    return store.create_job(project_id, 'premium_render', {'run_id': run_id})


class PremiumNoRequestConfirmation(BaseModel):
    ordinal: int
    confirmed_no_request: bool


@app.post('/api/projects/{project_id}/premium/runs/{run_id}/confirm-no-request')
def confirm_no_premium_request(project_id: str, run_id: str, body: PremiumNoRequestConfirmation,
                               store: Store = Depends(get_store)):
    project = project_or_404(store, project_id)
    if not body.confirmed_no_request:
        raise HTTPException(status_code=422, detail='Check the Higgsfield API console before clearing an uncertain submission')
    run = store.get_premium_run(project_id, run_id)
    return reviewed_or_409(lambda: store.confirm_no_premium_submission(
        project_id, run_id, body.ordinal, premium_run_fingerprint(project, run)))


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str, store: Store = Depends(get_store)):
    try:
        return store.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail='Job not found') from None


FRONTEND_DIST = ROOT / 'frontend/dist'
if FRONTEND_DIST.is_dir():
    app.mount('/', StaticFiles(directory=FRONTEND_DIST, html=True), name='studio')
