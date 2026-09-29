# Project status — 2026-09-27

**Phase 1: passed. Phase 2: passed. Phase 3: pending user review and provider configuration.** See `docs/phase1_report.md`, `docs/phase1_benchmarks.md`, and `docs/phase2_report.md` for evidence.

## Verified foundation

- Audited RTX 5070 Ti (16,303 MiB), 128 GiB RAM class, NVIDIA 616.92 driver, CUDA 13.4 reported by driver, current Pinokio ComfyUI 0.11.1/Manager 3.39.2, Python, Node, Git, FFmpeg, disk and existing models. Evidence: `docs/hardware_software_audit.json`.
- Backed up existing ComfyUI configuration/workflows before additions. ComfyUI localhost API responded and CUDA generated one valid 512×512 FLUX storyboard frame in 29.58 s, with 13,678 MiB observed peak GPU memory.
- Kokoro ONNX generated a valid 2.83 s, 24 kHz narration WAV in 2.72 s. faster-whisper tiny.en transcribed it successfully; first-run model download and transcription took 143.78 s.
- FFmpeg encoded a playable 1280×720 H.264/AAC draft MP4, 2.83 s. The assembly test checks media streams and duration.
- Foundation FastAPI, editable OpenAI profiles, Responses API structured call path, and provider status implemented. Automated tests passed before final documentation update; rerun at phase close.
- Live OpenAI Astra Medium structured Responses API request passed after the user configured the key: 66 input tokens, 56 output tokens, 122 total. The key was neither printed nor committed.
- Installed SHA-256-verified LTX 2B 0.9.8 distilled FP8 and T5 encoder. Produced 49-frame, 3.06-second playable H.264 MP4s at 512×320 (11,631 MiB observed peak VRAM) and 768×480 (13,963 MiB).

## Phase 2 work

- Higgsfield authentication/discovery/estimate: credentials absent, so the provider truthfully reports `NOT_CONFIGURED`. ElevenLabs is optional and also `NOT_CONFIGURED`.
- The React browser studio and localhost FastAPI/SQLite project workflow are operational. Uploads accept existing reference images before planning or at a particular shot; the first attached shot image conditions LTX video. Changes preserve prior media and reset the needed approvals.
- A persistent local job produced a complete 15-second, 1280×720 draft with five storyboard frames, five LTX clips, one continuous Kokoro narration take, captions, and H.264/AAC rough assembly. The current review copy is `data/projects/phase-2-spiceberry-local-demo-f1160f2e/local_drafts/video/rough_cut_v003.mp4`; full evidence is in `docs/phase2_report.md`.
- The persisted single-worker OpenAI planning job records usage; uncertain paid requests stop for review instead of auto-retrying. One user-authorized live call succeeded, producing five 3-second shots and a 35-word continuous script with no claim warnings. The demo video used a separate local fixture plan; the live plan awaits human approval before its own local draft can be generated.
- Local generated media must remain non-commercial drafts. LTX content must be disclosed as AI-generated and commercial final export must reject local drafts.

## User action required

The user may review the 15-second demo and the live OpenAI concept in the browser. Higgsfield keys may be added to the ignored local `.env` if available; no balance purchase is required. The user has already accepted the LTX licence for installation/testing and specified that locally generated drafts are never for commercial use.

The separate user-created SpiceBerry YouTubeAd project timed out during its first paid plan request. [The investigation](docs/spiceberry_timeout_investigation.md) records the evidence. The studio now detects and previews 15/30/45/60-second targets, supports editing project input, and blocks a conflicting approved-claims list. That project targets the 60-second master and awaits revised claims and brief approval. No paid request was repeated; 60-second end-to-end production is not yet validated.

## Next phase

After human review of the draft, proceed to selective premium-shot promotion and final export guards. The downloaded model cache remains in ignored `data/hf_cache/` because automatic approval review blocked recursive cleanup; verified installed model files are intact.
