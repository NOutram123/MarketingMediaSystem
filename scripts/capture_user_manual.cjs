/* Capture reproducible manual screenshots from an isolated demo server. */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const sharp = require('sharp');

const ROOT = path.resolve(__dirname, '..');
const BASE = process.env.STUDIO_URL || 'http://127.0.0.1:8787';
const API = `${BASE}/api`;
const OUT = path.join(ROOT, 'docs', 'user-manual', 'screenshots');
const ASSETS = path.join(ROOT, 'docs', 'user-manual', 'assets');
const EDGE = process.env.EDGE_PATH || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const TITLE = 'Northstar Flow · City to Summit';

async function api(route, options = {}) {
  const response = await fetch(API + route, options);
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${route}: ${response.status} ${await response.text()}`);
  return response.status === 204 ? null : response.json();
}

async function upload(projectId, filename, role, description) {
  const form = new FormData();
  const data = fs.readFileSync(path.join(ASSETS, filename));
  form.append('file', new Blob([data], { type: 'image/png' }), filename);
  form.append('role', role);
  form.append('description', description);
  return api(`/projects/${projectId}/references`, { method: 'POST', body: form });
}

async function seedDemo() {
  const existing = await api('/projects');
  for (const project of existing.filter((item) => item.title === TITLE)) {
    await api(`/projects/${project.id}`, { method: 'DELETE' });
  }
  const brief = `Audience: Active urban professionals aged 25-45 who move between commuting, work and weekend adventures.
Objective: Introduce Northstar Flow and make the bottle feel like one dependable companion from city to trail.
Key message: Cold all day. Ready anywhere.
Tone and feeling: Capable, calm, optimistic and premium without feeling exclusive.
Must show: The deep-teal bottle, copper cap, city-to-hill progression, tactile details and the approved 24-hour cold claim.
Avoid or exclude: Health promises, carbon-neutral claims, disposable-plastic imagery and extreme-sport clichés.
Deliverable: 30-second 16:9 social and website film ending with the call to action and required disclaimer.`;
  const brand = {
    product_name: 'Northstar Flow',
    description: 'A 750 ml insulated bottle made with recycled stainless steel for commuting and everyday outdoor use.',
    logos: [], colors: ['#123B3A', '#C97943', '#F2EADF'], typography: [],
    approved_wording: [], prohibited_wording: [],
    approved_claims: ['Keeps drinks cold for up to 24 hours', 'Made with recycled stainless steel'],
    prohibited_claims: ['Carbon neutral', '100% sustainable', 'Improves health'],
    required_disclaimers: ['Performance varies with use and conditions.'],
    reference_people: [], voice: 'Calm, clear British English narration',
    visual_style: 'Modern British outdoor editorial, crisp dawn light, teal and copper palette, restrained camera movement',
    cta: 'Choose your route at northstarflow.example', website: 'northstarflow.example'
  };
  let project = await api('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: TITLE, brief, treatment_notes: '', brand, profile_id: 'astra-medium', target_duration_seconds: 30 }) });
  await api(`/projects/${project.id}/approvals/brief`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approve: true, note: 'Example brief approved for the manual.' }) });
  const concept = 'Follow one bottle from a quiet city kitchen through the morning commute and onto an open hilltop. Match-cut circular details and copper highlights create continuity. The film closes on a calm product hero with the route ahead.';
  const script = 'Your day rarely follows one route. From the first train to the last climb, Northstar Flow keeps drinks cold for up to twenty-four hours. Made with recycled stainless steel, it is ready when plans change. Choose your route with Northstar Flow.';
  await api(`/projects/${project.id}/direction`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ concept, script }) });
  await api(`/projects/${project.id}/approvals/concept`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approve: true, note: 'Direction approved.' }) });
  const scenes = [
    { purpose: 'Open with product recognition', visual: 'Dawn kitchen counter. Condensation beads on the teal bottle as a hand lifts it beside keys and a folded map.', camera: 'Slow 50 mm push-in, then a clean match cut on the copper cap.', duration_seconds: 4, narration: 'Your day rarely follows one route.', image_prompt: 'Premium dawn product photograph of a deep-teal insulated bottle with copper cap on a calm modern kitchen counter, tactile condensation, cream and slate palette', video_prompt: 'Slow controlled push-in; hand enters naturally and lifts the bottle; keep label and bottle proportions stable', negative_prompt: 'warped bottle, extra fingers, illegible branding, oversaturated colours' },
    { purpose: 'Move into the city', visual: 'The bottle sits in the side pocket of a commuter bag while the wearer crosses a wet city street at blue hour.', camera: 'Low tracking shot, gentle parallax in reflections.', duration_seconds: 5, narration: 'From the first train', image_prompt: 'Cinematic British city commute at blue hour, wet pavement, deep-teal bottle visible in backpack pocket, copper practical lights', video_prompt: 'Track smoothly beside the walking subject, subtle fabric motion and realistic reflections', negative_prompt: 'traffic danger, distorted bag, changed bottle colour' },
    { purpose: 'Show everyday performance', visual: 'Close detail of the cap opening at a bright studio desk; cold vapour and droplets imply refreshment without making a health claim.', camera: 'Macro detail with a short focus pull from copper cap to bottle body.', duration_seconds: 6, narration: 'to the last climb, Northstar Flow keeps drinks cold for up to twenty-four hours.', image_prompt: 'Macro premium product detail of copper bottle cap and deep-teal textured body at a modern work desk, crisp natural light', video_prompt: 'Short focus pull and restrained cap movement; condensation remains realistic', negative_prompt: 'medical imagery, excessive vapour, deformed cap, false labels' },
    { purpose: 'Connect city and outdoors', visual: 'Match cut to the bottle on a stone ledge above the city as the walker pauses at sunrise.', camera: 'Wide reveal with a slow rise from product foreground to skyline.', duration_seconds: 7, narration: 'Made with recycled stainless steel, it is ready when plans change.', image_prompt: 'Wide sunrise hilltop above a British city, Northstar Flow bottle sharp in foreground, walker resting in background, premium editorial photography', video_prompt: 'Slow rising reveal, light breeze in clothing, bottle stays fixed and consistent', negative_prompt: 'extreme sport, duplicated people, altered bottle markings' },
    { purpose: 'Resolve with brand and action', visual: 'Clean hero bottle against warm cream with a subtle contour-line shadow and room for the end card.', camera: 'Locked hero frame with a faint light sweep.', duration_seconds: 8, narration: 'Choose your route with Northstar Flow.', image_prompt: 'Centered hero packshot of a deep-teal Northstar Flow bottle with copper cap on warm cream, subtle topographic shadow, premium minimal advertising', video_prompt: 'Locked camera, very subtle light sweep across copper cap, no shape change', negative_prompt: 'busy background, extra products, misspelled text, morphing bottle' }
  ];
  await api(`/projects/${project.id}/storyboard`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scenes) });
  const product = await upload(project.id, 'northstar-product.png', 'product', 'Exact bottle shape, deep-teal colour, copper cap, compass mark and contour-line motif.');
  const lifestyle = await upload(project.id, 'northstar-lifestyle.png', 'style', 'City-to-hill dawn mood, natural outdoor styling and teal/copper colour balance.');
  const location = await upload(project.id, 'northstar-location.png', 'location', 'Wet modern city at blue hour with warm copper reflections and a route toward distant hills.');
  project = await api(`/projects/${project.id}`);
  const shot = (ordinal) => project.shots.find((item) => item.ordinal === ordinal);
  const attach = (ordinal, asset, guidance) => api(`/projects/${project.id}/shots/${shot(ordinal).id}/references/${asset.id}?guidance=${encodeURIComponent(guidance)}`, { method: 'PUT' });
  await attach(1, product, 'Keep the exact bottle proportions, teal finish, copper cap and contour motif. Use the kitchen setting from the scene prompt, not the reference background.');
  await attach(2, location, 'Use the blue-hour lighting, wet reflections and route composition; introduce the bottle from the product prompt.');
  await attach(3, product, 'Prioritise cap, surface texture and colour accuracy in the macro detail.');
  await attach(4, lifestyle, 'Use the overall dawn mood and bottle placement. Keep the person secondary; the photographed background may influence the cloud result.');
  await attach(5, product, 'Preserve product identity against the clean cream hero backdrop.');
  await api(`/projects/${project.id}/approvals/storyboard`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approve: true, note: 'Storyboard approved for demonstration.' }) });
  return api(`/projects/${project.id}`);
}

async function captureClipped(page, locator, filename, maxHeight = 1450) {
  await locator.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  const buffer = await locator.screenshot();
  const image = sharp(buffer);
  const metadata = await image.metadata();
  if (!metadata.width || !metadata.height) throw new Error(`Unable to capture ${filename}`);
  const height = Math.min(metadata.height, maxHeight);
  await image.extract({ left: 0, top: 0, width: metadata.width, height }).png().toFile(path.join(OUT, filename));
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const project = await seedDemo();
  const browser = await chromium.launch({ headless: true, executablePath: EDGE, args: ['--disable-gpu', '--hide-scrollbars'] });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 1 });
  await context.route('**/api/setup/status', (route) => route.fulfill({ json: { token: 'manual-demo', completed: true, tested: true, local: { ready: true, checks: [], assets: [], storage: [], models_dir: 'Pinokio/ComfyUI/models', comfyui_url: 'http://127.0.0.1:8188' }, providers: { openai: { configured: false, skipped: true }, higgsfield: { configured: false, skipped: true } }, task: { status: 'IDLE', message: 'Ready', current_bytes: 0, total_bytes: 0 } } }));
  await context.route('**/api/providers', (route) => route.fulfill({ json: [
    { provider: 'comfyui', status: 'AVAILABLE', detail: 'Demo capture' },
    { provider: 'higgsfield', status: 'NOT_CONFIGURED', detail: 'Add in Setup & Diagnostics' },
    { provider: 'openai', status: 'NOT_CONFIGURED', detail: 'Add in Setup & Diagnostics' }
  ] }));
  const page = await context.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('section.create');
  await captureClipped(page, page.locator('section.create'), '01-new-project.png', 1500);
  await page.evaluate((id) => localStorage.setItem('studio-project', id), project.id);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: 'Brief & brand' }).waitFor();
  await page.waitForTimeout(1000);
  const panel = (heading) => page.locator('section.panel').filter({ has: page.getByRole('heading', { name: heading }) }).first();
  await captureClipped(page, panel('Brief & brand'), '02-brief-brand.png', 1250);
  await captureClipped(page, panel('Existing images'), '03-existing-images.png', 1250);
  await captureClipped(page, panel('Concept & script'), '04-concept-script.png', 1250);
  await captureClipped(page, panel('Storyboard'), '05-storyboard.png', 1700);
  await captureClipped(page, panel('Rough cut'), '06-rough-cut.png', 1100);
  await captureClipped(page, panel('Higgsfield video test'), '07-higgsfield.png', 1450);
  await page.screenshot({ path: path.join(OUT, '00-studio-overview.png'), fullPage: true });
  await browser.close();
  console.log(`Captured 8 screenshots for project ${project.id}`);
}

main().catch((error) => { console.error(error); process.exit(1); });
