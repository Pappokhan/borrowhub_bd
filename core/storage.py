from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """Files that must never be public (e.g. NID photos). Served only to staff via /private/<path>."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", str(settings.PRIVATE_MEDIA_ROOT))
        kwargs.setdefault("base_url", "/private/")
        super().__init__(*args, **kwargs)


def private_storage():
    return PrivateMediaStorage()
