"""Local ComfyUI video choices and their required installed weights."""
from .config import Settings

DEFAULT_VIDEO_MODEL = 'ltx-2b'
VIDEO_MODELS = {
    'ltx-2b': {
        'label': 'LTX 2B · fast preview',
        'provider': 'comfyui_ltx_2b',
        'workflow': 'ltx_2b_098_distilled_draft.json',
        'checkpoint': 'ltxv-2b-0.9.8-distilled-fp8.safetensors',
        'required': {'checkpoints/ltxv-2b-0.9.8-distilled-fp8.safetensors': 4461695684,
                     'text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors': 5157348688},
        'width': 512, 'height': 288, 'fps': 16,
    },
    'ltx-13b': {
        'label': 'LTX 13B FP8 · quality trial',
        'provider': 'comfyui_ltx_13b',
        'workflow': 'ltx_2b_098_distilled_draft.json',
        'checkpoint': 'ltxv-13b-0.9.8-distilled-fp8.safetensors',
        'required': {'checkpoints/ltxv-13b-0.9.8-distilled-fp8.safetensors': 15694280140,
                     'text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors': 5157348688},
        'width': 512, 'height': 288, 'fps': 16,
    },
    'wan-5b': {
        'label': 'Wan 2.2 5B · quality trial',
        'provider': 'comfyui_wan_5b',
        'workflow': 'wan_22_5b_i2v_draft.json',
        'checkpoint': 'wan2.2_ti2v_5B_fp16.safetensors',
        'required': {'diffusion_models/wan2.2_ti2v_5B_fp16.safetensors': 9999658848,
                     'text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors': 6735906897,
                     'vae/wan2.2_vae.safetensors': 1409400960},
        'width': 800, 'height': 448, 'fps': 16,
    },
}


def video_model_status(settings: Settings):
    result = []
    for model_id, spec in VIDEO_MODELS.items():
        missing = [name for name, size in spec['required'].items()
                   if not (settings.comfyui_models_dir / name).is_file()
                   or (settings.comfyui_models_dir / name).stat().st_size != size]
        result.append({'id': model_id, 'label': spec['label'], 'installed': not missing,
                       'missing_files': missing})
    return result


def require_video_model(model_id: str, settings: Settings):
    if model_id not in VIDEO_MODELS:
        raise ValueError('Unknown local video model')
    state = next(item for item in video_model_status(settings) if item['id'] == model_id)
    if not state['installed']:
        raise ValueError(f'{state["label"]} is not installed yet: {", ".join(state["missing_files"])}')
    return VIDEO_MODELS[model_id]
