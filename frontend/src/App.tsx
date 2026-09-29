import { useEffect, useState, type FormEvent } from 'react';

const API = (location.port === '5173' ? 'http://127.0.0.1:8787' : location.origin) + '/api';
const BRIEF_OUTLINE = `Audience:
Objective:
Key message:
Tone and feeling:
Must show:
Avoid or exclude:`;
const STYLE_PRESETS: Record<string, string> = {
  cinematic: 'Warm cinematic product photography, expressive lighting, restrained camera movement',
  documentary: 'Natural documentary photography, authentic settings, handheld observational camera',
  animation: 'Stylised character animation, clear silhouettes, vivid colour, expressive motion',
  editorial: 'Clean editorial design, graphic compositions, controlled colour palette',
};
type Approval = { status: string; note: string };
type Asset = { id: string; shot_id?: string | null; kind: string; status: string; relative_path: string; classification: string; metadata?: { role?: string; description?: string; original_name?: string; model_id?: string; fingerprint?: string } };
type ShotData = { purpose?: string; visual?: string; camera?: string; duration_seconds?: number; narration?: string; image_prompt?: string; video_prompt?: string; negative_prompt?: string };
type Shot = { id: string; ordinal: number; data: ShotData };
type Project = {
  id: string; title: string; brief: string; treatment_notes: string; target_duration_seconds: number; narration_voice: string; brand: { product_name: string; description?: string; visual_style?: string; approved_claims?: string[]; prohibited_claims?: string[]; required_disclaimers?: string[]; cta?: string };
  plan?: { concept: string; script: string; shots?: ShotData[]; claim_warnings?: string[] };
  approvals: Record<string, Approval>; shots: Shot[]; assets: Asset[];
  shot_references: { shot_id: string; asset_id: string; guidance: string }[];
  jobs: { id: string; kind: string; status: string; error?: string; result?: { candidates?: string[] } }[];
  premium_runs: { id: string; fingerprint: string; status: string; estimated_usd: string; error?: string }[];
};
type PremiumPreview = { model: string; resolution: string; aspect_ratio: string; generate_audio: boolean; fingerprint: string;
  scenes: { ordinal: number; duration_seconds: number; model_path: string; reference_ids: string[] }[]; errors: string[] };
type PremiumRun = { id: string; fingerprint: string; status: string; estimated_usd: string; error?: string;
  scenes: { ordinal: number; status: string; estimated_usd: string; model_path: string; payload: { resolution?: string }; request_id?: string; error?: string }[] };
type Preview = { target_duration_seconds: number; expected_shots: number; inferred_duration_seconds: number; inference_reason: string; prompt_characters: number; warnings: { severity: string; code: string; message: string }[] };
type InputDraft = { brief: string; treatment_notes: string; target_duration_seconds: number; brand: Project['brand'] };
type VoiceOption = { id: string; label: string; language: string };
type VideoModel = { id: string; label: string; installed: boolean; missing_files: string[] };
type Suggestion = { asset_id: string; reason: string };
type Suggestions = Record<string, Suggestion[]>;
type TreatmentExtract = { concept: string; script: string; shots: ShotData[]; warnings: string[] };
type ProviderStatus = { provider: string; status: string; detail: string };

