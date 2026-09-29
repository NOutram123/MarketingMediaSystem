"""Conservative extraction of explicit concept, voiceover and timed scenes from notes."""
import re


SCENE_HEADING = re.compile(r'^#{1,3}\s*\d+\.\s*(.+)$')
TIME_RANGE = re.compile(r'(\d{1,3})\s*[–—-]\s*(\d{1,3})\s*(?:sec|seconds|s)\b', re.I)


def clean_line(value):
    return re.sub(r'[*_`#]+', '', value).strip().lstrip('•-> ').strip()


def extract_treatment(notes):
    lines = notes.splitlines()
    concept = ''
    for index, line in enumerate(lines):
        if re.match(r'^#{1,3}\s*(core idea|concept|treatment)\s*$', line.strip(), re.I):
            body = []
            for following in lines[index + 1:]:
                if following.strip() == '---' or re.match(r'^#{1,3}\s+\S', following):
                    break
                if clean_line(following):
                    body.append(clean_line(following))
            concept = '\n'.join(body)[:4000]
            break

    headings = [(index, match.group(1)) for index, line in enumerate(lines)
                if (match := SCENE_HEADING.match(line.strip()))]
    shots = []
    voiceover = []
    warnings = []
    previous_end = 0
    for position, (start_index, title) in enumerate(headings):
        end_index = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        block = lines[start_index + 1:end_index]
        if position + 1 == len(headings):
            for offset, line in enumerate(block):
                if re.match(r'^#{1,3}\s+[A-Za-z]', line.strip()):
                    block = block[:offset]
                    break
        timing = next((match for line in block if (match := TIME_RANGE.search(line))), None)
        if not timing:
            warnings.append(f'No explicit time range found for {title}')
            continue
        start, end = map(int, timing.groups())
        if end <= start or end - start > 30:
            warnings.append(f'Unsupported duration for {title}')
            continue
        if shots and start != previous_end:
            warnings.append(f'Timing gap or overlap before {title}')
        previous_end = end
        visual_lines = []
        narration_lines = []
        in_voiceover = False
        for line in block:
            if TIME_RANGE.search(line) or line.strip() == '---':
                continue
            if re.match(r'^#{1,4}\s*voice\s*over\b|^#{1,4}\s*voiceover\b', line.strip(), re.I):
                in_voiceover = True
                continue
            if in_voiceover and line.lstrip().startswith('>'):
                narration_lines.append(clean_line(line))
            elif not in_voiceover and clean_line(line):
                visual_lines.append(clean_line(line))
        visual = '\n'.join(visual_lines).strip()[:4000] or title
        narration = ' '.join(narration_lines).strip()
        voiceover.extend(narration_lines)
        shots.append({'purpose': clean_line(title)[:300], 'visual': visual,
                      'camera': 'Cinematic framing; refine before approval.',
                      'duration_seconds': end - start, 'narration': narration[:1000],
                      'image_prompt': visual, 'video_prompt': visual,
                      'negative_prompt': ''})
    if not concept and shots:
        concept = 'A film following: ' + '; '.join(shot['purpose'] for shot in shots)
    if not shots:
        warnings.append('No numbered scenes with explicit start–end timings found')
    return {'concept': concept, 'script': ' '.join(voiceover)[:4000],
            'shots': shots, 'warnings': warnings}
