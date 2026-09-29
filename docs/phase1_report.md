# Phase 1 completion report — 2026-09-27

## Completed

Machine and Pinokio/ComfyUI audit, pre-change backup, foundation repository, isolated Python dependencies, localhost FastAPI service, editable OpenAI model profiles, provider status, model licence register, and repeatable media benchmarks. LTX and T5 models were checksum verified before installation.

## Tests passed

- GPU detection and CUDA-backed ComfyUI API; local FLUX image generation.
- LTX 49-frame, 3.06-second draft MP4s at 512×320 and 768×480; 11,631 and 13,963 MiB observed peak VRAM respectively. MP4 codec, dimensions, frame count, duration, metadata and changing frames verified.
- Kokoro narration, faster-whisper transcription, FFmpeg H.264/AAC assembly and media probing.
- Live OpenAI `gpt-6-astra` Medium structured Responses API request, 122 total tokens with usage captured.
- Higgsfield and ElevenLabs return `NOT_CONFIGURED` cleanly; this is the brief's permitted Higgsfield Phase 1 alternative. Server configuration loads, remains local, and 10 automated tests pass.
- Licences and benchmark evidence are documented in `MODEL_LICENSES.md` and `docs/phase1_benchmarks.md`.

## Tests failed

Direct FFmpeg decode of ComfyUI's animated WebP failed. The tested conversion path extracts its 49 frames with Pillow and encodes them with FFmpeg. No Phase 1 acceptance item remains failed.

## Issues and fallbacks

The local LTX clips show motion and composition but have stylised, high-contrast visuals. This is acceptable for non-commercial previsualisation and is not final render quality. The 768×480 option uses most of the 16 GB card; 512×320 is the lower-memory fallback. Higgsfield live validation is unavailable without credentials; no funding is required for current local mode. Automatic approval review blocked recursive removal of redundant download cache; installed model files remain verified.

## User action required

None to start Phase 2 local development. Optional Higgsfield and ElevenLabs credentials can be added server-side to `.env` later. Premium generation would require a separate cost approval.

## Next phase

Build the browser UI, SQLite project and asset lineage, local generation jobs, brand kit and claim controls, approval gates, captions, and an approximately 15-second local draft advert. Do not use locally generated drafts commercially.
