"""Preview, then save a continuous 15-second voiceover for the existing demo."""
import argparse
import asyncio
import json

from backend.config import ROOT, Settings
from backend.local_media import LocalDraftGenerator, existing_asset
from backend.store import Store


SCRIPT = (
    'Meet SpiceBerry, a bright berry moment in a bottle. '
    'Fresh berry flavour brings colour to your day. '
    'Pour a glass, take a breath, and enjoy the little moments wherever you are. '
    'SpiceBerry. Bring a brighter moment to the table.'
)


def preview():
    from kokoro_onnx import Kokoro
    models = ROOT / 'data/models/kokoro'
    voice = Kokoro(str(models / 'kokoro-v1.0.onnx'), str(models / 'voices-v1.0.bin'))
    samples, sample_rate = voice.create(SCRIPT, voice='af_sarah', speed=1.0, lang='en-us')
    print(json.dumps({'words': len(SCRIPT.split()), 'duration_at_speed_1': round(len(samples) / sample_rate, 2),
                      'script': SCRIPT}, indent=2))


async def apply():
    settings = Settings()
    store = Store(settings.data_dir)
    marker = settings.data_dir / 'benchmarks/phase2_demo_project.json'
    project_id = json.loads(marker.read_text(encoding='utf-8'))['project_id']
    project = store.get_project(project_id)
    if project['plan']['script'] != SCRIPT:
        project = store.update_script(project_id, SCRIPT)
    else:
        audio = existing_asset(project, 'narration')
        if audio and audio['metadata'].get('timing') != 'one continuous take':
            project = store.supersede_audio_and_cut(project_id)
    for gate in ('concept', 'storyboard'):
        if project['approvals'][gate]['status'] != 'APPROVED':
            project = store.review_gate(project_id, gate, True, 'Approved only for local demonstration')
    result = await LocalDraftGenerator(store, settings).generate(project_id)
    print(json.dumps({'project_id': project_id, **result}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    options = parser.parse_args()
    if options.apply:
        asyncio.run(apply())
    else:
        preview()
