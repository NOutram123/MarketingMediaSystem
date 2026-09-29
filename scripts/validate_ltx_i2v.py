"""Validate one restartable image-conditioned LTX shot without a paid API call."""
import asyncio
import json
import shutil

from backend.config import Settings
from backend.local_media import LocalDraftGenerator, probe
from backend.schemas import BrandKit
from backend.store import Store


async def main():
    settings = Settings()
    store = Store(settings.data_dir)
    marker = settings.data_dir / 'benchmarks/ltx_i2v_project.json'
    if marker.is_file():
        project_id = json.loads(marker.read_text(encoding='utf-8'))['project_id']
        project = store.get_project(project_id)
        shot = project['shots'][0]
    else:
        prior = next((item for item in store.list_projects()
                      if item['title'] == 'LTX image guidance validation'), None)
        if prior:
            project = store.get_project(prior['id'])
            project_id = project['id']
            shot = project['shots'][0]
        else:
            project = store.create_project('LTX image guidance validation',
                                           'Validate one image-guided, non-commercial LTX draft shot.',
                                           BrandKit(product_name='SpiceBerry').model_dump())
            project_id = project['id']
            store.review_gate(project_id, 'brief', True)
            store.set_plan(project_id, {'concept': 'A bottle on a wooden table',
                                        'script': 'SpiceBerry brings a bright berry moment.'})
            store.review_gate(project_id, 'concept', True)
            shot = store.set_shots(project_id, [{'purpose': 'Bottle hero',
                                                'image_prompt': 'Berry drink bottle on a wooden table',
                                                'video_prompt': 'A berry drink bottle stands on a wooden table as the camera slowly pushes in.',
                                                'negative_prompt': 'distorted, flicker, text, logo'}])['shots'][0]
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({'project_id': project_id}, indent=2), encoding='utf-8')
    root = store.project_dir(project)
    frame = root / 'local_drafts/images/shot_01.png'
    if not frame.is_file():
        shutil.copyfile(settings.data_dir / 'benchmarks/flux_schnell_storyboard_001.png', frame)
    if not any(asset['kind'] == 'storyboard_frame' for asset in store.get_project(project_id)['assets']):
        store.add_asset(project_id, 'storyboard_frame', 'comfyui_flux_schnell', frame.relative_to(root),
                        shot_id=shot['id'], prompt=shot['data']['image_prompt'])
    generator = LocalDraftGenerator(store, settings)
    video = await generator.video(store.get_project(project_id), shot, frame)
    media = probe(video, settings)
    print(json.dumps({'project_id': project_id, 'video': str(video),
                      'duration_seconds': media['format']['duration'],
                      'streams': [(stream['codec_type'], stream.get('width'), stream.get('height'))
                                  for stream in media['streams']]}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
