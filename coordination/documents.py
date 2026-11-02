"""Validation shared by every private document upload."""

import hashlib
from pathlib import Path
import uuid
import zipfile
from django.core.exceptions import ValidationError
from django.conf import settings

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
