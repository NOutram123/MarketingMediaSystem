import { useCallback, useEffect, useState } from 'react';
import App from './App';

type Task = { status: string; message: string; current_bytes: number; total_bytes: number };
type Verification = { status: string; detail: string; billing_url: string };
type Provider = { configured: boolean; skipped: boolean; verification?: Verification };
type Status = {
  token: string; completed: boolean; tested: boolean; task: Task;
  providers: Record<string, Provider>;
  local: { ready: boolean; ram_gb: number; models_dir: string; comfyui_url: string;
    checks: { name: string; ok: boolean; detail: string }[];
    assets: { label: string; installed: boolean; bytes: number; path: string }[];
    storage: { volume: string; needed_bytes: number; free_bytes: number; enough: boolean }[] };
};
const API = (location.port === '5173' ? 'http://127.0.0.1:8787' : location.origin) + '/api/setup';
const gb = (bytes: number) => (bytes / 1e9).toFixed(1) + ' GB';

async function read<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Setup request failed.');
  return body;
}

function CredentialPanel({ name, label, provider, disabled, post }: {
  name: string; label: string; provider: Provider; disabled: boolean;
  post: (path: string, body: object) => Promise<void>;
}) {
  const [value, setValue] = useState('');
  const openai = name === 'openai';
  return <section className="panel setup-provider">
    <div className="section-head"><h2>{label}</h2><span className="badge">{provider.configured ? 'Key saved' : provider.skipped ? 'Skipped for now' : 'Not configured'}</span></div>
    <p>{openai ? 'Enables AI planning and claim suggestions. Your ChatGPT subscription does not supply an API key.' : 'Enables paid cloud video evaluation. Website subscription credits are separate from the API balance.'}</p>
    <p><a href={openai ? 'https://platform.openai.com/api-keys' : 'https://cloud.higgsfield.ai/'} target="_blank" rel="noreferrer">Open {label} API console</a></p>
    <form onSubmit={async event => { event.preventDefault(); const submitted = value; setValue(''); await post('/credentials', { provider: name, value: submitted }); }}>
      <label>{openai ? 'OpenAI API key' : 'Complete Higgsfield key-id:key-secret'}
        <input type="password" value={value} autoComplete="off" spellCheck={false} maxLength={1024}
          placeholder={provider.configured ? 'Enter a replacement key (saved key stays hidden)' : 'Paste your API credential here'} onChange={event => setValue(event.target.value)} /></label>
      <div className="setup-actions">
        <button disabled={disabled || !value.trim()} type="submit">Save key</button>
        <button disabled={disabled || !provider.configured} type="button" onClick={() => void post('/verify', { provider: name })}>Check API access</button>
        {!provider.configured && <button disabled={disabled} type="button" onClick={() => void post('/skip', { provider: name })}>Skip for now</button>}
      </div>
    </form>
    {!provider.configured && <p className="warning">{openai ? 'Without this key, AI plan creation and claim suggestions are unavailable. You can still enter your own treatment and scenes.' : 'Without this key, Higgsfield estimates and cloud rendering are unavailable. Local drafts remain available.'}</p>}
    {provider.verification && <p role="status"><strong>{provider.verification.status.replaceAll('_', ' ')}</strong><br />{provider.verification.detail}</p>}
    <p className="setup-muted">Balance: unavailable in setup. <a href={openai ? 'https://platform.openai.com/settings/organization/billing/overview' : 'https://cloud.higgsfield.ai/'} target="_blank" rel="noreferrer">View API billing</a>. Setup never submits a paid generation.</p>
  </section>;
}

