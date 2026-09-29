from io import BytesIO

import pytest
from PIL import Image

from backend.local_media import validate_animated_preview


def test_static_webp_can_coalesce_requested_frames():
    image = Image.new('RGB', (64, 32), 'red')
    buffer = BytesIO()
    image.save(buffer, 'WEBP', save_all=True, append_images=[image.copy() for _ in range(5)],
               duration=62, lossless=False)
    buffer.seek(0)
    with Image.open(buffer) as preview:
        assert preview.n_frames < 6
        validate_animated_preview(preview, (64, 32), 'ltx-13b')
        with pytest.raises(RuntimeError, match='size='):
            validate_animated_preview(preview, (32, 32), 'ltx-13b')
