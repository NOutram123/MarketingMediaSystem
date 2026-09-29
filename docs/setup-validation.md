# Setup validation - 29 September 2026

The implementation adds a Windows bootstrap, first-run local readiness gate, resumable pinned model downloads, local generation test, optional API setup, diagnostics, and a generated PDF guide. Existing application changes in the workspace were preserved.

## Verified

- Python regression and setup tests: 58 passed (43 existing tests and 15 setup tests).
- TypeScript compilation and Vite production build succeed.
- PowerShell scripts parse without syntax errors. The unpublished repository placeholder fails before installing prerequisites.
- All nine required local model/asset files match their approved SHA-256 digests, including the existing Kokoro variant.
- Browser renders the wizard, masked credential fields, required local checks, disabled completion gate and diagnostics controls. Keyboard readiness-check interaction works.
- Download tests cover supported/ignored Range requests, interrupted partial-file reuse, incorrect ranges/checksums, existing-file preservation and insufficient storage.
- Configuration tests cover completion refusal before local testing, inability to skip the local stack, API skip persistence, protected credential writes, no credential reflection in validation errors, and safe provider status reporting.
- Whisper cache reuse requires one complete snapshot instead of mixing files across directories.
- The four-page PDF is generated from EASY_SETUP.md and visually checked after rendering through Poppler.

## Live limitation discovered

Pinokio 8.2.0 on this workstation does not finish initialising when launched from this non-elevated session. Its log reports `EPERM` opening its conda-meta/pinned file. That existing file is owned by Administrators and grants normal users read/execute access only. The Pinokio UI reports that its backend is still warming up; ComfyUI's CUDA API therefore remains unavailable.

No permissions or model files were changed to work around this. The wizard now surfaces the runtime access issue. An administrator-installed Pinokio runtime may need Pinokio started with its original elevated permissions, or its administrator to repair folder access. If an elevated ComfyUI is already serving CUDA, the normal-user studio can use it.

The new end-to-end local generation test has **not** passed in this session. Its completion marker was not manufactured. Model presence, old benchmark files and passing unit tests do not substitute for that test.

## Release checks still needed

- Run Setup.cmd on a genuinely fresh Windows 11 PC, including winget, Windows installer/UAC prompts, Pinokio's first-run tool setup and the full model downloads.
- Test a clean repository installation from `https://github.com/NOutram123/MarketingMediaSystem.git`, including private-repository authentication where required.
- Run the required local generation test on the supported hardware after Pinokio starts correctly.
- Benchmark the proposed 8 GB RTX class before describing it as a verified minimum. The established working configuration is RTX 5070 Ti 16 GB.
- API setup makes no paid generation calls. Higgsfield authentication/balance remain explicitly unverified; OpenAI model-access checks do not certify available credit.

## Maintainer notes

The model manifest is config/setup-models.json. Update pinned source revisions and hashes together, then test the complete workflows. Python dependencies and frontend packages remain controlled by their existing lock files; the upstream Pinokio ComfyUI launcher itself can evolve and requires release testing.

Regenerate the guide with scripts/build_setup_guide.py using Python with ReportLab installed. That authoring dependency is not needed to install or run the studio. User data, .env, setup state, partial downloads and local helper logs are excluded from source control.
