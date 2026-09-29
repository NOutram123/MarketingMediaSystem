# Phase 1 practical benchmarks — 2026-09-27

Machine: RTX 5070 Ti (16,303 MiB reported VRAM), 128 GiB system RAM class, NVIDIA driver 616.92 / CUDA UMD 13.4. Tests run on the actual workstation. Outputs and machine-readable results are in ignored `data/benchmarks/`; the audit is `docs/hardware_software_audit.json`.

| Check | Actual result | Status |
| --- | --- | --- |
| ComfyUI FLUX.1 Schnell FP8, 512×512 | First cold generation took 29.58 s with 13,678 MiB observed peak GPU memory. A later new-seed run with model resident took 2.23 s, output 333,682-byte PNG, peak 13,781 MiB including already loaded models. | PASS |
| Kokoro ONNX v1.0 narration | 2.83 s / 24 kHz WAV; latest generation took 1.75 s. | PASS |
| faster-whisper tiny.en transcription | Timed English segment from 0.0–2.56 s; first run including model download took 143.78 s, warm run 1.27 s. | PASS |
| FFmpeg assembly | 2.83 s, 1280×720 H.264/AAC playable MP4, encoded in 0.30 s on latest run. | PASS |
| LTX 2B 0.9.8 distilled FP8, 512×320 | 49 frames / 3.06 s at 16 fps, ComfyUI execution 6.16 s, generation plus conversion 9.34 s, observed peak VRAM 11,631 MiB, peak system RAM used 31.58 GB. Playable H.264 MP4. | PASS |
| LTX 2B 0.9.8 distilled FP8, 768×480 | 49 frames / 3.06 s at 16 fps, ComfyUI execution 8.54 s, generation plus conversion 12.19 s, observed peak VRAM 13,963 MiB, peak system RAM used 31.91 GB. Playable H.264 MP4. | PASS |
| OpenAI Responses API | Live `gpt-6-astra` Medium structured request passed: 66 input tokens, 56 output tokens (33 reasoning), 122 total. Output matched the schema. | PASS |
| Higgsfield | Client reports `NOT_CONFIGURED` without crashing; authentication/discovery/estimate require credentials. No paid generation attempted. | NOT CONFIGURED |
| ElevenLabs | Optional client reports `NOT_CONFIGURED` without crashing. | NOT CONFIGURED |

Every generated local image/audio/video benchmark has `DRAFT` and `commercial_use=false` in its result manifest. Video files also carry draft metadata. These results do not establish permission for commercial use; the user's rule is non-commercial local drafts only.

The FastAPI server was started on `127.0.0.1:8787` and its `/api/health`, `/api/providers`, `/api/resources`, and OpenAPI JSON endpoints responded. Ten automated tests passed. Both LTX clips have substantial frame-to-frame change and show camera motion, but the visuals are stylised and high-contrast; they are useful for timing and composition, not premium deliverables. FFmpeg could not decode ComfyUI's animated WebP directly, so the verified conversion uses Pillow to extract frames and FFmpeg to encode the MP4. Phase 1 acceptance passed under the brief's explicit `NOT_CONFIGURED` alternative for Higgsfield.
