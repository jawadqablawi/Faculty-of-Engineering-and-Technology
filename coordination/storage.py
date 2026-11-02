"""Private, persistent file storage in the same PostgreSQL database as records.

Used on serverless hosting without a persistent disk. Public file URLs are never
created; all reads continue through the existing permission-checked endpoints.
"""

from io import BytesIO
from pathlib import PurePosixPath
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.storage import Storage
from django.db import connection
from django.utils.deconstruct import deconstructible
from .models import StoredDocument


@deconstructible
class DatabaseStorage(Storage):
    def _open(self, name, mode="rb"):
        if mode not in ["r", "rb"]:
            raise ValueError("Database files are immutable; upload a new version")
        try:
            record = StoredDocument.objects.get(name=name)
        except StoredDocument.DoesNotExist:
            raise FileNotFoundError(name)
        return File(BytesIO(bytes(record.data)), name=name)

    def _save(self, name, content):
        original = PurePosixPath(name)
        name = str(original.parent / (uuid.uuid4().hex + original.suffix.lower()))
        maximum = settings.ETCS_MAX_UPLOAD_BYTES
        if content.size > maximum:
            raise ValidationError("الملف أكبر من الحد المسموح")
        data = content.read(maximum + 1)
        if len(data) > maximum:
            raise ValidationError("الملف أكبر من الحد المسموح")
        actor = None
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT NULLIF(current_setting('etcs.user_id',true),'')::bigint"
                )
                actor = cursor.fetchone()[0]
        StoredDocument.objects.create(
            name=name, data=data, size=len(data), uploader_id=actor
        )
        return name

    def exists(self, name):
        return StoredDocument.objects.filter(name=name).exists()

    def delete(self, name):
        StoredDocument.objects.filter(name=name).delete()

    def size(self, name):
        return StoredDocument.objects.values_list("size", flat=True).get(name=name)

    def url(self, name):
        raise ValueError("Private documents do not have public URLs")
