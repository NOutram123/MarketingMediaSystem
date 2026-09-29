"""Deterministic, review-only suggestions for scene reference links."""
import re


STOP = {'about', 'against', 'background', 'camera', 'character', 'cinematic', 'close',
        'from', 'image', 'inside', 'location', 'product', 'reference', 'scene', 'shot',
        'style', 'that', 'their', 'this', 'with'}


def words(value):
    return {part for part in re.findall(r"[\w']+", value.casefold()) if len(part) >= 4 and part not in STOP}


def suggest_references(project):
    images = [asset for asset in project['assets'] if asset['kind'] == 'reference_image']
    suggestions = {}
    for shot in project['shots']:
        scene_text = ' '.join(str(shot['data'].get(key, '')) for key in ('purpose', 'visual', 'image_prompt', 'video_prompt'))
        scene_words = words(scene_text)
        matches = []
        for asset in images:
            metadata = asset.get('metadata') or {}
            label = metadata.get('description') or metadata.get('original_name') or ''
            overlap = sorted(scene_words & words(label))
            if overlap:
                matches.append({'asset_id': asset['id'], 'reason': 'Scene mentions ' + ', '.join(overlap[:4])})
        suggestions[shot['id']] = matches
    return suggestions
