# Marketing Media System - Easy Setup

## Before you start

Use Windows 11 and an NVIDIA GPU with a working CUDA-capable driver. An RTX-class card with at least 8 GB VRAM is a provisional recommendation, not a benchmarked minimum. The system has been tested on an RTX 5070 Ti with 16 GB VRAM. Setup runs a real generation test on your computer.

Have a reliable internet connection and allow roughly 60 GB of free space for the local foundation and initial working space, plus room for projects. Required model downloads total about 27.3 GB. The wizard shows actual missing download sizes and checks destination free space; the 60 GB figure is planning guidance, not an exact installer footprint. Low RAM and low VRAM can make local generation very slow or fail. Larger video models are optional after setup.

## 1. Install the studio

Clone or download `https://github.com/NOutram123/MarketingMediaSystem`, then extract the source to a permanent location if required. Double-click **Setup.cmd**. Keep its terminal open. Windows may ask you to approve prerequisite installers. The script uses Windows Package Manager for missing Git, Python 3.11, Node.js LTS and FFmpeg; it restores the project's pinned dependencies, creates data folders and creates a blank-key .env only if none exists. Existing settings and projects are preserved.

If winget is unavailable, install **App Installer** from the Microsoft Store and rerun Setup.cmd. If an older Node.js installation is detected, install Node.js 24 LTS from https://nodejs.org/ and reopen setup. Python 3.11 must include the Python launcher (py.exe).

For assistant-led installation, copy the prompt in **SETUP_PROMPT.md**. It points to the official repository and tells the assistant how to run the bootstrap and first-run setup.

