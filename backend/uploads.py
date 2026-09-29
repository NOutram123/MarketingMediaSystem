"""Preserve and validate user-supplied reference images."""
import hashlib
from io import BytesIO
from uuid import uuid4

from PIL import Image, UnidentifiedImageError


MAX_REFERENCE_BYTES = 20 * 1024 * 1024
FORMATS = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}
ROLES = {'character', 'product', 'style', 'location', 'other'}


def save_reference(store, project_id, data: bytes, original_name: str, role: str, description: str):
    if role not in ROLES:
        raise ValueError('Unknown reference role')
    if not data or len(data) > MAX_REFERENCE_BYTES:
        raise ValueError('Reference image must be between 1 byte and 20 MB')
    if len(description) > 2000:
        raise ValueError('Reference description is too long')
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid reference image') from exc
    if image_format not in FORMATS or width < 16 or height < 16 or width * height > 40_000_000:
        raise ValueError('Reference must be a PNG, JPEG, or WebP image of 16–40 million pixels')
    project = store.get_project(project_id)
    relative_path = f'source_assets/{uuid4().hex}{FORMATS[image_format]}'
    path = store.project_dir(project) / relative_path
    path.write_bytes(data)
    try:
        return store.add_asset(project_id, 'reference_image', 'user_upload', relative_path,
                               ai_generated=False, commercial_use=False,
                               metadata={'role': role, 'description': description,
                                         'original_name': original_name[:255],
                                         'sha256': hashlib.sha256(data).hexdigest(),
                                         'width': width, 'height': height,
                                         'format': image_format, 'user_supplied': True})
    except Exception:
        path.unlink(missing_ok=True)
        raise
