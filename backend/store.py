"""SQLite project state and immutable asset lineage for the local studio."""
import json
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


GATES = ('brief', 'concept', 'storyboard', 'rough_cut', 'premium_spend', 'final')
PROJECT_FOLDERS = (
    'brief', 'brand', 'scripts', 'storyboards', 'source_assets', 'references',
    'local_drafts/images', 'local_drafts/video', 'local_drafts/audio',
    'premium_generations/higgsfield', 'premium_generations/elevenlabs',
    'narration', 'music', 'sfx', 'captions', 'thumbnails', 'shorts', 'longform',
    'final', 'logs', 'manifests', 'cost', 'qa',
)


def now():
    return datetime.now(timezone.utc).isoformat()


def slugify(value):
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')[:48]
    return slug or 'campaign'


def decode(row):
    if row is None:
        return None
    result = dict(row)
    for key in ('brand_json', 'plan_json', 'data_json', 'settings_json', 'payload_json', 'result_json', 'metadata_json'):
        if key in result:
            result[key.removesuffix('_json')] = json.loads(result.pop(key)) if result[key] else None
    if 'commercial_use' in result:
        result['commercial_use'] = bool(result['commercial_use'])
    if 'ai_generated' in result:
        result['ai_generated'] = bool(result['ai_generated'])
    return result


