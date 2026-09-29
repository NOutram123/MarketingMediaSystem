import shutil
import subprocess
from pathlib import Path

import pytest

from backend.config import Settings
from backend.local_media import LocalDraftGenerator, probe
from backend.schemas import BrandKit
from backend.store import Store


def test_variable_scene_rough_cut_has_target_duration(tmp_path):
    settings = Settings(data_dir=tmp_path)
    if not Path(settings.ffmpeg_path).is_file() and not shutil.which(settings.ffmpeg_path):
        pytest.skip('FFmpeg is not installed')
    store = Store(tmp_path)
    project = store.create_project('Variable local', 'A 15-second film with two scenes.',
                                   BrandKit(product_name='Berry').model_dump())
    pid = project['id']
    store.review_gate(pid, 'brief', True)
    shots = [{'purpose': 'First', 'duration_seconds': 6}, {'purpose': 'Second', 'duration_seconds': 9}]
    store.set_plan(pid, {'concept': 'Two scenes', 'script': 'A continuous narration for this local film.', 'shots': shots})
    store.review_gate(pid, 'concept', True)
    project = store.set_shots(pid, shots)
    store.review_gate(pid, 'storyboard', True)
    root = store.project_dir(project)
    clips = []
    for index, shot in enumerate(project['shots']):
        clip = root / f'local_drafts/video/fixture_{index}.mp4'
        subprocess.run([settings.ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', f'color=c={"red" if index == 0 else "blue"}:s=512x288:r=16:d=3',
                        '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)], check=True)
        store.add_asset(pid, 'draft_clip', 'fixture', clip.relative_to(root), shot_id=shot['id'])
        clips.append(clip)
    audio = root / 'local_drafts/audio/fixture.wav'
    subprocess.run([settings.ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'sine=frequency=440:duration=15', str(audio)], check=True)
    store.add_asset(pid, 'narration', 'fixture', audio.relative_to(root))
    captions = root / 'captions/fixture.srt'
    captions.write_text('1\n00:00:00,000 --> 00:00:15,000\nA continuous narration\n', encoding='utf-8')
    store.add_asset(pid, 'captions', 'fixture', captions.relative_to(root))

    output = LocalDraftGenerator(store, settings).assemble(store.get_project(pid), clips, audio, captions)
    media = probe(output, settings)
    assert 14.5 <= float(media['format']['duration']) <= 15.5
    assert any(stream['codec_type'] == 'subtitle' for stream in media['streams'])
