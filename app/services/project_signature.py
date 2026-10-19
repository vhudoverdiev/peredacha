"""Validate and normalize per-project signature images before storing them."""
import base64
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


def normalize_signature(upload) -> str:
    raw = upload.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("Размер подписи не должен превышать 5 МБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in {"PNG", "JPEG"} or source.width * source.height > 16_000_000:
                    raise ValueError("Загрузите PNG или JPEG не более 16 мегапикселей.")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGBA")
                image.thumbnail((1000, 500), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format="PNG")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Не удалось прочитать изображение подписи. Загрузите корректный PNG или JPEG.") from exc
    return base64.b64encode(output.getvalue()).decode("ascii")
