# Assistant installation prompt

Use the repository's `main` branch for the current installation. Use a tagged release for a reproducible installation once releases exist.

Copy this prompt into ChatGPT Work or Codex with access to the target Windows PC:

> Install the Marketing Media System locally from `https://github.com/NOutram123/MarketingMediaSystem.git`, release/branch `main`. If the repository is private, guide me through authenticating with GitHub without asking me to paste a token into chat.
>
> Target Windows 11 with an NVIDIA CUDA GPU. An RTX-class GPU with at least 8 GB VRAM is a provisional recommendation; the tested machine has an RTX 5070 Ti with 16 GB VRAM. Do not claim that every 8 GB GPU is verified. Check available disk space and let me choose the installation location and Pinokio home drive before large downloads.
>
> Inspect the repository's setup instructions, then run its `scripts/bootstrap.ps1` installer. Use `-LocalSource` for already-extracted source or `-RepositoryUrl`, `-Ref`, and `-InstallDirectory` for a new clone. Install supported prerequisites where possible and guide me through Windows prompts where necessary. Preserve existing .env values, projects, model files and Pinokio installations. Do not reset, update or overwrite an existing checkout merely to install it.
>
> Launch the studio and complete its first-run setup: Pinokio, ComfyUI with CUDA, FLUX Schnell FP8, LTX 2B distilled FP8 with its T5 encoder, Kokoro narration and voices, Whisper tiny.en, and FFmpeg/FFprobe. Use the required model manifest and resumable installer; reuse existing verified files. Guide me through installing/opening Pinokio and selecting its home folder if needed. Local setup cannot be skipped.
>
> Run the required local generation test and confirm its actual result. Ask me to enter OpenAI and Higgsfield API credentials directly into the local setup form, never in chat. API connections may be skipped with their feature warnings. Do not submit paid generations or top up accounts during setup. Show authentication, model access and billing availability accurately; never infer remaining credits from a key's presence.
>
> Finish by opening the studio, showing the Easy Setup PDF, and reporting installed components, any skipped APIs, and any remaining failed checks. If execution is unavailable in this chat, give me the repository's standalone Setup.cmd instructions instead of claiming to have installed it.
