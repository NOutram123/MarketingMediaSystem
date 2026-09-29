"""Resume verified ComfyUI model downloads after interruption.

Run with the project's Python environment. Files are downloaded by huggingface_hub
into its resumable local cache, checked against the publisher's SHA-256, and only
then moved into ComfyUI's model directories.
"""
import hashlib
import os
from pathlib import Path

from huggingface_hub import hf_hub_download


MODELS = Path(os.environ.get('COMFYUI_MODELS_DIR', r'C:\pinokio\api\comfy.git\app\models'))
SPECS = (
    ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
     'split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors',
     'diffusion_models/wan2.2_ti2v_5B_fp16.safetensors',
     '456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e'),
    ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
     'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
     'text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
     'c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68'),
    ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
     'split_files/vae/wan2.2_vae.safetensors',
     'vae/wan2.2_vae.safetensors',
     'e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156'),
    ('Lightricks/LTX-Video', 'ltxv-13b-0.9.8-distilled-fp8.safetensors',
     'checkpoints/ltxv-13b-0.9.8-distilled-fp8.safetensors',
     '111a3d07baa17f520e98b571e7916139ae0865c9a24b7534529d6b9e74264db3'),
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if not MODELS.is_dir():
        raise SystemExit(f'ComfyUI models directory is missing: {MODELS}')
    for repo, filename, destination, expected_sha in SPECS:
        target = MODELS / destination
        if target.is_file() and sha256(target) == expected_sha:
            print(f'Already verified: {target}', flush=True)
            continue
        print(f'Downloading: {repo}/{filename}', flush=True)
        source = Path(hf_hub_download(repo, filename, local_dir=MODELS))
        if sha256(source) != expected_sha:
            raise RuntimeError(f'SHA-256 mismatch: {source}')
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
        print(f'Installed and verified: {target}', flush=True)


if __name__ == '__main__':
    main()
