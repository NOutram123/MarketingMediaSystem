"""Read-only checks before a paid planning request."""
import math
from .duration import detect_duration
from .jobs import plan_prompt


def plan_preview(project):
    duration = project.get('target_duration_seconds', 15)
    detected = detect_duration(project['brief'] + '\n' + project.get('treatment_notes', ''))
    inferred, reason = detected if detected is not None else (
        duration, f'No duration stated in the brief; using the project target of {duration} seconds')
    warnings = []
    if detected is not None and inferred != duration:
        warnings.append({'severity': 'warning', 'code': 'duration_mismatch',
                         'message': f'The brief suggests {inferred}s ({reason}), but this project targets {duration}s.'})
    claims = project['brand'].get('approved_claims', [])
    questionable = [claim for claim in claims if any(
        phrase in claim.casefold() for phrase in
        ('would not use', 'not yet', 'without checking', 'not approved', 'do not use'))]
    if questionable:
        warnings.append({'severity': 'blocker', 'code': 'approved_claims_conflict',
                         'message': 'The approved-claims field contains wording marked as not ready for use. '
                                    'Move it out of approved claims and review the remaining claims before planning.'})
    prompt_chars = len(plan_prompt(project))
    if prompt_chars > 8000:
        warnings.append({'severity': 'warning', 'code': 'large_prompt',
                         'message': f'The planning input is long ({prompt_chars:,} characters); the API may take longer.'})
    if project['assets'] and any(asset['kind'] == 'reference_image' for asset in project['assets']):
        warnings.append({'severity': 'info', 'code': 'reference_descriptions_only',
                         'message': 'Planning and local draft prompts use reference descriptions. Select references for each scene; local generation does not directly inspect their image pixels.'})
    return {'target_duration_seconds': duration, 'expected_shots': math.ceil(duration / 6),
            'inferred_duration_seconds': inferred, 'inference_reason': reason,
            'prompt_characters': prompt_chars, 'warnings': warnings}
