# Changelog

## Phase 2 in progress

- Added SQLite project/shot/asset/job state, independent project folders, versioned asset lineage, editable brand/brief records, and sequential human approval gates.
- Exposed localhost project, approval, storyboard and job-status API routes. Restart and gate-order tests pass.
- Added a persistent single-worker OpenAI plan queue with usage accounting, duplicate submission protection, and review state for interrupted or uncertain paid calls.
- Added the React studio UI with project creation, brand inputs, existing-image uploads, plan/storyboard gates, per-shot references, job status, and rough-cut review.
- Added reference-conditioned LTX draft video, FLUX storyboard images, one continuous Kokoro narration take, faster-whisper captions, and FFmpeg rough-cut assembly. A real five-shot, 15-second non-commercial draft passed practical validation.
- Preserved superseded media versions and made changed shot references invalidate only the affected clip plus assembled rough cut. Added project-level resume manifests for local ComfyUI prompts.
- Switched the rough-cut voiceover to one continuous take after user review; prior audio/cut versions remain saved. One authorized live Astra Medium planning call passed and persisted token usage.

## 2026-09-27 — Phase 1 foundation passed

- Audited machine and existing Pinokio/ComfyUI installation; preserved backups before changes.
- Added isolated Python environment, server-side configuration, loopback FastAPI foundation routes, provider health, and editable OpenAI model profiles.
- Added repeatable local image, TTS, transcription and FFmpeg media benchmarks, plus model download/checksum tooling for LTX.
- Recorded the user's non-commercial-only policy for every locally generated draft asset.
- Validated a live Astra Medium structured Responses API request and recorded token usage.
- Added initial architecture, installation, licence and status documentation.
- Installed SHA-256-verified LTX 2B 0.9.8 distilled FP8 and T5 encoder. Generated and validated 512×320 and 768×480 local draft MP4s. Worked around FFmpeg's inability to decode ComfyUI animated WebP by extracting frames with Pillow before encoding.