For a future repository installation, download scripts/bootstrap.ps1 from the selected release and run it in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -RepositoryUrl https://github.com/NOutram123/MarketingMediaSystem.git -Ref main -InstallDirectory D:\MarketingMediaSystem
```

The installer refuses to clone over an existing folder. To repair an existing installation, run that folder's Setup.cmd. Use **Launch.cmd** for normal daily startup; its browser opens at http://127.0.0.1:8787 once the server is ready. Keep the terminal open while using the studio.

## 2. Install and start the required local foundation

The browser opens **Get your studio ready** on first run. There is no Skip button for the local foundation.

1. Select **Download and install Pinokio**, or visit https://pinokio.co/. Install and open it. Complete its first-run tool installation and choose its home directory on a drive with enough space. NVIDIA driver installation and operating-system prompts are guided steps, not unattended operations.
2. In the studio, select **Install / start ComfyUI**. The studio dispatches the official Pinokio ComfyUI launcher. Watch detailed installation progress in Pinokio. After installation, press the button again if ComfyUI is not yet running. This does not update or reset existing ComfyUI installations.
3. Select **Check readiness**. ComfyUI should report CUDA active. If using an existing installation with a different folder or port, expand **Existing installation / custom paths**, choose its actual models directory and local HTTP address, then save. This field does not move files or change ComfyUI's own model search paths.
4. Select **Download / verify required models**. Files are downloaded from pinned upstream sources and checked with SHA-256. Existing approved files are reused. Incomplete downloads use .partial files and resume when you retry. Conflicting files are preserved and reported for manual review.
5. Restart ComfyUI through Pinokio after adding models, then select **Check readiness** again. Use **Install FFmpeg** only if its check fails. If a newly installed tool is still not detected, close and reopen the studio.

The standard package includes FLUX Schnell FP8 (storyboard images, including encoders/VAE), LTX 2B 0.9.8 distilled FP8 and T5 (draft video), Kokoro and its voices (narration), Whisper tiny.en (captions), and FFmpeg/FFprobe (assembly and validation). Voice/transcription assets stay in the studio's data/models folder; ComfyUI weights go in the displayed ComfyUI models directory.

## 3. Test this computer

Finish other ComfyUI and studio jobs, then select **Run required local test**. Keep the studio running. The test verifies model checksums, creates narration, transcribes it, generates a storyboard image and a short LTX video, and checks FFmpeg assembly. It can take several minutes. Outputs go in data/benchmarks and are non-commercial drafts. No paid API request is made.

**Installed** means a model file is present with an approved size. **Local generation test passed** means the required test actually succeeded for the current file/path configuration. A changed model or path requires another test. Setup cannot be completed with a failed test or a missing local component.

## 4. Add API connections

**OpenAI:** Open https://platform.openai.com/api-keys and create your own API key. Paste it into the masked field and select **Save key**, then **Check API access**. This free check verifies access to the configured model. It does not verify that generation is funded or that every selectable model is accessible. API billing is separate from a ChatGPT subscription. Use the linked API billing page to review funding.

**Higgsfield:** Open the API console at https://cloud.higgsfield.ai/ and create an API credential. Paste the complete **key-id:key-secret** into the masked field and save. The current wizard deliberately reports **configured, unverified**: no supported free authentication or balance endpoint has been verified for this integration. Use the normal estimate/render workflow to check real service access, with its existing separate approval for paid generation. Website subscription credits are not the API balance.

Keys are written to the local ignored .env file and applied to future studio jobs without a manual restart. They are not returned in the UI, stored in browser storage, or included in diagnostic exports. As with any plaintext local .env, anyone who can read your Windows account's files can read it: keep it out of shared folders and source control. Do not paste keys into assistant chats. The wizard waits for running jobs before changing configuration; server environment overrides must be removed before editing the same setting here.

Each missing API has **Skip for now**. Skipping OpenAI disables AI planning/claim suggestions; manual treatment and scene editing remain available. Skipping Higgsfield disables cloud estimates/rendering. These choices persist and can be revisited later. Pinokio and the local stack cannot be skipped.

Select **Open studio** once the local test passes and each API is configured or explicitly skipped. Use **Setup & Diagnostics** at the top of the studio to return at any time.

## Recovery and support

| Problem | What to do |
| --- | --- |
| Pinokio control plane unavailable | Open Pinokio and complete its startup. Its pterm executable can exist while Pinokio is closed. Retry the ComfyUI button. |
| Pinokio runtime access denied | An administrator-installed runtime may require Pinokio to be opened as administrator. Ask your administrator to correct access if appropriate. For fresh installs choose a writable home folder. The studio does not change folder permissions. |
| ComfyUI does not report CUDA | Install the NVIDIA driver and use Pinokio's NVIDIA ComfyUI installation. Restart Windows if requested. Check ComfyUI's terminal. |
| Existing ComfyUI in another directory | Set its real models directory and local address under custom paths. Start that installation in Pinokio. |
| Insufficient space | Free space on the reported drive. For a new installation, choose the intended Pinokio home drive before installing; do not move live model junctions casually. |
| Interrupted download | Relaunch the studio and retry Download / verify required models. Verified destination files remain intact and partial downloads resume. |
| Checksum or existing-file conflict | Move only the named conflicting file aside manually after confirming it is not in use, then retry. Setup never silently replaces it. |
| Local test failed | Check the Pinokio terminal, available RAM/VRAM and free disk. Retry after addressing the cause. The 8 GB recommendation is not a guarantee for every card. |
| Studio closed during local test | The submitted ComfyUI job may continue. Wait for its queue to clear before retrying; interrupted tests are not marked passed. |
| API authentication/access failed | Replace the credential, confirm the selected model is available, and check the provider's API dashboard. A balance of “unavailable” does not mean zero. |
| Port 8787 in use | Use the already-running studio or close its terminal before launching another copy. |

Use **Export diagnostics** for a report without API secrets or model paths. Preserve .env and data (especially projects and the database) in private backups. Do not share .env, backups, virtual environments, model downloads or user projects when publishing the source repository.

## Validation scope

Setup supports the existing Windows/Pinokio installation and provides automated tests for configuration, authentication status, resumable downloads and completion gates. A true fresh Windows installation, Windows elevation prompts, and the 8 GB GPU recommendation need release testing on separate hardware or a clean machine. A successful build is not evidence of those checks.