export default function SetupGate() {
  const [status, setStatus] = useState<Status | null>(null);
  const [show, setShow] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [modelsDir, setModelsDir] = useState('');
  const [comfyUrl, setComfyUrl] = useState('');
  const refresh = useCallback(async () => {
    const next = await read<Status>('/status');
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    let active = true;
    read<Status>('/status').then(next => {
      if (!active) return;
      setStatus(next); setModelsDir(next.local.models_dir); setComfyUrl(next.local.comfyui_url);
      setShow(!next.completed || !next.local.ready);
    }).catch(err => active && setError(String(err)));
    return () => { active = false; };
  }, []);

  const running = status?.task.status === 'RUNNING';
  useEffect(() => {
    if (!running) return;
    let active = true;
    let timer: number;
    const poll = async () => {
      try {
        const next = await read<Task>('/task');
        if (!active) return;
        setStatus(current => current ? { ...current, task: next } : current);
        if (next.status !== 'RUNNING') { await refresh(); return; }
      } catch (err) { if (active) setError(String(err)); }
      if (active) timer = window.setTimeout(poll, 1500);
    };
    timer = window.setTimeout(poll, 1500);
    return () => { active = false; window.clearTimeout(timer); };
  }, [running, refresh]);

  async function post(path: string, body: object) {
    if (!status) return;
    setBusy(true); setError('');
    try {
      await read(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setup-Token': status.token }, body: JSON.stringify(body) });
      const next = await refresh();
      if (path === '/complete' && next.completed && next.local.ready) setShow(false);
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  }
  async function check() {
    setBusy(true); setError('');
    try { const next = await refresh(); setModelsDir(next.local.models_dir); setComfyUrl(next.local.comfyui_url); }
    catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  }
  async function exportDiagnostics() {
    try {
      const report = await read('/diagnostics');
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = 'studio-setup-diagnostics.json'; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) { setError(String(err)); }
  }
  if (!show) return <><div className="setup-toolbar">{status && Object.entries(status.providers).filter(([, provider]) => !provider.configured).map(([name]) => <span key={name} className="setup-muted">{name === 'openai' ? 'OpenAI planning unavailable' : 'Higgsfield rendering unavailable'} · </span>)}<button onClick={() => { setShow(true); void check(); }}>Setup &amp; Diagnostics</button></div><App /></>;
  const disabled = busy || !!running;
  const canFinish = status?.local.ready && status.tested && Object.values(status.providers).every(provider => provider.configured || provider.skipped);
  return <main className="setup-page">
    <header><div><p className="eyebrow">Marketing Media System · first-run setup</p><h1>Get your studio ready</h1><p>Configure once. Check or repair here whenever you need.</p></div><a className="setup-guide" href={API + '/guide'} target="_blank" rel="noreferrer">Easy Setup PDF ↗</a></header>
    {error && <p className="error" role="alert">{error}</p>}
    {!status ? <section className="panel"><p role="status">Checking the local studio…</p><button onClick={() => void check()}>Retry connection</button></section> : <>
      <section className="panel setup-intro"><h2>1 · Required local foundation</h2>
        <p>Windows 11 and an NVIDIA CUDA GPU are required. We recommend an RTX-class card with at least 8 GB VRAM; that is a provisional recommendation, not a verified minimum. Tested configuration: RTX 5070 Ti, 16 GB VRAM. Detected system RAM: {status.local.ram_gb} GB.</p>
        <p>Pinokio, ComfyUI, FLUX Schnell, LTX 2B, Kokoro, Whisper and FFmpeg are required. This step cannot be skipped. Choose a Pinokio home drive with ample free space before installing ComfyUI. Allow roughly 60 GB for models, runtime installation and initial working space; projects need additional space.</p>
        <ol className="setup-steps"><li><a href="https://pinokio.co/" target="_blank" rel="noreferrer">Download and install Pinokio</a>. Open it, complete initial tool setup, and choose its home folder.</li><li>Use the button below to install or start ComfyUI. Follow progress in Pinokio; if installation finishes without starting ComfyUI, press the button again.</li><li>Download the required models, then restart ComfyUI through Pinokio so it sees the new files.</li></ol>
        <div className="setup-actions"><button disabled={disabled} onClick={() => void post('/action', { action: 'comfy' })}>Install / start ComfyUI</button><button disabled={disabled} onClick={() => void post('/action', { action: 'ffmpeg' })}>Install FFmpeg</button><button disabled={busy} onClick={() => void check()}>Check readiness</button></div>
        <details className="setup-paths"><summary>Existing installation / custom paths</summary><p>Select the actual ComfyUI models folder; changing this field does not move files or reconfigure ComfyUI. To use another drive for a fresh install, choose Pinokio home in Pinokio first.</p>
          <label>ComfyUI models folder<input value={modelsDir} onChange={event => setModelsDir(event.target.value)} /></label>
          <label>ComfyUI local address<input value={comfyUrl} onChange={event => setComfyUrl(event.target.value)} /></label>
          <button disabled={disabled} onClick={() => void post('/paths', { models_dir: modelsDir, comfyui_url: comfyUrl })}>Save local paths</button>
        </details>
      </section>
      <div className="setup-grid"><section className="panel"><h2>2 · Models &amp; readiness</h2><p>Required model files total {gb(status.local.assets.reduce((sum, asset) => sum + asset.bytes, 0))}. Existing files are reused; downloads resume after interruption.</p>
        {status.local.storage.map(volume => <p key={volume.volume} className={volume.enough ? '' : 'warning'}>{volume.volume}: {gb(volume.needed_bytes)} remaining downloads · {gb(volume.free_bytes)} free{volume.enough ? '' : ' — free more space first'}</p>)}
        <p className="setup-muted">Large models go to {status.local.models_dir}. Voice and transcription assets go in the studio’s data/models folder. Outputs retain the existing non-commercial draft policy.</p>
        <div className="setup-actions"><button disabled={disabled || status.local.storage.some(volume => !volume.enough)} onClick={() => void post('/action', { action: 'models' })}>Download / verify required models</button></div>
        <ul className="setup-checks">{status.local.checks.map(item => <li key={item.name}><span className={item.ok ? 'setup-ok' : 'setup-missing'}>{item.ok ? '✓' : '!'}</span><div><strong>{item.name}</strong><small>{item.detail}</small></div></li>)}</ul>
      </section><section className="panel"><h2>3 · Test this computer</h2><p>Checks model integrity, synthesises a short narration, transcribes it, generates a FLUX image and an LTX video, and tests FFmpeg assembly. It uses local compute only and can take several minutes. Finish other studio or ComfyUI jobs first.</p>
        <button disabled={disabled || !status.local.ready} onClick={() => void post('/action', { action: 'test' })}>{status.tested ? 'Run local test again' : 'Run required local test'}</button>
        <p className={status.tested ? 'setup-ok' : 'warning'}>{status.tested ? 'Local generation test passed for this installation.' : 'A successful local generation test is required before opening the studio.'}</p>
        <div className="setup-task" role="status" aria-live="polite"><strong>{status.task.status}</strong><p>{status.task.message}</p>{running && <progress max={status.task.total_bytes || undefined} value={status.task.total_bytes ? status.task.current_bytes : undefined} />}{status.task.total_bytes > 0 && <small>{gb(status.task.current_bytes)} / {gb(status.task.total_bytes)}</small>}</div>
        <p className="setup-muted">Keep the studio running during downloads and testing. After interruption, reopen it and retry the same step. Downloads keep their partial files. A test interrupted after submission may still be running in ComfyUI; let its queue finish before retrying.</p>
      </section></div>
      <h2 className="setup-section-title">4 · API connections</h2><div className="setup-grid">{(['openai', 'higgsfield'] as const).map(name => <CredentialPanel key={name} name={name} label={name === 'openai' ? 'OpenAI' : 'Higgsfield'} provider={status.providers[name]} disabled={disabled} post={post} />)}</div>
      <footer className="panel setup-footer"><div><h2>{canFinish ? 'Ready to open the studio' : 'Complete the required steps above'}</h2><p>API connections can be added later. The local foundation must pass its checks.</p></div><div className="setup-actions"><button disabled={busy} onClick={() => void exportDiagnostics()}>Export diagnostics</button><button className="primary" disabled={disabled || !canFinish} onClick={() => void post('/complete', {})}>Open studio</button></div></footer>
    </>}
  </main>;
}
