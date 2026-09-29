# Phase 2 local draft studio — validation record

Date: 2026-09-27. Status: **Phase 2 passed**.

The browser studio is served on `http://127.0.0.1:8787`. It creates persistent projects with a brand kit and brief, uploads PNG/JPEG/WebP reference images, uses descriptions during planning, and links a reference to a shot at the storyboard stage. The first linked image conditions that shot's LTX image-to-video draft. Changing a link supersedes the affected clip and rough cut, preserves old files, and resets the relevant approvals. Local outputs remain non-commercial AI-generated drafts.

The API has a single-worker restartable local draft job. Each storyboard image and video clip is registered separately with the prompt, model workflow, and lineage. A saved ComfyUI prompt ID lets an interrupted step resume without submitting a second local prompt. Narration, captions, and the rough cut are also registered as versioned assets. The OpenAI planning job persists token usage and will not automatically repeat an uncertain paid call.

## Practical evidence

- A real image-guided LTX test produced a playable 49-frame, 512×288 MP4 lasting 3.06 seconds. See `data/projects/ltx-image-guidance-validation-fa3e747c/local_drafts/video/shot_01.mp4`.
- A non-commercial SpiceBerry demo project produced five distinct FLUX storyboard frames, five image-guided LTX clips, Kokoro narration, faster-whisper captions, and an FFmpeg rough cut. The project ID is `f1160f2e-26e9-493e-a76e-e9ff4df7296c`. The current review cut is `data/projects/phase-2-spiceberry-local-demo-f1160f2e/local_drafts/video/rough_cut_v003.mp4`; versions 1 and 2 are preserved.
- FFprobe confirmed version 3 lasts exactly 15.000 seconds and contains 1280×720 H.264 video, AAC audio, and a `mov_text` subtitle track. Its single continuous narration take lasts about 13 seconds, and matching WebVTT captions run across the five shots. A five-frame contact sheet at `data/projects/phase-2-spiceberry-local-demo-f1160f2e/qa/sequence_contact_sheet.png` shows a coherent product sequence at preview quality.
- The first cut's uninterrupted voiceover ended around 9.6 seconds; the second cut tested shot-aligned lines; the current cut uses a longer, naturally flowing single take requested by the user. Rerunning the draft builder reused completed clips rather than duplicating them.
- Automated Python checks: 20 passed. React/TypeScript production build: passed. Live API health, root UI, reference upload, and job status were checked locally.
- The user authorized one paid OpenAI planning call. It succeeded in project `1df98868-78cf-47e8-853f-73e082492909`: Astra Medium returned five 3-second shots, a 35-word continuous script, the approved claim only, and no claim warnings. Usage was 639 input tokens and 2,334 output tokens (including 516 reasoning), 2,973 total. The usage row persisted in SQLite. The script's local Kokoro preview was 11.2 seconds at default speed and 12.6 seconds with the supported gentle slowdown, fitting the 15-second cut.

The completed rough cut used a local fixture plan, and the separately generated live OpenAI plan remains awaiting human concept and storyboard review. No approval gate was bypassed on that project. Higgsfield and ElevenLabs are not configured; no premium generation was attempted.