function emptyScene(): ShotData {
  return { purpose: '', visual: '', camera: '', duration_seconds: 5, narration: '', image_prompt: '', video_prompt: '', negative_prompt: '' };
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.status === 204 ? undefined as T : response.json();
}

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestions>({});
  const [treatmentWarnings, setTreatmentWarnings] = useState<string[]>([]);
  const [inputDraft, setInputDraft] = useState<InputDraft | null>(null);
  const [selectedId, setSelectedId] = useState(localStorage.getItem('studio-project') || '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState('');
  const [product, setProduct] = useState('');
  const [brief, setBrief] = useState(BRIEF_OUTLINE);
  const [treatmentNotes, setTreatmentNotes] = useState('');
  const [createDuration, setCreateDuration] = useState('auto');
  const [productDescription, setProductDescription] = useState('');
  const [visualStyle, setVisualStyle] = useState('');
  const [approvedClaims, setApprovedClaims] = useState('');
  const [prohibitedClaims, setProhibitedClaims] = useState('');
  const [requiredDisclaimers, setRequiredDisclaimers] = useState('');
  const [cta, setCta] = useState('');
  const [description, setDescription] = useState('');
  const [role, setRole] = useState('character');
  const [file, setFile] = useState<File | null>(null);
  const [editingReferenceId, setEditingReferenceId] = useState('');
  const [guidance, setGuidance] = useState<Record<string, string>>({});
  const [scriptDraft, setScriptDraft] = useState('');
  const [conceptDraft, setConceptDraft] = useState('');
  const [editingStoryboard, setEditingStoryboard] = useState(false);
  const [scenesDraft, setScenesDraft] = useState<ShotData[]>([]);
  const [editingShotId, setEditingShotId] = useState('');
  const [shotDraft, setShotDraft] = useState<ShotData | null>(null);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [voiceDraft, setVoiceDraft] = useState('af_sarah');
  const [videoModels, setVideoModels] = useState<VideoModel[]>([]);
  const [videoModel, setVideoModel] = useState('ltx-2b');
  const [premiumPreview, setPremiumPreview] = useState<PremiumPreview | null>(null);
  const [premiumRun, setPremiumRun] = useState<PremiumRun | null>(null);
  const [premiumResolution, setPremiumResolution] = useState<'480p' | '720p'>('480p');
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [recoveryRequestId, setRecoveryRequestId] = useState('');
  const [confirmedNoRequest, setConfirmedNoRequest] = useState(false);

  async function refresh(id = selectedId, resolution = premiumResolution) {
    const list = await request<Project[]>('/projects');
    setProjects(list);
    if (id) {
      const [loaded, nextPreview, nextSuggestions, nextPremiumPreview] = await Promise.all([request<Project>(`/projects/${id}`), request<Preview>(`/projects/${id}/plan-preview`), request<Suggestions>(`/projects/${id}/reference-suggestions`), request<PremiumPreview>(`/projects/${id}/premium/preflight?resolution=${resolution}`)]);
      setProject(loaded); setPreview(nextPreview);
      setSuggestions(nextSuggestions);
      setPremiumPreview(nextPremiumPreview);
      setPremiumRun(loaded.premium_runs?.length ? await request<PremiumRun>(`/projects/${id}/premium/runs/${loaded.premium_runs[0].id}`) : null);
    } else {
      setProject(null); setPreview(null); setPremiumPreview(null); setPremiumRun(null);
    }
  }

  useEffect(() => { refresh().catch((err) => setError(String(err))); }, [selectedId, premiumResolution]);
  useEffect(() => { setScriptDraft(project?.plan?.script || ''); }, [project?.id, project?.plan?.script]);
  useEffect(() => { setConceptDraft(project?.plan?.concept || ''); }, [project?.id, project?.plan?.concept]);
  useEffect(() => { setVoiceDraft(project?.narration_voice || 'af_sarah'); }, [project?.id, project?.narration_voice]);
  useEffect(() => { request<VoiceOption[]>('/voices').then(setVoices).catch((err) => setError(String(err))); }, []);
  useEffect(() => { request<ProviderStatus[]>('/providers').then(setProviders).catch((err) => setError(String(err))); }, []);
  useEffect(() => {
    const load = () => request<VideoModel[]>('/local-video-models').then(setVideoModels).catch((err) => setError(String(err)));
    load();
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { setVideoModel(localStorage.getItem(`studio-video-model-${project?.id}`) || 'ltx-2b'); }, [project?.id]);
  useEffect(() => {
    if (!project?.jobs.some((job) => ['QUEUED', 'RUNNING'].includes(job.status))) return;
    const timer = window.setInterval(() => refresh(project.id).catch((err) => setError(String(err))), 2500);
    return () => window.clearInterval(timer);
  }, [project?.id, project?.jobs.map((job) => `${job.id}:${job.status}`).join(',')]);

  function select(id: string) {
    if (id) localStorage.setItem('studio-project', id);
    else localStorage.removeItem('studio-project');
    setSelectedId(id);
    setPremiumResolution('480p');
    if (!id) { setProject(null); setPreview(null); setPremiumPreview(null); setPremiumRun(null); }
    setInputDraft(null);
    setEditingReferenceId(''); setFile(null); setRole('character'); setDescription('');
    setEditingShotId(''); setShotDraft(null);
    setEditingStoryboard(false); setScenesDraft([]);
    setTreatmentWarnings([]);
    setRecoveryRequestId('');
    setConfirmedNoRequest(false);
    setError('');
  }

  function newProject() {
    select('');
  }

  async function act(operation: () => Promise<unknown>) {
    setBusy(true);
    setError('');
    try { await operation(); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  function create(event: FormEvent) {
    event.preventDefault();
    act(async () => {
      const made = await request<Project>('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, brief, treatment_notes: treatmentNotes, brand: {
          product_name: product, description: productDescription, visual_style: visualStyle,
          approved_claims: approvedClaims.split('\n').map((item) => item.trim()).filter(Boolean),
          prohibited_claims: prohibitedClaims.split('\n').map((item) => item.trim()).filter(Boolean),
          required_disclaimers: requiredDisclaimers.split('\n').map((item) => item.trim()).filter(Boolean), cta,
        }, profile_id: 'astra-medium', target_duration_seconds: createDuration === 'auto' ? null : Number(createDuration) }) });
      select(made.id);
    });
  }

  function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project) return;
    if (editingReferenceId) {
      const assetId = editingReferenceId;
      act(async () => {
        await request(`/projects/${project.id}/references/${assetId}`, { method: 'PUT',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role, description }) });
        resetReferenceEditor();
      });
      return;
    }
    if (!file) return;
    const formElement = event.currentTarget;
    const form = new FormData();
    form.append('file', file);
    form.append('role', role);
    form.append('description', description);
    act(async () => {
      await request(`/projects/${project.id}/references`, { method: 'POST', body: form });
      resetReferenceEditor();
      formElement.reset();
    });
  }

  function resetReferenceEditor() {
    setEditingReferenceId(''); setFile(null); setRole('character'); setDescription('');
  }

  function editReference(asset: Asset) {
    setEditingReferenceId(asset.id);
    setFile(null);
    setRole(asset.metadata?.role || 'other');
    setDescription(asset.metadata?.description || '');
    document.getElementById('reference-editor')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function deleteReference() {
    if (!project || !editingReferenceId) return;
    const selected = project.assets.find((asset) => asset.id === editingReferenceId);
    const filename = selected?.metadata?.original_name || 'this image';
    const linkedScenes = project.shot_references.filter((link) => link.asset_id === editingReferenceId).length;
    const consequence = linkedScenes ? ` It will also be removed from ${linkedScenes} scene${linkedScenes === 1 ? '' : 's'} and their approvals will need review.` : '';
    if (!window.confirm(`Delete “${filename}” from this project?${consequence}`)) return;
    const assetId = editingReferenceId;
    act(async () => {
      await request(`/projects/${project.id}/references/${assetId}`, { method: 'DELETE' });
      resetReferenceEditor();
    });
  }

  function saveInput(event: FormEvent) {
    event.preventDefault();
    if (!project || !inputDraft) return;
    act(async () => {
      await request(`/projects/${project.id}/input`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inputDraft) });
      setInputDraft(null);
    });
  }

  function review(gate: string, approve: boolean) {
    if (!project) return;
    act(() => request(`/projects/${project.id}/approvals/${gate}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approve }) }));
  }

  function attach(shotId: string, assetId: string) {
    if (!project || !assetId) return;
    const params = new URLSearchParams({ guidance: guidance[shotId] || '' });
    act(() => request(`/projects/${project.id}/shots/${shotId}/references/${assetId}?${params}`, { method: 'PUT' }));
  }

  function detach(shotId: string, assetId: string) {
    if (!project) return;
    act(() => request(`/projects/${project.id}/shots/${shotId}/references/${assetId}`, { method: 'DELETE' }));
  }

  function saveShot(event: FormEvent, shotId: string) {
    event.preventDefault();
    if (!project || !shotDraft) return;
    act(async () => {
      await request(`/projects/${project.id}/shots/${shotId}`, { method: 'PUT',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(shotDraft) });
      setEditingShotId(''); setShotDraft(null);
    });
  }

  function saveDirection() {
    if (!project) return;
    act(() => request(`/projects/${project.id}/direction`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ concept: conceptDraft.trim(), script: scriptDraft.trim() }) }));
  }

  async function useTreatment(part: 'direction' | 'scenes') {
    if (!project) return;
    setBusy(true); setError('');
    try {
      const extracted = await request<TreatmentExtract>(`/projects/${project.id}/treatment-extract`);
      setTreatmentWarnings(extracted.warnings);
      if (part === 'direction') {
        if (!extracted.concept || extracted.script.length < 20) throw new Error('No complete concept and voiceover found in the treatment; enter them manually.');
        setConceptDraft(extracted.concept); setScriptDraft(extracted.script);
      } else {
        if (!extracted.shots.length) throw new Error('No timed scenes found in the treatment; create them manually.');
        setScenesDraft(extracted.shots); setEditingStoryboard(true);
      }
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  function saveStoryboard(event: FormEvent) {
    event.preventDefault();
    if (!project) return;
    act(async () => {
      await request(`/projects/${project.id}/storyboard`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scenesDraft) });
      setEditingStoryboard(false);
    });
  }

  function deleteProject() {
    if (!project || !window.confirm(`Delete “${project.title}” and all its project files? This cannot be undone.`)) return;
    const id = project.id;
    setBusy(true); setError('');
    request(`/projects/${id}`, { method: 'DELETE' }).then(async () => { select(''); await refresh(''); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false));
  }

  const references = project?.assets.filter((asset) => asset.kind === 'reference_image') || [];
  const editingReference = references.find((asset) => asset.id === editingReferenceId);
  const roughCut = [...(project?.assets || [])].reverse().find((asset) => asset.kind === 'rough_cut' && asset.status === 'CREATED');
  const premiumEvaluation = [...(project?.assets || [])].reverse().find((asset) => asset.kind === 'premium_evaluation' && asset.status === 'CREATED' && asset.metadata?.fingerprint === premiumPreview?.fingerprint);
  const renderedModel = [...(project?.assets || [])].reverse().find((asset) => asset.kind === 'draft_clip' && asset.status === 'CREATED')?.metadata?.model_id || 'ltx-2b';
  const selectedVideoModel = videoModels.find((model) => model.id === videoModel);
  const higgsfieldConfigured = providers.some((provider) => provider.provider === 'higgsfield' && provider.status === 'CONFIGURED_UNVERIFIED');
  const uncertainPremiumScene = premiumRun?.scenes.find((scene) => scene.status === 'SUBMITTING' && !scene.request_id);
  const quotedResolution = premiumRun?.scenes[0]?.payload?.resolution || '720p';
  const quoteMatchesSelection = !!premiumRun && premiumRun.fingerprint === premiumPreview?.fingerprint && quotedResolution === premiumResolution;
  const captions = [...(project?.assets || [])].reverse().find((asset) => asset.kind === 'captions_vtt' && asset.status === 'CREATED');
  const claimJob = [...(project?.jobs || [])].reverse().find((job) => job.kind === 'openai_claim_suggestions' && job.status === 'SUCCEEDED');

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="mark">◆</span><div><strong>Media Studio</strong><small>LOCAL PREVIS</small></div></div>
      <p className="eyebrow">Projects</p>
      <button className="new-project" onClick={newProject}>+ New project</button>
      <div className="project-list">{projects.map((item) => <button key={item.id} className={selectedId === item.id ? 'selected' : ''} onClick={() => select(item.id)}>{item.title}</button>)}</div>
      <p className="sidebar-note">Local AI drafts are for review only and may not be used commercially.</p>
    </aside>
    <main>
      <header><div><p className="eyebrow">Hybrid AI Media Studio</p><h1>{project ? project.title : 'Build a campaign'}</h1></div><span className="badge">AI-generated draft · non-commercial</span></header>
      {error && <div className="error" role="alert">{error}</div>}
      {!project ? <section className="panel create"><h2>New project</h2><p>Use the brief to define the assignment. Put any existing concept, script or timed storyboard in the separate treatment notes so it remains available for editing.</p>
        <form onSubmit={create}>
          <label>Project title<input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={2}/></label>
          <label>Product name<input value={product} onChange={(event) => setProduct(event.target.value)} required/></label>
          <label>Product description<textarea value={productDescription} onChange={(event) => setProductDescription(event.target.value)} rows={2}/></label>
          <label>Creative brief · editable outline<textarea value={brief} onChange={(event) => setBrief(event.target.value)} minLength={10} required rows={8}/></label>
          <label>Existing treatment · optional<textarea value={treatmentNotes} onChange={(event) => setTreatmentNotes(event.target.value)} rows={6} placeholder="Paste any existing concept, script, storyboard or scene timings here. You can later edit the concept and scenes separately."/></label>
          <label>Film length<select value={createDuration} onChange={(event) => setCreateDuration(event.target.value)}><option value="auto">Detect from brief (defaults to 15s)</option>{[15, 30, 45, 60].map((seconds) => <option key={seconds} value={seconds}>{seconds} seconds</option>)}</select></label>
          <label>Visual style preset<select value={Object.keys(STYLE_PRESETS).find((key) => STYLE_PRESETS[key] === visualStyle) || ''} onChange={(event) => setVisualStyle(STYLE_PRESETS[event.target.value] || '')}><option value="">Custom / none</option>{Object.keys(STYLE_PRESETS).map((key) => <option key={key} value={key}>{key[0].toUpperCase() + key.slice(1)}</option>)}</select></label>
          <label>Visual style · editable<input value={visualStyle} onChange={(event) => setVisualStyle(event.target.value)} placeholder="e.g. Warm cinematic product photography"/></label>
          <label>Approved claims · one per line<textarea value={approvedClaims} onChange={(event) => setApprovedClaims(event.target.value)} rows={2} placeholder="Only wording you have checked and approved"/></label>
          <label>Prohibited claims · one per line<textarea value={prohibitedClaims} onChange={(event) => setProhibitedClaims(event.target.value)} rows={2} placeholder="Statements or promises the advert must avoid"/></label>
          <label>Required disclaimers · one per line<textarea value={requiredDisclaimers} onChange={(event) => setRequiredDisclaimers(event.target.value)} rows={2}/></label>
          <label>Call to action<input value={cta} onChange={(event) => setCta(event.target.value)} placeholder="e.g. Discover the ingredients at our website"/></label>
          <small>The call to action is what you want viewers to do at the end. Leave it blank if the film should only inform.</small>
          <button className="primary" disabled={busy}>Create project</button>
        </form></section> : <div className="content">
          <section className="panel"><div className="section-head"><div><p className="eyebrow">01 / Input</p><h2>Brief & brand</h2></div><span className="status">{project.approvals.brief.status}</span></div>
            <p><strong>Project target:</strong> {project.target_duration_seconds}-second film · variable-length scenes</p>
            <p className="brief">{project.brief}</p><p><strong>Product:</strong> {project.brand.product_name}</p>
            {project.treatment_notes && <details><summary>Existing treatment notes</summary><p className="brief">{project.treatment_notes}</p></details>}
            {project.brand.description && <p>{project.brand.description}</p>}
            {project.brand.visual_style && <p><strong>Visual style:</strong> {project.brand.visual_style}</p>}
            {!!project.brand.approved_claims?.length && <p><strong>Approved claims:</strong> {project.brand.approved_claims.join('; ')}</p>}
            <p>Claim suggestions are unverified candidates. Check evidence and permitted wording before adding any to the approved list.</p>
            <button disabled={busy || project.jobs.some((job) => job.kind === 'openai_claim_suggestions' && ['QUEUED', 'RUNNING'].includes(job.status))}
              onClick={() => act(() => request(`/projects/${project.id}/claim-suggestions`, { method: 'POST' }))}>Suggest claim candidates · paid API</button>
            {!!claimJob?.result?.candidates?.length && <div className="suggestions"><small>Candidate claims to review:</small>{claimJob.result.candidates.map((candidate, index) => <button key={`${index}-${candidate}`} disabled={busy} onClick={() => setInputDraft((current) => {
              const draft = current || { brief: project.brief, treatment_notes: project.treatment_notes || '', brand: project.brand, target_duration_seconds: project.target_duration_seconds };
              return { ...draft, brand: { ...draft.brand, approved_claims: [...new Set([...(draft.brand.approved_claims || []), candidate])] } };
            })}>{candidate} · review in editor</button>)}</div>}
            {!!project.brand.prohibited_claims?.length && <p><strong>Prohibited claims:</strong> {project.brand.prohibited_claims.join('; ')}</p>}
            {!!project.brand.required_disclaimers?.length && <p><strong>Disclaimers:</strong> {project.brand.required_disclaimers.join('; ')}</p>}
            {project.brand.cta && <p><strong>Call to action:</strong> {project.brand.cta}</p>}
            {!inputDraft && <button disabled={busy} onClick={() => setInputDraft({ brief: project.brief, treatment_notes: project.treatment_notes || '', brand: project.brand, target_duration_seconds: project.target_duration_seconds })}>Edit brief, treatment & length</button>}
            {inputDraft && <form onSubmit={saveInput}>
              <label>Target length<select value={inputDraft.target_duration_seconds} onChange={(event) => setInputDraft({ ...inputDraft, target_duration_seconds: Number(event.target.value) })}>{[15, 30, 45, 60].map((seconds) => <option key={seconds} value={seconds}>{seconds} seconds</option>)}</select></label>
              <label>Creative brief<textarea rows={10} required minLength={10} value={inputDraft.brief} onChange={(event) => setInputDraft({ ...inputDraft, brief: event.target.value })}/></label>
              <label>Existing treatment notes<textarea rows={8} value={inputDraft.treatment_notes} onChange={(event) => setInputDraft({ ...inputDraft, treatment_notes: event.target.value })}/></label>
              <label>Product description<textarea rows={3} value={inputDraft.brand.description || ''} onChange={(event) => setInputDraft({ ...inputDraft, brand: { ...inputDraft.brand, description: event.target.value } })}/></label>
              <label>Visual style<input value={inputDraft.brand.visual_style || ''} onChange={(event) => setInputDraft({ ...inputDraft, brand: { ...inputDraft.brand, visual_style: event.target.value } })}/></label>
              <label>Approved claims · one per line<textarea rows={5} value={(inputDraft.brand.approved_claims || []).join('\n')} onChange={(event) => setInputDraft({ ...inputDraft, brand: { ...inputDraft.brand, approved_claims: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean) } })}/></label>
              <label>Prohibited claims · one per line<textarea rows={4} value={(inputDraft.brand.prohibited_claims || []).join('\n')} onChange={(event) => setInputDraft({ ...inputDraft, brand: { ...inputDraft.brand, prohibited_claims: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean) } })}/></label>
              <label>Required disclaimers · one per line<textarea rows={4} value={(inputDraft.brand.required_disclaimers || []).join('\n')} onChange={(event) => setInputDraft({ ...inputDraft, brand: { ...inputDraft.brand, required_disclaimers: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean) } })}/></label>
              <label>Call to action<input value={inputDraft.brand.cta || ''} onChange={(event) => setInputDraft({ ...inputDraft, brand: { ...inputDraft.brand, cta: event.target.value } })}/></label>
              <div><button className="primary" disabled={busy}>Save input</button><button type="button" onClick={() => setInputDraft(null)}>Cancel</button></div>
              <p>Saving changes resets approvals and the current plan. Uploaded reference images remain available.</p>
            </form>}
            {project.approvals.brief.status !== 'APPROVED' && <button disabled={busy} onClick={() => review('brief', true)}>Approve brief</button>}
            <button className="danger" disabled={busy} onClick={deleteProject}>Delete project…</button>
          </section>
          <section className="panel"><div className="section-head"><div><p className="eyebrow">02 / Sources</p><h2>Existing images</h2></div><span className="status">{references.length} saved</span></div>
            <p>Upload character, product, style or location references. In each scene you choose which ones apply. For local drafts, their descriptions and your guidance inform the image and motion prompts; the whole uploaded photo is not used as the first frame. Local models may still vary the appearance between scenes.</p>
            <form className="upload-form" id="reference-editor" onSubmit={upload}>
              <label>Image{editingReference
                ? <output className="reference-file">{editingReference.metadata?.original_name || editingReference.relative_path.split('/').pop()}</output>
                : <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setFile(event.target.files?.[0] || null)} required/>}</label>
              <label>Role<select value={role} onChange={(event) => setRole(event.target.value)}><option>character</option><option>product</option><option>style</option><option>location</option><option>other</option></select></label>
              <label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="e.g. Purple owl mascot, round glasses" maxLength={2000}/></label>
              <div className="reference-actions"><button className="primary" disabled={busy || (!editingReferenceId && !file)}>{editingReferenceId ? 'Update' : 'Add image'}</button>
                {editingReferenceId && <><button type="button" disabled={busy} onClick={resetReferenceEditor}>Cancel</button><button className="danger" type="button" disabled={busy} onClick={deleteReference}>Delete image…</button></>}</div>
            </form>
            <div className="asset-grid">{references.map((asset) => <button type="button" className={`asset-card reference-card${editingReferenceId === asset.id ? ' selected' : ''}`} aria-pressed={editingReferenceId === asset.id} disabled={busy} key={asset.id} onClick={() => editReference(asset)}>
              <img src={`${API}/projects/${project.id}/assets/${asset.id}/file`} alt={asset.metadata?.description || asset.metadata?.original_name || 'Uploaded reference'}/>
              <div><strong>{asset.metadata?.role}</strong><small className="reference-name">{asset.metadata?.original_name || asset.relative_path.split('/').pop()}</small><small>{asset.metadata?.description}</small></div>
            </button>)}</div>
          </section>
          <section className="panel" id="direction-panel"><div className="section-head"><div><p className="eyebrow">03 / Direction</p><h2>Concept & script</h2></div><span className="status">{project.approvals.concept.status}</span></div>
            {project.approvals.brief.status === 'APPROVED' && <><p>Enter an existing treatment here, or generate a first version with the paid planning request. Approve when the direction is ready to become a storyboard.</p>
              {!!project.treatment_notes && project.approvals.concept.status !== 'APPROVED' && <button disabled={busy} onClick={() => useTreatment('direction')}>Extract concept & voiceover from treatment · free</button>}
              {!!treatmentWarnings.length && <div className="warning">Review extraction: {treatmentWarnings.join('; ')}</div>}
              <label>Concept<textarea value={conceptDraft} onChange={(event) => setConceptDraft(event.target.value)} rows={4} disabled={project.approvals.concept.status === 'APPROVED'} placeholder="What happens in the film and why?"/></label>
              <label>Continuous voiceover script · roughly {Math.round(project.target_duration_seconds * 2.4)} words<textarea value={scriptDraft} onChange={(event) => setScriptDraft(event.target.value)} rows={6} disabled={project.approvals.concept.status === 'APPROVED'} placeholder="One continuous narration across all scenes"/></label>
              <small>{scriptDraft.trim() ? scriptDraft.trim().split(/\s+/).length : 0} words</small>
              {project.approvals.concept.status === 'APPROVED'
                ? <button disabled={busy} onClick={() => review('concept', false)}>Request changes to concept & script</button>
                : <><button disabled={busy || conceptDraft.trim().length < 3 || scriptDraft.trim().length < 20 || (conceptDraft.trim() === project.plan?.concept && scriptDraft.trim() === project.plan?.script)} onClick={saveDirection}>Save concept & script</button>
                  {project.plan && <button disabled={busy || conceptDraft.trim() !== project.plan.concept || scriptDraft.trim() !== project.plan.script} onClick={() => review('concept', true)}>Approve concept & script</button>}</>}
              {!!project.plan?.claim_warnings?.length && <div className="warning">Review claims: {project.plan.claim_warnings.join('; ')}</div>}</>}
            {preview && <div className="warning"><strong>Planning preview:</strong> {preview.target_duration_seconds}s · {preview.expected_shots} shots · {preview.prompt_characters.toLocaleString()} input characters. {preview.inference_reason}
              {preview.warnings.map((warning) => <p key={warning.code}><strong>{warning.severity}:</strong> {warning.message}</p>)}</div>}
            {project.approvals.brief.status === 'APPROVED' && <button disabled={busy || !!inputDraft || preview?.warnings.some((warning) => warning.severity === 'blocker') || project.jobs.some((job) => job.kind === 'openai_plan' && ['QUEUED', 'RUNNING'].includes(job.status))}
              onClick={() => act(() => request(`/projects/${project.id}/plan`, { method: 'POST' }))}>{project.plan ? 'Regenerate direction & scenes · paid API' : `Generate direction & scenes · paid API`}</button>}
          </section>
          <section className="panel"><div className="section-head"><div><p className="eyebrow">04 / Sequence</p><h2>Storyboard</h2></div><span className="status">{project.approvals.storyboard.status}</span></div>
            {project.approvals.concept.status === 'APPROVED' && <button disabled={busy} onClick={() => { review('concept', false); document.getElementById('direction-panel')?.scrollIntoView({ behavior: 'smooth' }); }}>Request changes to concept & script</button>}
            {project.approvals.concept.status === 'APPROVED' && !project.shots.length && !!project.plan?.shots?.length && <button disabled={busy} onClick={() => act(() => request(`/projects/${project.id}/storyboard`, { method: 'POST' }))}>Create storyboard from plan</button>}
            {project.approvals.concept.status === 'APPROVED' && !!project.treatment_notes && <button disabled={busy} onClick={() => useTreatment('scenes')}>Extract timed scenes from treatment · free</button>}
            {project.approvals.concept.status === 'APPROVED' && !editingStoryboard && <button disabled={busy} onClick={() => { setScenesDraft(project.shots.length ? project.shots.map((shot) => ({ ...shot.data })) : [emptyScene()]); setEditingStoryboard(true); }}> {project.shots.length ? 'Revise scene sequence' : 'Create scenes manually'}</button>}
            {editingStoryboard && <form className="scene-sequence" onSubmit={saveStoryboard}><p>Set variable scene lengths; together they must total {project.target_duration_seconds} seconds. Saving a revised sequence replaces scene links and generated drafts.</p>
              {scenesDraft.map((scene, index) => <fieldset key={index}><legend>Scene {index + 1}</legend>
                <label>Duration (seconds)<input type="number" min={2} max={30} step={0.5} value={scene.duration_seconds || 0} onChange={(event) => setScenesDraft(scenesDraft.map((item, at) => at === index ? { ...item, duration_seconds: Number(event.target.value) } : item))}/></label>
                {(['purpose', 'visual', 'camera', 'narration', 'image_prompt', 'video_prompt'] as const).map((field) => <label key={field}>{field.replace('_', ' ')}<textarea rows={field === 'visual' || field.includes('prompt') ? 3 : 2} required={field !== 'narration'} value={scene[field] || ''} onChange={(event) => setScenesDraft(scenesDraft.map((item, at) => at === index ? { ...item, [field]: event.target.value } : item))}/></label>)}
                <button type="button" disabled={scenesDraft.length <= 1} onClick={() => setScenesDraft(scenesDraft.filter((_, at) => at !== index))}>Remove scene</button>
              </fieldset>)}
              <p><strong>Total:</strong> {scenesDraft.reduce((sum, scene) => sum + Number(scene.duration_seconds || 0), 0)} / {project.target_duration_seconds} seconds</p>
              <button type="button" disabled={scenesDraft.length >= 20} onClick={() => setScenesDraft([...scenesDraft, emptyScene()])}>Add scene</button>
              <button className="primary" disabled={busy || Math.abs(scenesDraft.reduce((sum, scene) => sum + Number(scene.duration_seconds || 0), 0) - project.target_duration_seconds) > 0.05}>Save scene sequence</button>
              <button type="button" onClick={() => setEditingStoryboard(false)}>Cancel</button>
            </form>}
            <div className="shots">{project.shots.map((shot) => {
              const suggested = (suggestions[shot.id] || []).filter((item) => !project.shot_references.some((link) => link.shot_id === shot.id && link.asset_id === item.asset_id));
              return <article className="shot" key={shot.id}><div className="shot-number">{String(shot.ordinal).padStart(2, '0')}</div>
              <div><h3>{shot.data.purpose || 'Untitled shot'}</h3><p>{shot.data.visual}</p><small>{shot.data.duration_seconds || 3}s · {shot.data.narration}</small>
                {editingShotId === shot.id && shotDraft ? <form className="shot-editor" onSubmit={(event) => saveShot(event, shot.id)}>
                  <label>Purpose<input required value={shotDraft.purpose || ''} onChange={(event) => setShotDraft({ ...shotDraft, purpose: event.target.value })}/></label>
                  <label>Duration (seconds)<input required type="number" min={2} max={30} step={0.5} value={shotDraft.duration_seconds || 3} onChange={(event) => setShotDraft({ ...shotDraft, duration_seconds: Number(event.target.value) })}/></label>
                  <label>Visual description<textarea required rows={4} value={shotDraft.visual || ''} onChange={(event) => setShotDraft({ ...shotDraft, visual: event.target.value })}/></label>
                  <label>Camera direction<textarea required rows={2} value={shotDraft.camera || ''} onChange={(event) => setShotDraft({ ...shotDraft, camera: event.target.value })}/></label>
                  <label>Narration timing cue<textarea rows={2} value={shotDraft.narration || ''} onChange={(event) => setShotDraft({ ...shotDraft, narration: event.target.value })}/></label>
                  <label>Storyboard image prompt<textarea required rows={3} value={shotDraft.image_prompt || ''} onChange={(event) => setShotDraft({ ...shotDraft, image_prompt: event.target.value })}/></label>
                  <label>Video motion prompt<textarea required rows={3} value={shotDraft.video_prompt || ''} onChange={(event) => setShotDraft({ ...shotDraft, video_prompt: event.target.value })}/></label>
                  <label>Negative prompt<textarea rows={2} value={shotDraft.negative_prompt || ''} onChange={(event) => setShotDraft({ ...shotDraft, negative_prompt: event.target.value })}/></label>
                  <div><button className="primary" disabled={busy}>Save shot</button><button type="button" onClick={() => { setEditingShotId(''); setShotDraft(null); }}>Cancel</button></div>
                </form> : <><details><summary>Camera and generation directions</summary><p><strong>Camera:</strong> {shot.data.camera}</p><p><strong>Image:</strong> {shot.data.image_prompt}</p><p><strong>Motion:</strong> {shot.data.video_prompt}</p></details>
                  <button disabled={busy} onClick={() => { setEditingShotId(shot.id); setShotDraft({ ...shot.data }); }}>Edit scene</button></>}
                {!!suggested.length && <div className="suggestions"><small>Suggested references · select to use:</small>{suggested.map((item) => {
                  const asset = references.find((candidate) => candidate.id === item.asset_id);
                  return <button key={item.asset_id} disabled={busy} title={item.reason} onClick={() => attach(shot.id, item.asset_id)}>{asset?.metadata?.role}: {asset?.metadata?.description || asset?.metadata?.original_name}</button>;
                })}</div>}
                {!!references.length && <div className="attach"><select id={`ref-${shot.id}`} defaultValue=""><option value="">Choose a reference…</option>{references.map((asset) => <option key={asset.id} value={asset.id}>{asset.metadata?.role}: {asset.metadata?.description || asset.metadata?.original_name}</option>)}</select>
                  <input value={guidance[shot.id] || ''} onChange={(event) => setGuidance({ ...guidance, [shot.id]: event.target.value })} placeholder="e.g. Keep PolyPhenol's face and outfit consistent"/>
                  <button disabled={busy} onClick={() => attach(shot.id, (document.getElementById(`ref-${shot.id}`) as HTMLSelectElement).value)}>Use in scene</button></div>}
                <div className="linked">{project.shot_references.filter((link) => link.shot_id === shot.id).map((link) => {
                  const asset = references.find((item) => item.id === link.asset_id);
                  return <span key={link.asset_id}>{asset?.metadata?.role || 'reference'} · {link.guidance || asset?.metadata?.description} <button className="unlink" disabled={busy} onClick={() => detach(shot.id, link.asset_id)} aria-label="Remove reference">×</button></span>;
                })}</div>
              </div></article>})}</div>
            {!!project.shots.length && <p><strong>Scene total:</strong> {project.shots.reduce((sum, shot) => sum + Number(shot.data.duration_seconds || 3), 0)} / {project.target_duration_seconds} seconds</p>}
            {project.shots.some((shot) => Number(shot.data.duration_seconds || 3) > 5) && <p>Local preview motion is time-stretched for scenes longer than about five seconds. The scene timing and continuous narration remain as planned.</p>}
            {!!project.shots.length && project.approvals.storyboard.status !== 'APPROVED' && <button disabled={busy || project.approvals.concept.status !== 'APPROVED' || Math.abs(project.shots.reduce((sum, shot) => sum + Number(shot.data.duration_seconds || 3), 0) - project.target_duration_seconds) > 0.05} onClick={() => review('storyboard', true)}>Approve storyboard</button>}
          </section>
          <section className="panel"><div className="section-head"><div><p className="eyebrow">05a / Local review</p><h2>Rough cut</h2></div><span className="status">{project.approvals.rough_cut.status}</span></div>
            <label>Local video model<select value={videoModel} onChange={(event) => {
              setVideoModel(event.target.value);
              localStorage.setItem(`studio-video-model-${project.id}`, event.target.value);
            }}>
              {videoModels.map((model) => <option key={model.id} value={model.id}>{model.label}{model.installed ? '' : ' · downloading or missing'}</option>)}
            </select></label>
            <p>{selectedVideoModel?.installed ? 'Ready for local rendering.' : 'This model is not ready yet. Its weights are downloading or missing.'} LTX 13B may exceed this GPU’s memory; Wan and LTX 13B still need a live benchmark here.</p>
            <label>Narration voice<select value={voiceDraft} onChange={(event) => setVoiceDraft(event.target.value)}>
              {voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}
            </select></label>
            <button disabled={busy || !voices.length || voiceDraft === project.narration_voice || project.jobs.some((job) => job.kind === 'local_draft' && ['QUEUED', 'RUNNING'].includes(job.status))}
              onClick={() => act(() => request(`/projects/${project.id}/voice`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice_id: voiceDraft }) }))}>Save voice</button>
            <p>Changing voice keeps the video clips. Generate the local draft again to create new narration, captions and a rough cut.</p>
            {project.approvals.storyboard.status === 'APPROVED' && (!roughCut || renderedModel !== videoModel) && <button disabled={busy || !selectedVideoModel?.installed || project.jobs.some((job) => job.kind === 'local_draft' && ['QUEUED', 'RUNNING'].includes(job.status))}
              onClick={() => act(() => request(`/projects/${project.id}/local-draft`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ video_model: videoModel }) }))}>{roughCut ? 'Render with selected model' : 'Generate local draft'}</button>}
            {roughCut ? <video className="player" controls src={`${API}/projects/${project.id}/assets/${roughCut.id}/file`}>
              {captions && <track kind="subtitles" src={`${API}/projects/${project.id}/assets/${captions.id}/file`} srcLang="en" label="English" default/>}
            </video> : <p>The local draft will appear here when generated.</p>}
            {roughCut && project.approvals.rough_cut.status !== 'APPROVED' && <button disabled={busy} onClick={() => review('rough_cut', true)}>Approve rough cut</button>}
          </section>
          <section className="panel"><div className="section-head"><div><p className="eyebrow">05b / Cloud evaluation</p><h2>Higgsfield video test</h2></div><span className="status">{premiumRun?.status || 'NOT STARTED'}</span></div>
            <p><strong>Model:</strong> Seedance 2.5 via Higgsfield API · 16:9. Each storyboard scene becomes one cloud video clip. Selected uploaded images are sent as visual references for that scene; scenes without images use Seedance text-to-video. The clips are assembled with one continuous local draft narration and captions.</p>
            <label>Cloud video resolution
              <select value={premiumResolution} onChange={(event) => setPremiumResolution(event.target.value as '480p' | '720p')} disabled={busy}>
                <option value="480p">480p · lower cost</option>
                <option value="720p">720p · higher detail and cost</option>
              </select>
            </label>
            <p>Getting an estimate uploads the selected reference images to Higgsfield, but does not submit a paid generation. Higgsfield currently provides an approximate per-second rate for the selected resolution; the studio totals that rate across the scenes before any account discount. Your approval is required before rendering.</p>
            {!higgsfieldConfigured && <p className="warning">Higgsfield API key is not configured. Open Setup &amp; Diagnostics to save your complete key-id:key-secret credential. Website plan credits are separate from the API balance.</p>}
            <p>This is an AI-generated, non-commercial evaluation. A reference image includes its photographed background; the model may reproduce it despite scene direction, and character consistency is not guaranteed.</p>
            {premiumPreview && <><p><strong>Prepared scenes:</strong> {premiumPreview.scenes.length} · {premiumPreview.scenes.reduce((sum, scene) => sum + scene.duration_seconds, 0)}s</p>
              {premiumPreview.scenes.map((scene) => <p className="job" key={scene.ordinal}><strong>Scene {scene.ordinal} · {scene.duration_seconds}s</strong><span>{scene.reference_ids.length ? `${scene.reference_ids.length} image reference${scene.reference_ids.length === 1 ? '' : 's'}` : 'Prompt only'}</span></p>)}
              {premiumPreview.errors.map((problem, index) => <p className="warning" key={index}>{problem}</p>)}
            </>}
            <button disabled={busy || !higgsfieldConfigured || !!uncertainPremiumScene || !premiumPreview || premiumPreview.resolution !== premiumResolution || !!premiumPreview.errors.length || project.jobs.some((job) => job.kind === 'premium_render' && ['QUEUED', 'RUNNING'].includes(job.status))}
              onClick={() => act(() => request(`/projects/${project.id}/premium/estimate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resolution: premiumResolution }) }))}>Get {premiumResolution} Higgsfield estimate · no generation</button>
            {premiumRun && <><p><strong>Latest {quotedResolution} estimate:</strong> about ${premiumRun.estimated_usd} USD before discounts for {premiumRun.scenes.length} scene{premiumRun.scenes.length === 1 ? '' : 's'}. Higgsfield says actual charges can vary with output dimensions and billable duration; this estimate is not a spending cap. The app stops if the published estimate rises before submission.</p>
              {premiumRun.scenes.map((scene) => <p className="job" key={scene.ordinal}><strong>Scene {scene.ordinal} · ${scene.estimated_usd}</strong><span>{scene.status}</span>{scene.error && <small>{scene.error}</small>}</p>)}
              {!quoteMatchesSelection && <p className="warning">This quote is for {quotedResolution} or an earlier storyboard. Select {quotedResolution} to review it, or request a fresh {premiumResolution} estimate before approving or rendering.</p>}
              {premiumRun.status === 'QUOTED' && quoteMatchesSelection && <button disabled={busy} onClick={() => act(() => request(`/projects/${project.id}/premium/runs/${premiumRun.id}/approve`, { method: 'POST' }))}>Approve approximate ${premiumRun.estimated_usd} estimate for this film</button>}
              {['APPROVED', 'RUNNING', 'SCENES_READY'].includes(premiumRun.status) && quoteMatchesSelection && !project.jobs.some((job) => job.kind === 'premium_render' && ['QUEUED', 'RUNNING'].includes(job.status)) && <button disabled={busy} onClick={() => act(() => request(`/projects/${project.id}/premium/runs/${premiumRun.id}/render`, { method: 'POST' }))}>{premiumRun.status === 'APPROVED' ? 'Generate evaluation · paid API' : 'Resume Higgsfield render'}</button>}
              {premiumRun.status === 'FAILED' && quoteMatchesSelection && <button disabled={busy} onClick={() => act(() => request(`/projects/${project.id}/premium/runs/${premiumRun.id}/retry`, { method: 'POST' }))}>Retry failed scene · paid API</button>}
              {uncertainPremiumScene && <div className="warning"><p>A submission was interrupted before its request ID was saved. Check the Higgsfield API console for scene {uncertainPremiumScene.ordinal}; enter its request ID to resume polling without submitting it again.</p>
                <label>Higgsfield request ID<input value={recoveryRequestId} onChange={(event) => setRecoveryRequestId(event.target.value)} placeholder="Request ID from API console"/></label>
                <button disabled={busy || !recoveryRequestId.trim()} onClick={() => act(() => request(`/projects/${project.id}/premium/runs/${premiumRun.id}/reconcile`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ordinal: uncertainPremiumScene.ordinal, request_id: recoveryRequestId.trim() }) }))}>Recover and resume request</button>
                <label><input type="checkbox" checked={confirmedNoRequest} onChange={(event) => setConfirmedNoRequest(event.target.checked)}/> I checked the Higgsfield API console and no request exists for this scene.</label>
                <button disabled={busy || !confirmedNoRequest} onClick={() => act(() => request(`/projects/${project.id}/premium/runs/${premiumRun.id}/confirm-no-request`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ordinal: uncertainPremiumScene.ordinal, confirmed_no_request: true }) }))}>Mark scene not submitted</button>
              </div>}
              {premiumRun.error && <p className="warning">{premiumRun.error}</p>}
            </>}
            {premiumEvaluation && <video className="player" controls src={`${API}/projects/${project.id}/assets/${premiumEvaluation.id}/file`} />}
            {premiumEvaluation && <p>Download from the video player for non-commercial review. This draft combines Higgsfield scenes with the local narration; it is not a commercial final.</p>}
          </section>
          {!!project.jobs.length && <section className="panel"><p className="eyebrow">Activity</p><h2>Jobs</h2>{project.jobs.map((job) => <p key={job.id} className="job"><strong>{job.kind}</strong><span>{job.status}</span>{job.error && <small>{job.error}</small>}</p>)}</section>}
        </div>}
    </main>
  </div>;
}

export default App;
