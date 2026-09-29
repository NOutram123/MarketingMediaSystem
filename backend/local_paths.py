"""Discover local tools without assuming the original workstation's drive."""
import json
import shutil
from pathlib import Path


def pinokio_home():
    try:
        value = json.loads((Path.home() / '.pinokio/config.json').read_text(encoding='utf-8'))['home']
        path = Path(value)
        return path if path.is_absolute() else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def comfy_models():
    home = pinokio_home()
    return (home / 'api/comfy.git/app/models') if home else Path.home() / 'pinokio/api/comfy.git/app/models'


def media_tool(name):
    found = shutil.which(name)
    if found:
        return found
    link = Path.home() / f'AppData/Local/Microsoft/WinGet/Links/{name}.exe'
    if link.is_file():
        return str(link)
    home = pinokio_home()
    candidate = home / f'bin/ffmpeg-env/Library/bin/{name}.exe' if home else None
    return str(candidate) if candidate and candidate.is_file() else name


def pterm_path():
    home = pinokio_home()
    if home:
        for relative in ('bin/npm/pterm.cmd', 'bin/pterm/pterm.cmd'):
            candidate = home / relative
            if candidate.is_file():
                return candidate
    found = shutil.which('pterm.cmd')
    return Path(found) if found else None


def pinokio_access():
    home = pinokio_home()
    if not home:
        return False, 'Install and open Pinokio, then select a writable home folder.'
    pinned = home / 'bin/miniforge/conda-meta/pinned'
    if pinned.is_file():
        try:
            # Open without modifying content: Windows os.access does not reliably check ACLs.
            with pinned.open('r+b'):
                pass
        except OSError:
            return False, 'Pinokio cannot write its conda runtime. If installed as administrator, launch Pinokio with those permissions, or ask your administrator to repair folder access. No permissions were changed.'
    return True, 'Runtime folder access available; finish initial tool setup inside Pinokio if prompted.'


def whisper_model():
    from .setup_assets import whisper_directory
    local = whisper_directory()
    if (local / 'model.bin').is_file():
        return str(local)
    return 'tiny.en'
