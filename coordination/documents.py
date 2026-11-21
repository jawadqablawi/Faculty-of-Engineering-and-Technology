"""Validation shared by every private document upload."""

import hashlib
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

SIGNATURES = {
    ".pdf": b"%PDF-",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".docx": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",
}


def validate_document(file):
    ext = Path(file.name).suffix.lower() if file else ""
    if not file or file.size > settings.ETCS_MAX_UPLOAD_BYTES or ext not in SIGNATURES:
        raise ValidationError(
            f"ملف غير صالح: PDF، PNG، JPG، DOCX، XLSX حتى {settings.ETCS_MAX_UPLOAD_BYTES // (1024 * 1024)} ميغابايت"
        )
    if not file.read(8).startswith(SIGNATURES[ext]):
        raise ValidationError("محتوى الملف لا يطابق نوعه")
    file.seek(0)
    if ext in {".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(file) as archive:
                infos = archive.infolist()
                if (
                    len(infos) > 1000
                    or sum(i.file_size for i in infos) > 50 * 1024 * 1024
                    or "[Content_Types].xml" not in archive.namelist()
                    or not any(
                        n.startswith("word/" if ext == ".docx" else "xl/")
                        for n in archive.namelist()
                    )
                ):
                    raise ValueError
                if any("vbaproject" in n.lower() for n in archive.namelist()):
                    raise ValueError
        except (zipfile.BadZipFile, ValueError):
            raise ValidationError("مستند Office غير صالح")
        finally:
            file.seek(0)
    checksum = hashlib.sha256()
    for chunk in file.chunks():
        checksum.update(chunk)
    file.seek(0)
    name = Path(file.name).name[:200]
    file.name = f"{uuid.uuid4()}{ext}"
    return name, checksum.hexdigest()


def optimize_image(file):
    """Return a smaller same-format image where safe, retaining PNG transparency."""
    limit = settings.ETCS_UPLOAD_IMAGE_MAX_EDGE
    suffix = Path(file.name).suffix.lower()
    if limit <= 0 or suffix not in {".png", ".jpg", ".jpeg"}:
        return file

    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(file) as original:
            if original.width * original.height > 25_000_000:
                raise ValidationError("أبعاد الصورة كبيرة جدًا")
            if getattr(original, "is_animated", False):
                return file
            image = ImageOps.exif_transpose(original)
            image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
            output = BytesIO()
            if suffix == ".png":
                image.save(output, "PNG", optimize=True)
            else:
                image.convert("RGB").save(output, "JPEG", quality=85, optimize=True)
            return (
                ContentFile(output.getvalue(), name=file.name)
                if output.tell() < file.size
                else file
            )
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as error:
        raise ValidationError("تعذّر قراءة الصورة") from error
    finally:
        file.seek(0)
