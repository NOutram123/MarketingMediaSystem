# Installation and operation

For a fresh machine, use **Setup.cmd** and [EASY_SETUP.md](EASY_SETUP.md). The first-run wizard installs required models, checks the local stack, saves API keys, and requires a real local test. **Launch.cmd** starts the studio on subsequent runs. The workstation paths below describe the original verified installation; new installations discover Pinokio paths automatically or use the wizard's custom paths.

This records the tested workstation setup as of 2026-09-27. Run commands from `C:\Users\nicko\Documents\ChatGPT\MarketingMediaSystem` in PowerShell 7. Pinokio ComfyUI is installed at `C:\pinokio\api\comfy.git\app` and should be started through Pinokio or `C:\pinokio\bin\npm\pterm.cmd`; the project does not replace that installation.

## Configuration

Copy `.env.example` to `.env` if needed. `.env` is ignored by Git. Enter API keys there locally, never in chat or source control. The default `AUTO_APPROVE_BELOW_USD=0` means no paid generation is auto-approved. `LOCAL_DRAFTS_NONCOMMERCIAL=true` records the user's rule for all local draft media; leave it enabled. For Higgsfield, create a new API key in the API console and put the complete copied `key-id:key-secret` credential in `HF_KEY=` in `.env` (the same complete value is also accepted in `HF_API_KEY_ID=`). Restart the studio server and reload the browser page after editing it. Website credits do not fund the separate API balance.

The project virtual environment is `.venv`. To rebuild dependencies, create a Python 3.11 virtual environment, then install the pinned packages from `backend/requirements.lock.txt`. The lock is a pip freeze of the tested environment. The browser UI uses Node 24 and the lockfile in `frontend/`; `npm.cmd ci --no-audit --no-fund` restores its dependencies.

## Start and inspect

1. Start ComfyUI in Pinokio and verify `http://127.0.0.1:8188/system_stats` responds. It binds locally.
2. Run `powershell -ExecutionPolicy Bypass -File scripts/start.ps1`. It restores frontend dependencies if missing, builds the UI, and starts the studio on `http://127.0.0.1:8787`.
3. Open `http://127.0.0.1:8787` for the studio, or `/docs` for API routes.
4. Run `.\.venv\Scripts\python.exe -m pytest -q` for the current automated checks.

The independent practical checks are `python -m scripts.benchmark_comfy_image`, `python -m scripts.benchmark_tts`, `python -m scripts.benchmark_transcription`, and `python -m scripts.benchmark_assembly` using the project venv interpreter. Their outputs and machine audit are under ignored `data/benchmarks/` and `docs/hardware_software_audit.json`.

To make a campaign, create a project in the browser, add any existing character/product/style/location images with descriptions, approve the brief, request a plan, approve its concept, create and approve the storyboard, and attach relevant images to specific scenes. Step 5a makes a local rough cut; local generation uses the reference descriptions and scene guidance. Step 5b sends selected image files to Higgsfield as visual references, or uses text-to-video for scenes with no attached images. An attached image includes its photographed background; the model may reproduce that background and cannot guarantee character consistency. Both outputs remain non-commercial drafts. The paid OpenAI plan request and paid Higgsfield render are separate actions.

For Step 5b, every scene must be 4–30 whole seconds, and the scene durations must sum to the project length. Choose **480p · lower cost** (the default) or **720p · higher detail and cost**, then click **Get Higgsfield estimate**. The app uploads selected reference files and requests pricing for each scene. Seedance 2.5 currently returns an approximate per-second rate rather than a numeric total, so the app calculates an indicative total for the selected resolution before any account discount. Changing resolution requires a fresh estimate; each saved quote keeps its own resolution. Actual charges can vary with output dimensions and billable duration; the displayed total is not a spending cap. Click **Approve approximate estimate** once for the film, then **Generate evaluation · paid API** to submit scenes. The worker saves each request ID and completed clip locally. On restart it resumes known requests; an uncertain submission is held for review instead of being sent again. The review panel lets you enter a request ID found in the API console, or explicitly confirm that no request exists before allowing a fresh submit. A failed scene can be retried explicitly without regenerating completed scenes. Once clips complete, FFmpeg assembles them with the current continuous Kokoro narration and captions at the selected resolution. The output is labelled non-commercial evaluation, not a commercial final.

For a no-fee practical check, `.\.venv\Scripts\python.exe -m scripts.validate_ltx_i2v` makes one image-guided shot, and `.\.venv\Scripts\python.exe -m scripts.create_phase2_demo` creates or reuses the saved five-shot test project. The current demo's completed rough cut can be reviewed in the browser. `scripts.continuous_phase2_demo --apply` is an idempotent check of the current continuous-narration cut; the earlier cuts remain available as history.

The OpenAI test is `.\.venv\Scripts\python.exe -m scripts.validate_openai`; it skips cleanly without `OPENAI_API_KEY`. With a key it makes one minimal paid Responses API request and writes usage to `data/benchmarks/openai_benchmark.json`. Higgsfield credentials likewise belong only in `.env`; no generation or top-up runs from provider status checks.

LTX model installation uses `python -m scripts.install_ltx_models ltx` and `python -m scripts.install_ltx_models t5`. The script verifies SHA-256 and refuses to overwrite a different file. Both models are installed and verified. Run `.\.venv\Scripts\python.exe -m scripts.benchmark_ltx_video` for the safe 512×320 preview or add `--width 768 --height 480` for a 480p-class test. The benchmark checks an empty ComfyUI queue and unloads resident models first. Its output is an `AI-generated DRAFT` MP4 for non-commercial previsualisation only.

## Backups and troubleshooting

The pre-change ComfyUI workflows, settings, custom-node inventory and model-path map are in ignored `backups/comfyui-20260927/`. Pinokio controls the ComfyUI runtime. If the API stops responding, check its Pinokio terminal and queue before restarting. Do not delete the shared model junctions; they point to Pinokio's drive storage. The current ComfyUI health and GPU state can be inspected through `/api/providers`, `/api/resources`, and ComfyUI's `/system_stats`.

The Hugging Face cache under ignored `data/hf_cache/` still contains redundant partial downloads. Automatic approval review blocked recursive cache removal, so it was left intact. The installed ComfyUI model files passed independent SHA-256 checks and are unaffected.
