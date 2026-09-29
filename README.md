# Hybrid AI Media Studio

First-time installation: clone or download this repository and double-click **Setup.cmd**, then follow the required local setup wizard. Use **Launch.cmd** thereafter. Windows 11 and NVIDIA CUDA are required; RTX 8 GB is a provisional recommendation, and RTX 5070 Ti 16 GB is the tested configuration.

## Guides

- **[Illustrated User Manual](output/pdf/USER_MANUAL.pdf)** - a 23-page guide to briefs, uploaded references, concepts, scripts, storyboards, local rough cuts and Higgsfield evaluations, with worked examples and annotated screenshots.
- **[Easy Setup PDF](output/pdf/easy-setup.pdf)** - the printable installation and first-run checklist.
- [Easy Setup](EASY_SETUP.md) - the accessible text version of the setup guide.
- [Assistant installation prompt](SETUP_PROMPT.md) - a ready-to-use installation request for ChatGPT Work or Codex.

A local-first marketing media workstation for Windows, with an optional Higgsfield cloud evaluation path.

Local generation produces **non-commercial draft/previsualisation media only**. Every local output is marked `DRAFT` in its manifest; locally generated draft media must not be used commercially or silently promoted into commercial final exports. Premium/final media will require separately approved providers, costs, and human review.

Step 5a creates a local rough cut. Step 5b quotes and, only after explicit approval, renders a **non-commercial Higgsfield evaluation** with Seedance 2.5 scene clips, selected uploaded images as actual cloud references, and one continuous local Kokoro narration. Step 5b is independent of approving a Step 5a rough cut. See [INSTALLATION.md](INSTALLATION.md) for API-key setup and usage.

## What works now

- Pinokio ComfyUI API and CUDA-backed FLUX Schnell storyboard generation.
- Kokoro ONNX narration and faster-whisper transcription.
- FFmpeg rough video assembly and media probing.
- FastAPI foundation service with loopback-only settings, provider status, and resource status.
- Configurable OpenAI Responses API profiles and structured-output code. A live Astra Medium request returned schema-valid data and token usage.
- LTX 2B 0.9.8 distilled FP8 draft video at 512×320 and 768×480, both verified as playable MP4s.
- A pre-render selector offers LTX 2B, LTX 13B FP8, and Wan 2.2 TI2V 5B. The latter two are quality trials pending a live ComfyUI benchmark on this machine; installing weights alone does not establish output quality or memory fit.

The selector checks for all required weight files before it queues a local draft. For resumable installation of the two optional models, run `./.venv/Scripts/python.exe -u scripts/download_video_models.py` from this directory. Re-running that command skips verified files and resumes interrupted Hugging Face transfers. The weights go into the Pinokio ComfyUI model directories; their SHA-256 hashes are checked before use. Restart ComfyUI after installation so it discovers them. Set `COMFYUI_MODELS_DIR` for a different installation path, and use the matching `comfyui_models_dir` setting in `.env`.

See [INSTALLATION.md](INSTALLATION.md) to run the verified components, [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries, and [MODEL_LICENSES.md](MODEL_LICENSES.md) for model restrictions.
