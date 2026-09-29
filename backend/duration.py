"""Resolve a reviewable film duration from the creative brief."""
import re


SUPPORTED_DURATIONS = (15, 30, 45, 60)
_DURATION = r'(15|30|45|60)\s*(?:s|sec(?:ond)?s?)?'
_RANGE = re.compile(rf'{_DURATION}\s*(?:-|–|—|to)\s*{_DURATION}\s*(?:s|sec(?:ond)?s?)?\b', re.I)
_SINGLE = re.compile(rf'\b{_DURATION}\s*(?:-|–|—)?\s*(?:s|sec(?:ond)?s?)\b', re.I)


def detect_duration(brief: str) -> tuple[int, str] | None:
    candidates = []
    for line in brief.splitlines():
        line = re.split(r'\b(?:cutdowns?|cut-downs?|short versions?)\b', line, maxsplit=1, flags=re.I)[0]
        lower = line.casefold()
        if not line.strip():
            continue
        priority = 2 if any(word in lower for word in ('master', 'primary', 'main film', 'hero film')) else 1
        for match in _RANGE.finditer(line):
            candidates.append((priority, int(match.group(2)), match.group(0)))
        for match in _SINGLE.finditer(line):
            if not any(start <= match.start() < end for start, end in
                       ((range_match.start(), range_match.end()) for range_match in _RANGE.finditer(line))):
                candidates.append((priority, int(match.group(1)), match.group(0)))
    if candidates:
        chosen = max(candidates, key=lambda item: (item[0], item[1]))
        return chosen[1], f'Inferred from brief: {chosen[2]}'
    return None


def infer_duration(brief: str) -> tuple[int, str]:
    detected = detect_duration(brief)
    if detected is not None:
        return detected
    return 15, 'No supported duration found in brief; defaulted to 15 seconds'
