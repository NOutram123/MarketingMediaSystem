"""Installed English Kokoro voices and their phonemizer languages."""
import numpy as np

from .config import ROOT


VOICE_PACK = ROOT / 'data/models/kokoro/voices-v1.0.bin'
DEFAULT_VOICE = 'af_sarah'
ACCENTS = {'a': 'American', 'b': 'British'}
GENDERS = {'f': 'female', 'm': 'male'}


def english_voices():
    if not VOICE_PACK.is_file():
        return []
    with np.load(VOICE_PACK) as voices:
        names = sorted(name for name in voices.keys() if name[:2] in ('af', 'am', 'bf', 'bm'))
    return [{'id': name,
             'label': f'{name.split("_", 1)[1].capitalize()} · {ACCENTS[name[0]]} {GENDERS[name[1]]}',
             'language': 'en-gb' if name.startswith('b') else 'en-us'} for name in names]


def voice_language(voice_id):
    return next((voice['language'] for voice in english_voices() if voice['id'] == voice_id), None)
