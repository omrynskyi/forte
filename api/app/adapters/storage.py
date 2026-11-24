"""StorageAdapter: object storage for paystub PDFs (PAY-3). Scope is paystub PDFs only; there are
NO user file uploads (W-4 / DE 4 stay form fields). REP-2 CSV exports may reuse this later.

Implementations:
- S3Storage     boto3 against any S3 API. Locally: MinIO (docker compose, bucket `forte-paystubs`,
                versioning on). Production: AWS S3 with versioning (+ Object Lock / lifecycle for the
                4-year payroll record retention). Only config changes between the two.
- MemoryStorage in-process dict. Used by tests and CI, so CI never needs MinIO.

Presigned URLs are signed for a specific host. The API talks to storage on `s3_endpoint` (inside
docker: http://minio:9000), but URLs handed to the browser are signed against
`s3_public_endpoint` (e.g. http://localhost:9100, or http://<laptop-LAN-IP>:9100 for a phone).
Never hand out a URL for `minio:9000`: the browser can't resolve it and the signature would not
match a rewritten host.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import quote

from app.config import Settings

PAYSTUB_CONTENT_TYPE = "application/pdf"


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    version_id: str | None  # S3 VersionId when bucket versioning is on; None for MemoryStorage
    size: int


@dataclass(frozen=True)
class PresignedUrl:
    url: str
    expires_at: datetime


class StorageError(Exception):
    """Storage unavailable or object missing. Callers decide: retry later, or 503 to the user."""


class StorageAdapter(Protocol):
    def put_object(self, key: str, data: bytes, content_type: str) -> StoredObject: ...

    def get_object(self, key: str) -> bytes:
        """Used by the streaming fallback (GET .../pdf/file) and by integrity checks."""
        ...

    def presigned_get_url(
        self, key: str, *, ttl_seconds: int, download_filename: str | None = None
    ) -> PresignedUrl: ...


def paystub_object_key(company_id: object, paystub_id: object) -> str:
    return f"companies/{company_id}/paystubs/{paystub_id}.pdf"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MemoryStorage:
    """Test double. Keeps every version, like a versioned bucket, so tests can assert that a
    paystub PDF was written exactly once."""

    def __init__(self, bucket: str = "forte-paystubs") -> None:
        self.bucket = bucket
        self.objects: dict[str, list[tuple[bytes, str]]] = {}

    def put_object(self, key: str, data: bytes, content_type: str) -> StoredObject:
        versions = self.objects.setdefault(key, [])
        versions.append((data, content_type))
        return StoredObject(key, _sha256(data), f"v{len(versions)}", len(data))

    def get_object(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError(f"No such object: {key}")
        return self.objects[key][-1][0]

    def presigned_get_url(
        self, key: str, *, ttl_seconds: int, download_filename: str | None = None
    ) -> PresignedUrl:
        if key not in self.objects:
            raise StorageError(f"No such object: {key}")
        expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        return PresignedUrl(
            f"memory://{self.bucket}/{quote(key)}?expires={int(expires.timestamp())}", expires
        )


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        import boto3
        from botocore.config import Config

        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        common = {
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "region_name": settings.s3_region,
            "config": cfg,
        }
        self.bucket = settings.s3_bucket
        # Talks to storage (server-to-server).
        self._client = boto3.client("s3", endpoint_url=settings.s3_endpoint or None, **common)
        # Only signs URLs; never makes a network call. Must be the host the BROWSER uses.
        self._signer = boto3.client(
            "s3",
            endpoint_url=(settings.s3_public_endpoint or settings.s3_endpoint) or None,
            **common,
        )

    def put_object(self, key: str, data: bytes, content_type: str) -> StoredObject:
        from botocore.exceptions import BotoCoreError, ClientError

        digest = _sha256(data)
        try:
            resp = self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={"sha256": digest},
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(str(exc)) from exc
        return StoredObject(key, digest, resp.get("VersionId"), len(data))

    def get_object(self, key: str) -> bytes:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(str(exc)) from exc

    def presigned_get_url(
        self, key: str, *, ttl_seconds: int, download_filename: str | None = None
    ) -> PresignedUrl:
        params: dict[str, str] = {"Bucket": self.bucket, "Key": key}
        if download_filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_filename}"'
        url = self._signer.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=ttl_seconds
        )
        return PresignedUrl(url, datetime.now(UTC) + timedelta(seconds=ttl_seconds))
