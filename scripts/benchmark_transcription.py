"""Transcribe the generated narration locally and verify segment timing."""
import json
import time

from faster_whisper import WhisperModel
from backend.config import ROOT, Settings
from backend.local_paths import whisper_model


def main():
    settings = Settings()
    audio = settings.data_dir / 'benchmarks/kokoro_narration_001.wav'
    model_cache = ROOT / 'data/models/whisper'
    model_cached = any(model_cache.rglob('model.bin')) if model_cache.exists() else False
    started = time.monotonic()
    model = WhisperModel(whisper_model(), device='cpu', compute_type='int8', download_root=str(model_cache))
    segments, info = model.transcribe(str(audio), language='en', beam_size=1)
    segments = [{'start': round(s.start, 2), 'end': round(s.end, 2), 'text': s.text.strip()} for s in segments]
    if not segments or any(s['end'] <= s['start'] or not s['text'] for s in segments):
        raise RuntimeError('Whisper produced no valid timed transcript')
    report = {'provider': 'faster-whisper', 'model': 'tiny.en', 'language': info.language,
              'segments': segments, 'model_cached_before_run': model_cached,
              'generation_seconds': round(time.monotonic()-started, 2), 'status': 'PASS'}
    output = settings.data_dir / 'benchmarks/whisper_benchmark.json'
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
