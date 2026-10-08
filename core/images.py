import io
import os

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


def optimize_upload(field_file, max_side=1600, quality=82):
    """Downscale, auto-rotate and recompress a freshly uploaded image (saves bandwidth & storage).

    Call from a model's save() before super().save(); does nothing for files already stored.
    """
    if not field_file or getattr(field_file, "_committed", True):
        return
    try:
        field_file.file.seek(0)
        img = Image.open(field_file.file)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
            img = background
        elif img.mode == "L":
            img = img.convert("RGB")
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        base = os.path.splitext(os.path.basename(field_file.name))[0]
        field_file.save(f"{base}.jpg", ContentFile(buf.getvalue()), save=False)
    except Exception:  # never block an upload because of an optimisation problem
        field_file.file.seek(0)
