import hashlib
from datetime import timedelta
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import RateLimit


@transaction.atomic
def consume_limit(identity, limit=10, seconds=900):
    """Database-backed counters shared across workers; no raw identifiers stored."""
    key = hashlib.sha256(identity.encode()).hexdigest()
    now = timezone.now()
    try:
        with transaction.atomic():
            row, _ = RateLimit.objects.select_for_update().get_or_create(
                key=key, defaults={"expires": now + timedelta(seconds=seconds)}
            )
    except IntegrityError:
        row = RateLimit.objects.select_for_update().get(key=key)
    if row.expires <= now:
        row.attempts = 0
        row.expires = now + timedelta(seconds=seconds)
    if row.attempts >= limit:
        return False
    row.attempts += 1
    row.save(update_fields=["attempts", "expires"])
    return True
