"""Generate and probe a short local narration with Kokoro ONNX."""
import json
import subprocess
import time
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

from backend.config import ROOT, Settings


def main():
    settings = Settings()
    if not settings.local_drafts_noncommercial:
        raise RuntimeError('Local draft non-commercial policy must be enabled')
    models = ROOT / 'data/models/kokoro'
    output_dir = settings.data_dir / 'benchmarks'
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    kokoro = Kokoro(str(models / 'kokoro-v1.0.onnx'), str(models / 'voices-v1.0.bin'))
    narration = 'SpiceBerry brings a bright berry moment to your day.'
    samples, sample_rate = kokoro.create(narration, voice='af_sarah', speed=1, lang='en-us')
    output = output_dir / 'kokoro_narration_001.wav'
    sf.write(output, samples, sample_rate)
    result = subprocess.run([settings.ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(output)], capture_output=True, text=True, check=True, timeout=15)
    duration = float(json.loads(result.stdout)['format']['duration'])
    if not 1 < duration < 30:
        raise RuntimeError(f'Invalid narration duration: {duration}')
    report = {'provider': 'Kokoro ONNX', 'voice': 'af_sarah', 'sample_rate': sample_rate,
              'duration_seconds': round(duration, 2), 'generation_seconds': round(time.monotonic()-started, 2),
              'output': str(output), 'bytes': output.stat().st_size,
              'classification': 'DRAFT', 'commercial_use': False, 'status': 'PASS'}
    (output_dir / 'kokoro_benchmark.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
