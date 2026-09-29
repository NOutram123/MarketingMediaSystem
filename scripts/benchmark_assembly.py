"""Encode a draft video with the generated image and narration, then probe it."""
import json
import subprocess
import time

from backend.config import Settings


def main():
    settings = Settings()
    if not settings.local_drafts_noncommercial:
        raise RuntimeError('Local draft non-commercial policy must be enabled')
    folder = settings.data_dir / 'benchmarks'
    image = folder / 'flux_schnell_storyboard_001.png'
    audio = folder / 'kokoro_narration_001.wav'
    output = folder / 'foundation_draft_001.mp4'
    started = time.monotonic()
    command = [settings.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
               '-loop', '1', '-framerate', '24', '-i', str(image), '-i', str(audio),
               '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24', '-c:a', 'aac',
               '-shortest', '-movflags', '+faststart', '-metadata',
               'comment=DRAFT; non-commercial previsualisation only', str(output)]
    subprocess.run(command, capture_output=True, text=True, check=True, timeout=90)
    probed = subprocess.run([settings.ffprobe_path, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)], capture_output=True, text=True, check=True, timeout=15)
    data = json.loads(probed.stdout)
    streams = data['streams']
    video = next((s for s in streams if s['codec_type'] == 'video'), None)
    audio_stream = next((s for s in streams if s['codec_type'] == 'audio'), None)
    duration = float(data['format']['duration'])
    if not video or not audio_stream or (video['width'], video['height']) != (1280, 720) or not 2.5 < duration < 4:
        raise RuntimeError('Invalid FFmpeg draft output')
    report = {'provider': 'FFmpeg', 'duration_seconds': round(duration, 2), 'encode_seconds': round(time.monotonic()-started, 2),
              'width': video['width'], 'height': video['height'], 'video_codec': video['codec_name'],
              'audio_codec': audio_stream['codec_name'], 'output': str(output), 'bytes': output.stat().st_size,
              'classification': 'DRAFT', 'commercial_use': False, 'status': 'PASS'}
    (folder / 'assembly_benchmark.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
