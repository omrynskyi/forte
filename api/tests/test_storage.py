"""StorageAdapter (D16). Unit tests use MemoryStorage. The MinIO round-trip test runs only when a
local MinIO is reachable (`make up`); CI skips it."""

import os
import uuid
from urllib.parse import urlparse

import httpx
import pytest

from app.adapters.storage import MemoryStorage, S3Storage, StorageError, paystub_object_key
from app.config import Settings


def test_memory_storage_keeps_versions():
    s = MemoryStorage()
    key = paystub_object_key("c1", "p1")
    first = s.put_object(key, b"%PDF-1", "application/pdf")
    second = s.put_object(key, b"%PDF-2", "application/pdf")
    assert (first.version_id, second.version_id) == ("v1", "v2")
    assert s.get_object(key) == b"%PDF-2"
    assert len(s.objects[key]) == 2
    with pytest.raises(StorageError):
        s.presigned_get_url("missing.pdf", ttl_seconds=60)


def test_presigned_url_is_signed_for_public_endpoint_not_internal_host():
    """The API talks to http://minio:9000, but the browser must get a URL for the public host."""
    settings = Settings(
        s3_endpoint="http://minio:9000",
        s3_public_endpoint="http://localhost:9100",
        storage_backend="s3",
    )
    url = S3Storage(settings).presigned_get_url("companies/c/paystubs/p.pdf", ttl_seconds=60).url
    parsed = urlparse(url)
    assert parsed.netloc == "localhost:9100"
    assert "minio" not in url
    assert "X-Amz-Expires=60" in url


def _minio_up() -> bool:
    try:
        return httpx.get("http://localhost:9100/minio/health/live", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(os.environ.get("CI") == "true" or not _minio_up(), reason="needs local MinIO")
def test_minio_round_trip_versioned_and_presigned():
    settings = Settings(storage_backend="s3")
    store = S3Storage(settings)
    key = f"test/{uuid.uuid4()}.pdf"
    stored = store.put_object(key, b"%PDF-1.4 test", "application/pdf")
    assert stored.version_id, "bucket versioning must be enabled (make up runs minio-init)"
    assert store.get_object(key) == b"%PDF-1.4 test"
    link = store.presigned_get_url(key, ttl_seconds=60, download_filename="stub.pdf")
    r = httpx.get(link.url, timeout=5)
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test"
