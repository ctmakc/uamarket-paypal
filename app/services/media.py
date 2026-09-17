"""Product photos: validation, EXIF stripping and resized derivatives on a local volume.

An upload is accepted only when all of these hold:
  * the file is at most MEDIA_MAX_UPLOAD_MB (default 15) megabytes;
  * its name ends in .jpg, .jpeg, .png or .webp (an .svg, .html or anything else is refused
    before it is opened);
  * Pillow opens it and reports JPEG, PNG or WEBP, whatever the name says;
  * it has at most 50 megapixels and at least 200 px on its short side.

Nothing of the original file is kept. It is decoded, turned upright by its EXIF
orientation, flattened onto the linen colour when it has transparency, and written again
as WebP at up to three widths (480, 960, 1600 px, never wider than the source). The writes
carry no EXIF, so camera serial numbers and GPS positions never reach the shop.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

WIDTHS = (480, 960, 1600)
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 50_000_000
MIN_SIDE = 200
LINEN_BLEACHED = (232, 227, 214)


class MediaError(ValueError):
    def __init__(self, code: str, message: str, message_uk: str):
        super().__init__(message)
        self.code = code
        self.message_uk = message_uk

    def as_detail(self) -> dict:
        return {"code": self.code, "message": str(self), "message_uk": self.message_uk}


def media_root() -> Path:
    return Path(os.getenv("MEDIA_ROOT", "./media")).resolve()


def max_upload_bytes() -> int:
    try:
        mb = float((os.getenv("MEDIA_MAX_UPLOAD_MB") or "15").strip())
    except ValueError:
        mb = 15.0
    return int(max(1.0, min(mb, 50.0)) * 1024 * 1024)


@dataclass
class ProcessedImage:
    width: int
    height: int
    widths: list[int]
    files: dict[int, bytes]


def check_name(filename: str) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise MediaError(
            "type",
            f"“{filename}” is not a photo the shop accepts. Use a JPEG, PNG or WebP file.",
            f"«{filename}» — не той тип фото. Завантажте JPEG, PNG або WebP.",
        )


def check_size(size: int) -> None:
    limit = max_upload_bytes()
    if size > limit:
        raise MediaError(
            "too_large",
            f"The file is {size / 1048576:.1f} MB; the limit is {limit // 1048576} MB. Export a smaller JPEG and try again.",
            f"Файл важить {size / 1048576:.1f} МБ; межа — {limit // 1048576} МБ. Збережіть менший JPEG і спробуйте ще раз.",
        )


def process(data: bytes, filename: str) -> ProcessedImage:
    check_name(filename)
    check_size(len(data))
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise MediaError("type", "This file is not a JPEG, PNG or WebP photo.", "Цей файл не є фото JPEG, PNG чи WebP.")
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                ground = Image.new("RGB", rgba.size, LINEN_BLEACHED)
                ground.paste(rgba, mask=rgba.getchannel("A"))
                img = ground
            else:
                img = img.convert("RGB")
    except MediaError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        raise MediaError(
            "unreadable",
            f"The photo could not be read ({type(exc).__name__}). Save it again as JPEG and retry.",
            f"Фото не вдалося прочитати ({type(exc).__name__}). Збережіть його як JPEG і спробуйте ще раз.",
        )
    width, height = img.size
    if min(width, height) < MIN_SIDE:
        raise MediaError(
            "too_small",
            f"The photo is {width}×{height} px; the short side needs at least {MIN_SIDE} px.",
            f"Фото {width}×{height} px; коротша сторона має бути щонайменше {MIN_SIDE} px.",
        )
    widths = sorted({w for w in WIDTHS if w <= width} or {width})
    files: dict[int, bytes] = {}
    for w in widths:
        h = max(1, round(height * w / width))
        copy = img if w == width else img.resize((w, h), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        copy.save(out, "WEBP", quality=82, method=4)
        files[w] = out.getvalue()
    return ProcessedImage(width=width, height=height, widths=widths, files=files)


def product_dir(product_id: str) -> Path:
    return media_root() / "products" / product_id


def write_named(subdir: str, stem: str, processed: ProcessedImage) -> None:
    """Write the derivatives as MEDIA_ROOT/<subdir>/<stem>-<width>.webp.

    Product photos are the usual case (`write` below). Maker pictures use the same
    volume and the same /media route under `makers/`, so a shop that serves photos
    serves maker pictures without a second storage path or a second URL scheme.
    """
    folder = media_root() / subdir
    folder.mkdir(parents=True, exist_ok=True)
    for w, blob in processed.files.items():
        tmp = folder / f".{stem}-{w}.webp.tmp"
        tmp.write_bytes(blob)
        tmp.replace(folder / f"{stem}-{w}.webp")


def write(product_id: str, image_id: str, processed: ProcessedImage) -> None:
    write_named(f"products/{product_id}", image_id, processed)


def remove(product_id: str, image_id: str) -> None:
    folder = product_dir(product_id)
    for path in folder.glob(f"{image_id}-*.webp"):
        try:
            path.unlink()
        except OSError:
            pass


def resolve(relative: str) -> Path | None:
    """A served file under MEDIA_ROOT, or None for anything outside it or missing."""
    root = media_root()
    target = (root / relative).resolve()
    if root not in target.parents or not target.is_file() or target.suffix != ".webp":
        return None
    return target
