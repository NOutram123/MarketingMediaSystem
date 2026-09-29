"""One minimal paid Responses API structured-output probe, only with a configured key."""
import json
from datetime import datetime, timezone

from backend.config import Settings
from backend.orchestration import OpenAIOrchestrator, ValidationProbe


def main():
    settings = Settings()
    if not settings.openai_api_key.get_secret_value():
        print('SKIPPED: OPENAI_API_KEY is not configured')
        return
    response = OpenAIOrchestrator(settings).structured(
        'Return ok=true and a note of no more than five words confirming this structured API test.',
        ValidationProbe,
    )
    if not response['result'].ok:
        raise RuntimeError('OpenAI structured validation probe did not return ok=true')
    report = {'at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'PASS',
              'response_id': response['response_id'], 'model': response['model'],
              'result': response['result'].model_dump(), 'usage': response['usage']}
    destination = settings.data_dir / 'benchmarks/openai_benchmark.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