class Store:
    @staticmethod
    def _ensure_no_premium_job(project):
        if any(job['kind'] == 'premium_render' and job['status'] in ('QUEUED', 'RUNNING')
               for job in project['jobs']):
            raise ValueError('Wait for the Higgsfield render before changing this project')

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.projects_dir = self.data_dir / 'projects'
        self.db_path = self.data_dir / 'studio.sqlite3'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        with self.connection() as conn:
            conn.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                    brief TEXT NOT NULL, treatment_notes TEXT NOT NULL DEFAULT '', brand_json TEXT NOT NULL, plan_json TEXT,
                    profile_id TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'DRAFT',
                    target_duration_seconds INTEGER NOT NULL DEFAULT 15,
                    narration_voice TEXT NOT NULL DEFAULT 'af_sarah',
                    status TEXT NOT NULL DEFAULT 'CREATED', created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    project_id TEXT NOT NULL REFERENCES projects(id), gate TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING', note TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT, PRIMARY KEY(project_id, gate)
                );
                CREATE TABLE IF NOT EXISTS shots (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    ordinal INTEGER NOT NULL, data_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PLANNED',
                    UNIQUE(project_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    shot_id TEXT REFERENCES shots(id), kind TEXT NOT NULL, provider TEXT NOT NULL,
                    classification TEXT NOT NULL, commercial_use INTEGER NOT NULL,
                    ai_generated INTEGER NOT NULL, version INTEGER NOT NULL,
                    relative_path TEXT NOT NULL, prompt TEXT, settings_json TEXT,
                    metadata_json TEXT, source_asset_id TEXT REFERENCES assets(id),
                    status TEXT NOT NULL DEFAULT 'CREATED', created_at TEXT NOT NULL,
                    UNIQUE(project_id, shot_id, kind, version), UNIQUE(project_id, relative_path)
                );
                CREATE TABLE IF NOT EXISTS shot_references (
                    shot_id TEXT NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
                    asset_id TEXT NOT NULL REFERENCES assets(id),
                    guidance TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(shot_id, asset_id)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    kind TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
                    result_json TEXT, provider_job_id TEXT, error TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_usage (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    response_id TEXT UNIQUE, model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL, reasoning_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS premium_runs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL,
                    estimated_usd TEXT NOT NULL, approved_at TEXT,
                    error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS premium_scenes (
                    run_id TEXT NOT NULL REFERENCES premium_runs(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, shot_id TEXT NOT NULL,
                    model_path TEXT NOT NULL, payload_json TEXT NOT NULL,
                    estimated_usd TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
                    request_id TEXT, output_url TEXT, relative_path TEXT, error TEXT,
                    PRIMARY KEY(run_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_premium_runs_project ON premium_runs(project_id, created_at);
            ''')
            if 'target_duration_seconds' not in {row['name'] for row in conn.execute('PRAGMA table_info(projects)')}:
                conn.execute('ALTER TABLE projects ADD COLUMN target_duration_seconds INTEGER NOT NULL DEFAULT 15')
            if 'narration_voice' not in {row['name'] for row in conn.execute('PRAGMA table_info(projects)')}:
                conn.execute("ALTER TABLE projects ADD COLUMN narration_voice TEXT NOT NULL DEFAULT 'af_sarah'")
            if 'treatment_notes' not in {row['name'] for row in conn.execute('PRAGMA table_info(projects)')}:
                conn.execute("ALTER TABLE projects ADD COLUMN treatment_notes TEXT NOT NULL DEFAULT ''")

    def project_dir(self, project):
        return self.projects_dir / project['slug']

    def create_project(self, title, brief, brand, profile_id='astra-medium', target_duration_seconds=15,
                       treatment_notes=''):
        if target_duration_seconds not in (15, 30, 45, 60):
            raise ValueError('Target duration must be 15, 30, 45, or 60 seconds')
        project_id = str(uuid4())
        slug = f'{slugify(title)}-{project_id[:8]}'
        stamp = now()
        with self.connection() as conn:
            conn.execute('INSERT INTO projects (id, slug, title, brief, treatment_notes, brand_json, profile_id, target_duration_seconds, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (project_id, slug, title, brief, treatment_notes, json.dumps(brand), profile_id, target_duration_seconds, stamp, stamp))
            conn.executemany('INSERT INTO approvals (project_id, gate) VALUES (?,?)',
                             ((project_id, gate) for gate in GATES))
        folder = self.projects_dir / slug
        for child in PROJECT_FOLDERS:
            (folder / child).mkdir(parents=True, exist_ok=True)
        (folder / 'project.json').write_text(json.dumps({'id': project_id, 'title': title, 'created_at': stamp,
                                                        'target_duration_seconds': target_duration_seconds,
                                                        'narration_voice': 'af_sarah',
                                                        'classification': 'DRAFT', 'commercial_use': False}, indent=2), encoding='utf-8')
        (folder / 'brief/brief.txt').write_text(brief, encoding='utf-8')
        (folder / 'brief/treatment_notes.txt').write_text(treatment_notes, encoding='utf-8')
        (folder / 'brand/brand.json').write_text(json.dumps(brand, indent=2), encoding='utf-8')
        return self.get_project(project_id)

    def list_projects(self):
        with self.connection() as conn:
            return [decode(row) for row in conn.execute('SELECT * FROM projects ORDER BY updated_at DESC')]

    def delete_project(self, project_id):
        project = self.get_project(project_id)
        if any(job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the active job before deleting this project')
        root = self.project_dir(project).resolve()
        projects_root = self.projects_dir.resolve()
        if root == projects_root or not root.is_relative_to(projects_root):
            raise ValueError('Project directory is outside the project workspace')
        with self.connection() as conn:
            conn.execute('DELETE FROM shot_references WHERE shot_id IN (SELECT id FROM shots WHERE project_id=?)', (project_id,))
            conn.execute('DELETE FROM api_usage WHERE project_id=?', (project_id,))
            conn.execute('DELETE FROM premium_scenes WHERE run_id IN (SELECT id FROM premium_runs WHERE project_id=?)', (project_id,))
            conn.execute('DELETE FROM premium_runs WHERE project_id=?', (project_id,))
            conn.execute('DELETE FROM jobs WHERE project_id=?', (project_id,))
            conn.execute('DELETE FROM approvals WHERE project_id=?', (project_id,))
            while conn.execute('SELECT 1 FROM assets WHERE project_id=? LIMIT 1', (project_id,)).fetchone():
                changed = conn.execute('''DELETE FROM assets WHERE project_id=? AND id NOT IN
                    (SELECT source_asset_id FROM assets WHERE source_asset_id IS NOT NULL)''', (project_id,)).rowcount
                if not changed:
                    raise ValueError('Cannot delete project assets with circular dependencies')
            conn.execute('DELETE FROM shots WHERE project_id=?', (project_id,))
            conn.execute('DELETE FROM projects WHERE id=?', (project_id,))
        if root.exists():
            shutil.rmtree(root)

    def get_project(self, project_id):
        with self.connection() as conn:
            project = decode(conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone())
            if project is None:
                raise KeyError(project_id)
            project['approvals'] = {row['gate']: decode(row) for row in conn.execute('SELECT gate,status,note,reviewed_at FROM approvals WHERE project_id=?', (project_id,))}
            project['shots'] = [decode(row) for row in conn.execute("SELECT * FROM shots WHERE project_id=? AND status='PLANNED' ORDER BY ordinal", (project_id,))]
            project['assets'] = [decode(row) for row in conn.execute('SELECT * FROM assets WHERE project_id=? ORDER BY created_at', (project_id,))]
            project['shot_references'] = [dict(row) for row in conn.execute('''
                SELECT r.shot_id,r.asset_id,r.guidance FROM shot_references r
                JOIN shots s ON s.id=r.shot_id WHERE s.project_id=? AND s.status='PLANNED' ORDER BY s.ordinal,r.rowid''', (project_id,))]
            project['jobs'] = [decode(row) for row in conn.execute('SELECT * FROM jobs WHERE project_id=? ORDER BY created_at', (project_id,))]
            project['premium_runs'] = [dict(row) for row in conn.execute(
                'SELECT id,fingerprint,status,estimated_usd,approved_at,error,created_at,updated_at '
                'FROM premium_runs WHERE project_id=? ORDER BY created_at DESC', (project_id,))]
            return project

    def update_brand(self, project_id, brand):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        with self.connection() as conn:
            conn.execute('UPDATE projects SET brand_json=?,plan_json=NULL,status=?,updated_at=? WHERE id=?',
                         (json.dumps(brand), 'BRIEF_REVISED', now(), project_id))
            conn.execute("UPDATE approvals SET status='PENDING', reviewed_at=NULL WHERE project_id=?", (project_id,))
        (self.project_dir(project) / 'brand/brand.json').write_text(json.dumps(brand, indent=2), encoding='utf-8')
        return self.get_project(project_id)

    def update_brief(self, project_id, brief):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        with self.connection() as conn:
            conn.execute('UPDATE projects SET brief=?,plan_json=NULL,status=?,updated_at=? WHERE id=?',
                         (brief, 'BRIEF_REVISED', now(), project_id))
            conn.execute("UPDATE approvals SET status='PENDING', reviewed_at=NULL WHERE project_id=?", (project_id,))
        (self.project_dir(project) / 'brief/brief.txt').write_text(brief, encoding='utf-8')
        return self.get_project(project_id)

    def update_input(self, project_id, brief, brand, target_duration_seconds, treatment_notes=''):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if target_duration_seconds not in (15, 30, 45, 60):
            raise ValueError('Target duration must be 15, 30, 45, or 60 seconds')
        if any(job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the active job before changing project input')
        with self.connection() as conn:
            self._retire_storyboard(conn, project_id)
            conn.execute('''UPDATE projects SET brief=?,treatment_notes=?,brand_json=?,target_duration_seconds=?,plan_json=NULL,
                status='BRIEF_REVISED',updated_at=? WHERE id=?''',
                         (brief, treatment_notes, json.dumps(brand), target_duration_seconds, now(), project_id))
            conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=?", (project_id,))
        root = self.project_dir(project)
        (root / 'brief/brief.txt').write_text(brief, encoding='utf-8')
        (root / 'brief/treatment_notes.txt').write_text(treatment_notes, encoding='utf-8')
        (root / 'brand/brand.json').write_text(json.dumps(brand, indent=2), encoding='utf-8')
        (root / 'project.json').write_text(json.dumps({'id': project_id, 'title': project['title'],
            'created_at': project['created_at'], 'target_duration_seconds': target_duration_seconds,
            'narration_voice': project['narration_voice'],
            'classification': 'DRAFT', 'commercial_use': False}, indent=2), encoding='utf-8')
        return self.get_project(project_id)

    def set_plan(self, project_id, plan):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if project['approvals']['brief']['status'] != 'APPROVED':
            raise ValueError('Creative brief approval is required before planning')
        with self.connection() as conn:
            self._retire_storyboard(conn, project_id)
            conn.execute('UPDATE projects SET plan_json=?,status=?,updated_at=? WHERE id=?',
                         (json.dumps(plan), 'PLANNED', now(), project_id))
            conn.execute("UPDATE approvals SET status='PENDING', reviewed_at=NULL WHERE project_id=? AND gate IN ('concept','storyboard','rough_cut','premium_spend','final')", (project_id,))
        (self.project_dir(project) / 'scripts/plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        return self.get_project(project_id)

    @staticmethod
    def _retire_storyboard(conn, project_id):
        """Keep earlier rows/files for provenance while removing them from the active edit."""
        highest = conn.execute('SELECT COALESCE(MAX(ordinal),0) FROM shots WHERE project_id=?', (project_id,)).fetchone()[0]
        conn.execute("UPDATE shots SET ordinal=ordinal+?,status='SUPERSEDED' WHERE project_id=? AND status='PLANNED'",
                     (highest + 1000, project_id))
        conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND kind!='reference_image' AND status='CREATED'",
                     (project_id,))
        conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? AND gate IN ('storyboard','rough_cut','premium_spend','final')",
                     (project_id,))

    def update_direction(self, project_id, concept, script):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if project['approvals']['brief']['status'] != 'APPROVED':
            raise ValueError('Approve the brief before editing direction')
        if any(job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the active job before editing direction')
        plan = dict(project['plan'] or {})
        plan.update({'concept': concept.strip(), 'script': script.strip()})
        plan.setdefault('target_audience', '')
        plan.setdefault('key_message', '')
        plan.setdefault('claims_used', [])
        plan.setdefault('shots', [])
        with self.connection() as conn:
            self._retire_storyboard(conn, project_id)
            conn.execute('UPDATE projects SET plan_json=?,status=?,updated_at=? WHERE id=?',
                         (json.dumps(plan), 'DIRECTION_REVISED', now(), project_id))
            conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? AND gate IN ('concept','storyboard','rough_cut','premium_spend','final')", (project_id,))
        (self.project_dir(project) / 'scripts/plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        return self.get_project(project_id)

    def update_script(self, project_id, script):
        project = self.get_project(project_id)
        if not project['plan']:
            raise ValueError('Create a concept plan before editing its script')
        return self.update_direction(project_id, project['plan']['concept'], script)

    def update_voice(self, project_id, voice_id):
        from .voices import voice_language
        if voice_language(voice_id) is None:
            raise ValueError('Selected voice is not installed or is not an English voice')
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if project['narration_voice'] == voice_id:
            return project
        if any(job['kind'] == 'local_draft' and job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the current local draft job before changing the voice')
        with self.connection() as conn:
            conn.execute('UPDATE projects SET narration_voice=?,updated_at=? WHERE id=?',
                         (voice_id, now(), project_id))
            conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? "
                         "AND kind IN ('narration','captions','captions_vtt','rough_cut') AND status='CREATED'",
                         (project_id,))
            conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? "
                         "AND gate IN ('rough_cut','premium_spend','final')", (project_id,))
        path = self.project_dir(project) / 'project.json'
        metadata = json.loads(path.read_text(encoding='utf-8'))
        metadata['narration_voice'] = voice_id
        path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        return self.get_project(project_id)

    def set_shots(self, project_id, shots):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if project['approvals']['concept']['status'] != 'APPROVED':
            raise ValueError('Concept approval is required before storyboarding')
        if any(job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the active job before changing storyboard scenes')
        if not shots:
            raise ValueError('Add at least one scene')
        plan = dict(project['plan'])
        plan['shots'] = shots
        with self.connection() as conn:
            self._retire_storyboard(conn, project_id)
            for ordinal, data in enumerate(shots, 1):
                conn.execute('INSERT INTO shots (id,project_id,ordinal,data_json) VALUES (?,?,?,?)',
                             (str(uuid4()), project_id, ordinal, json.dumps(data)))
            conn.execute('UPDATE projects SET plan_json=?,updated_at=? WHERE id=?', (json.dumps(plan), now(), project_id))
            conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? AND gate IN ('storyboard','rough_cut','premium_spend','final')", (project_id,))
        (self.project_dir(project) / 'storyboards/shots.json').write_text(json.dumps(shots, indent=2), encoding='utf-8')
        (self.project_dir(project) / 'scripts/plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        return self.get_project(project_id)

    def update_shot(self, project_id, shot_id, data):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        shot = next((item for item in project['shots'] if item['id'] == shot_id), None)
        if shot is None:
            raise ValueError('Shot does not belong to project')
        if any(job['kind'] == 'local_draft' and job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the current local draft job before editing a shot')
        plan = dict(project['plan']) if project['plan'] else None
        if plan and 'shots' in plan and len(plan['shots']) >= shot['ordinal']:
            plan['shots'][shot['ordinal'] - 1] = data
        with self.connection() as conn:
            conn.execute('UPDATE shots SET data_json=? WHERE id=? AND project_id=?',
                         (json.dumps(data), shot_id, project_id))
            if plan:
                conn.execute('UPDATE projects SET plan_json=?,updated_at=? WHERE id=?',
                             (json.dumps(plan), now(), project_id))
            else:
                conn.execute('UPDATE projects SET updated_at=? WHERE id=?', (now(), project_id))
            conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? "
                         "AND gate IN ('storyboard','rough_cut','premium_spend','final')", (project_id,))
            conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND shot_id=? AND kind IN ('storyboard_frame','draft_clip') AND status='CREATED'", (project_id, shot_id))
            conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND kind='rough_cut' AND status='CREATED'", (project_id,))
        updated = self.get_project(project_id)
        (self.project_dir(updated) / 'storyboards/shots.json').write_text(
            json.dumps([item['data'] for item in updated['shots']], indent=2), encoding='utf-8')
        if plan:
            (self.project_dir(updated) / 'scripts/plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        return updated

    def review_gate(self, project_id, gate, approve, note=''):
        if gate not in GATES:
            raise ValueError('Unknown approval gate')
        if gate == 'premium_spend':
            raise ValueError('Approve a specific Higgsfield estimate in Step 5b')
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if approve:
            index = GATES.index(gate)
            previous = GATES[:index]
            if gate == 'final':
                previous = ('brief', 'concept', 'storyboard', 'rough_cut')
            if any(project['approvals'][prior]['status'] != 'APPROVED' for prior in previous):
                raise ValueError('Earlier approval gate is not approved')
            if gate == 'concept' and not project['plan']:
                raise ValueError('Concept/script plan is missing')
            if gate == 'storyboard' and not project['shots']:
                raise ValueError('Storyboard shots are missing')
            if gate == 'storyboard' and abs(sum(float(s['data'].get('duration_seconds', 3)) for s in project['shots']) - project['target_duration_seconds']) > 0.05:
                raise ValueError('Scene durations must add up to the target film length')
            if gate == 'rough_cut' and not any(a['kind'] == 'rough_cut' and a['status'] == 'CREATED' for a in project['assets']):
                raise ValueError('Rough cut asset is missing')
        with self.connection() as conn:
            if not approve and gate in ('brief', 'concept'):
                self._retire_storyboard(conn, project_id)
            elif not approve and gate == 'storyboard':
                conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND kind='rough_cut' AND status='CREATED'", (project_id,))
            conn.execute('UPDATE approvals SET status=?,note=?,reviewed_at=? WHERE project_id=? AND gate=?',
                         ('APPROVED' if approve else 'REJECTED', note, now(), project_id, gate))
            if not approve:
                for later in GATES[GATES.index(gate) + 1:]:
                    conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? AND gate=?", (project_id, later))
        return self.get_project(project_id)

    def add_asset(self, project_id, kind, provider, relative_path, *, shot_id=None, prompt=None,
                  settings=None, metadata=None, source_asset_id=None, commercial_use=False,
                  ai_generated=True):
        project = self.get_project(project_id)
        root = self.project_dir(project).resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Asset file must exist inside the project directory')
        if commercial_use:
            raise ValueError('Phase 2 assets are non-commercial drafts only')
        if shot_id and shot_id not in {shot['id'] for shot in project['shots']}:
            raise ValueError('Shot does not belong to project')
        stamp = now()
        with self.connection() as conn:
            version = conn.execute('SELECT COALESCE(MAX(version),0)+1 FROM assets WHERE project_id=? AND shot_id IS ? AND kind=?',
                                   (project_id, shot_id, kind)).fetchone()[0]
            asset_id = str(uuid4())
            conn.execute('''INSERT INTO assets (id,project_id,shot_id,kind,provider,classification,commercial_use,
                ai_generated,version,relative_path,prompt,settings_json,metadata_json,source_asset_id,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (asset_id, project_id, shot_id, kind, provider,
                          'AI-generated DRAFT' if ai_generated and not commercial_use else 'SOURCE' if not ai_generated else 'PREMIUM',
                          int(commercial_use), int(ai_generated), version, str(path.relative_to(root)), prompt,
                          json.dumps(settings) if settings is not None else None,
                          json.dumps(metadata) if metadata is not None else None, source_asset_id, stamp))
        return next(asset for asset in self.get_project(project_id)['assets'] if asset['id'] == asset_id)

    def get_asset(self, project_id, asset_id):
        project = self.get_project(project_id)
        return next((asset for asset in project['assets'] if asset['id'] == asset_id), None)

    def update_reference(self, project_id, asset_id, role, description):
        if role not in {'character', 'product', 'style', 'location', 'other'} or len(description) > 2000:
            raise ValueError('Invalid reference role or description')
        project = self.get_project(project_id)
        asset = self.get_asset(project_id, asset_id)
        if not asset or asset['kind'] != 'reference_image' or asset['ai_generated']:
            raise ValueError('Reference image not found in this project')
        if any(job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the active job before changing a reference image')
        metadata = dict(asset.get('metadata') or {})
        if metadata.get('role') == role and metadata.get('description', '') == description:
            return project
        metadata.update(role=role, description=description)
        linked_shots = {link['shot_id'] for link in project['shot_references'] if link['asset_id'] == asset_id}
        with self.connection() as conn:
            conn.execute('UPDATE assets SET metadata_json=? WHERE id=? AND project_id=?',
                         (json.dumps(metadata), asset_id, project_id))
            conn.execute('UPDATE projects SET updated_at=? WHERE id=?', (now(), project_id))
            for shot_id in linked_shots:
                self._invalidate_reference_dependents(conn, project_id, shot_id)
        return self.get_project(project_id)

    def delete_reference(self, project_id, asset_id):
        project = self.get_project(project_id)
        asset = self.get_asset(project_id, asset_id)
        if not asset or asset['kind'] != 'reference_image' or asset['ai_generated']:
            raise ValueError('Reference image not found in this project')
        if any(job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the active job before deleting a reference image')
        if any(item['source_asset_id'] == asset_id for item in project['assets']):
            raise ValueError('This reference is still a source for another asset')
        root = self.project_dir(project).resolve()
        path = (root / asset['relative_path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Reference image is outside the project directory')
        linked_shots = {link['shot_id'] for link in project['shot_references'] if link['asset_id'] == asset_id}
        with self.connection() as conn:
            conn.execute('DELETE FROM shot_references WHERE asset_id=?', (asset_id,))
            conn.execute('DELETE FROM assets WHERE id=? AND project_id=?', (asset_id, project_id))
            conn.execute('UPDATE projects SET updated_at=? WHERE id=?', (now(), project_id))
            for shot_id in linked_shots:
                self._invalidate_reference_dependents(conn, project_id, shot_id)
        path.unlink(missing_ok=True)
        return self.get_project(project_id)

    def attach_reference(self, project_id, shot_id, asset_id, guidance=''):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if shot_id not in {shot['id'] for shot in project['shots']}:
            raise ValueError('Shot does not belong to project')
        asset = self.get_asset(project_id, asset_id)
        if not asset or asset['kind'] != 'reference_image' or asset['ai_generated']:
            raise ValueError('Reference must be an uploaded image from this project')
        if any(job['kind'] == 'local_draft' and job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the current local draft job to finish before changing references')
        with self.connection() as conn:
            conn.execute('''INSERT INTO shot_references (shot_id,asset_id,guidance) VALUES (?,?,?)
                ON CONFLICT(shot_id,asset_id) DO UPDATE SET guidance=excluded.guidance''',
                (shot_id, asset_id, guidance))
            conn.execute('UPDATE projects SET updated_at=? WHERE id=?', (now(), project_id))
            self._invalidate_reference_dependents(conn, project_id, shot_id)
        return self.get_project(project_id)

    def detach_reference(self, project_id, shot_id, asset_id):
        project = self.get_project(project_id)
        self._ensure_no_premium_job(project)
        if shot_id not in {shot['id'] for shot in project['shots']}:
            raise ValueError('Shot does not belong to project')
        if any(job['kind'] == 'local_draft' and job['status'] in ('QUEUED', 'RUNNING') for job in project['jobs']):
            raise ValueError('Wait for the current local draft job to finish before changing references')
        with self.connection() as conn:
            conn.execute('DELETE FROM shot_references WHERE shot_id=? AND asset_id=?', (shot_id, asset_id))
            conn.execute('UPDATE projects SET updated_at=? WHERE id=?', (now(), project_id))
            self._invalidate_reference_dependents(conn, project_id, shot_id)
        return self.get_project(project_id)

    @staticmethod
    def _invalidate_reference_dependents(conn, project_id, shot_id):
        conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND shot_id=? AND kind IN ('storyboard_frame','draft_clip') AND status='CREATED'",
                     (project_id, shot_id))
        conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND kind='rough_cut' AND status='CREATED'", (project_id,))
        conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? AND gate IN ('storyboard','rough_cut','premium_spend','final')",
                     (project_id,))

    def supersede_audio_and_cut(self, project_id):
        self.get_project(project_id)
        with self.connection() as conn:
            conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND kind IN ('narration','captions','captions_vtt','rough_cut') AND status='CREATED'",
                         (project_id,))
            conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? AND gate IN ('rough_cut','final')",
                         (project_id,))
            conn.execute('UPDATE projects SET updated_at=? WHERE id=?', (now(), project_id))
        return self.get_project(project_id)

    def create_job(self, project_id, kind, payload):
        self.get_project(project_id)
        job_id = str(uuid4())
        stamp = now()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            active = conn.execute("SELECT id FROM jobs WHERE project_id=? AND kind=? AND status IN ('QUEUED','RUNNING')",
                                  (project_id, kind)).fetchone()
            if active:
                return self.get_job(active['id'])
            conn.execute('INSERT INTO jobs (id,project_id,kind,status,payload_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                         (job_id, project_id, kind, 'QUEUED', json.dumps(payload), stamp, stamp))
        return self.get_job(job_id)

    def reset_video_drafts_for_model(self, project_id, model_id):
        """Retire clips and cut when a new renderer is chosen; retain frames and voice."""
        project = self.get_project(project_id)
        active_clips = [asset for asset in project['assets']
                        if asset['kind'] == 'draft_clip' and asset['status'] == 'CREATED']
        if not active_clips:
            return
        if all((asset.get('metadata') or {}).get('model_id', 'ltx-2b') == model_id
               for asset in active_clips):
            return
        with self.connection() as conn:
            conn.execute("UPDATE assets SET status='SUPERSEDED' WHERE project_id=? AND kind IN ('draft_clip','rough_cut') AND status='CREATED'",
                         (project_id,))
            conn.execute("UPDATE approvals SET status='PENDING',reviewed_at=NULL WHERE project_id=? AND gate IN ('rough_cut','final')",
                         (project_id,))
            conn.execute('UPDATE projects SET updated_at=? WHERE id=?', (now(), project_id))

    def get_job(self, job_id):
        with self.connection() as conn:
            result = decode(conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())
            if result is None:
                raise KeyError(job_id)
            return result

    def requeue_interrupted_local_jobs(self):
        with self.connection() as conn:
            conn.execute("UPDATE jobs SET status='QUEUED',updated_at=? WHERE status='RUNNING' AND kind LIKE 'local_%'", (now(),))
            # A premium scene with a persisted request ID can resume polling. An
            # interrupted SUBMITTING scene may have been charged, so hold it.
            premium_jobs = conn.execute("SELECT id,payload_json FROM jobs WHERE status='RUNNING' AND kind='premium_render'").fetchall()
            for job in premium_jobs:
                run_id = json.loads(job['payload_json'])['run_id']
                uncertain = conn.execute("SELECT 1 FROM premium_scenes WHERE run_id=? AND status='SUBMITTING' AND request_id IS NULL", (run_id,)).fetchone()
                conn.execute('UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=?',
                             ('NEEDS_REVIEW' if uncertain else 'QUEUED',
                              'A Higgsfield submission may have been accepted; check the API console before retrying' if uncertain else None,
                              now(), job['id']))
                if uncertain:
                    conn.execute("UPDATE premium_runs SET status='NEEDS_REVIEW',error=?,updated_at=? WHERE id=?",
                                 ('A submission may have been accepted; check the API console', now(), run_id))
            conn.execute("UPDATE jobs SET status='NEEDS_REVIEW',error=?,updated_at=? WHERE status='RUNNING' AND kind NOT LIKE 'local_%' AND kind!='premium_render' AND provider_job_id IS NULL",
                         ('Interrupted request may have incurred a charge; review before retrying', now()))

    def claim_job(self):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute("SELECT id FROM jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            conn.execute("UPDATE jobs SET status='RUNNING',attempts=attempts+1,updated_at=? WHERE id=?", (now(), row['id']))
        return self.get_job(row['id'])

    def finish_job(self, job_id, *, result=None, error=None):
        with self.connection() as conn:
            conn.execute('UPDATE jobs SET status=?,result_json=?,error=?,updated_at=? WHERE id=?',
                         ('FAILED' if error else 'SUCCEEDED', json.dumps(result) if result is not None else None,
                          error, now(), job_id))
        return self.get_job(job_id)

    def mark_job_review(self, job_id, reason):
        with self.connection() as conn:
            conn.execute("UPDATE jobs SET status='NEEDS_REVIEW',error=?,updated_at=? WHERE id=?",
                         (reason, now(), job_id))
        return self.get_job(job_id)

    def record_usage(self, project_id, response):
        usage = response.get('usage') or {}
        details = usage.get('output_tokens_details') or {}
        with self.connection() as conn:
            conn.execute('INSERT OR IGNORE INTO api_usage VALUES (?,?,?,?,?,?,?,?)',
                         (str(uuid4()), project_id, response['response_id'], response['model'],
                          usage.get('input_tokens', 0), usage.get('output_tokens', 0),
                          details.get('reasoning_tokens', 0), now()))

    def create_premium_quote(self, project_id, fingerprint, scenes):
        """Persist scene inputs and indicative provider estimates shown for approval."""
        self.get_project(project_id)
        run_id = str(uuid4())
        stamp = now()
        from decimal import Decimal
        total = sum((Decimal(str(scene['estimated_usd'])) for scene in scenes), Decimal('0'))
        with self.connection() as conn:
            conn.execute('INSERT INTO premium_runs VALUES (?,?,?,?,?,?,?,?,?)',
                         (run_id, project_id, fingerprint, 'QUOTED', str(total), None, None, stamp, stamp))
            conn.executemany('''INSERT INTO premium_scenes
                (run_id,ordinal,shot_id,model_path,payload_json,estimated_usd,status)
                VALUES (?,?,?,?,?,?,'PENDING')''',
                ((run_id, item['ordinal'], item['shot_id'], item['model_path'],
                  json.dumps(item['payload']), str(item['estimated_usd'])) for item in scenes))
        return self.get_premium_run(project_id, run_id)

    def get_premium_run(self, project_id, run_id):
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM premium_runs WHERE id=? AND project_id=?', (run_id, project_id)).fetchone()
            if row is None:
                raise KeyError(run_id)
            result = dict(row)
            result['scenes'] = [decode(scene) for scene in conn.execute(
                'SELECT * FROM premium_scenes WHERE run_id=? ORDER BY ordinal', (run_id,))]
            return result

    def approve_premium_run(self, project_id, run_id, fingerprint):
        run = self.get_premium_run(project_id, run_id)
        project = self.get_project(project_id)
        if run['status'] != 'QUOTED' or run['fingerprint'] != fingerprint:
            raise ValueError('The storyboard or references changed; request a new estimate')
        if project['approvals']['storyboard']['status'] != 'APPROVED':
            raise ValueError('Approve the storyboard before premium spend')
        with self.connection() as conn:
            conn.execute("UPDATE premium_runs SET status='APPROVED',approved_at=?,updated_at=? WHERE id=?",
                         (now(), now(), run_id))
            conn.execute("UPDATE approvals SET status='APPROVED',note=?,reviewed_at=? WHERE project_id=? AND gate='premium_spend'",
                         (f'Higgsfield run {run_id}; estimate USD {run["estimated_usd"]}', now(), project_id))
        return self.get_premium_run(project_id, run_id)

    def update_premium_run(self, project_id, run_id, status, error=None):
        self.get_premium_run(project_id, run_id)
        with self.connection() as conn:
            conn.execute('UPDATE premium_runs SET status=?,error=?,updated_at=? WHERE id=? AND project_id=?',
                         (status, error, now(), run_id, project_id))

    def update_premium_scene(self, project_id, run_id, ordinal, status, **fields):
        self.get_premium_run(project_id, run_id)
        allowed = {'request_id', 'output_url', 'relative_path', 'error'}
        if set(fields) - allowed:
            raise ValueError('Unknown premium scene field')
        assignments = ','.join(['status=?'] + [f'{key}=?' for key in fields])
        values = [status, *fields.values(), run_id, ordinal]
        with self.connection() as conn:
            changed = conn.execute(f'UPDATE premium_scenes SET {assignments} WHERE run_id=? AND ordinal=?', values).rowcount
            conn.execute('UPDATE premium_runs SET updated_at=? WHERE id=?', (now(), run_id))
        if changed != 1:
            raise KeyError(ordinal)

    def retry_failed_premium_run(self, project_id, run_id, fingerprint):
        run = self.get_premium_run(project_id, run_id)
        if run['status'] != 'FAILED' or run['fingerprint'] != fingerprint:
            raise ValueError('Only a failed, unchanged Higgsfield run can be retried')
        if not any(scene['status'] == 'FAILED' for scene in run['scenes']):
            raise ValueError('No failed scene is available to retry')
        with self.connection() as conn:
            conn.execute("UPDATE premium_scenes SET status='PENDING',request_id=NULL,output_url=NULL,relative_path=NULL,error=NULL "
                         "WHERE run_id=? AND status='FAILED'", (run_id,))
            conn.execute("UPDATE premium_runs SET status='APPROVED',error=NULL,updated_at=? WHERE id=?",
                         (now(), run_id))
        return self.get_premium_run(project_id, run_id)

    def reconcile_premium_submission(self, project_id, run_id, ordinal, request_id, fingerprint):
        run = self.get_premium_run(project_id, run_id)
        if run['status'] != 'NEEDS_REVIEW' or run['fingerprint'] != fingerprint:
            raise ValueError('This Higgsfield run cannot be reconciled; request a fresh estimate if inputs changed')
        scene = next((item for item in run['scenes'] if item['ordinal'] == ordinal), None)
        if not scene or scene['status'] != 'SUBMITTING' or scene['request_id']:
            raise ValueError('No uncertain submission exists for that scene')
        with self.connection() as conn:
            conn.execute("UPDATE premium_scenes SET request_id=?,status='RUNNING',error=NULL WHERE run_id=? AND ordinal=?",
                         (request_id, run_id, ordinal))
            conn.execute("UPDATE premium_runs SET status='RUNNING',error=NULL,updated_at=? WHERE id=?",
                         (now(), run_id))
        return self.get_premium_run(project_id, run_id)

    def confirm_no_premium_submission(self, project_id, run_id, ordinal, fingerprint):
        run = self.get_premium_run(project_id, run_id)
        if run['status'] != 'NEEDS_REVIEW' or run['fingerprint'] != fingerprint:
            raise ValueError('This Higgsfield run cannot be released; request a fresh estimate if inputs changed')
        scene = next((item for item in run['scenes'] if item['ordinal'] == ordinal), None)
        if not scene or scene['status'] != 'SUBMITTING' or scene['request_id']:
            raise ValueError('No uncertain submission exists for that scene')
        with self.connection() as conn:
            conn.execute("UPDATE premium_scenes SET status='PENDING',error=NULL WHERE run_id=? AND ordinal=?",
                         (run_id, ordinal))
            conn.execute("UPDATE premium_runs SET status='APPROVED',error=NULL,updated_at=? WHERE id=?",
                         (now(), run_id))
        return self.get_premium_run(project_id, run_id)
