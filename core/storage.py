"""Object storage abstraction for exported documents and generated assets.

Supports S3-compatible object storage (AWS S3, Cloudflare R2, MinIO) when
``S3_BUCKET`` is configured and ``boto3`` is installed, with automatic
local-disk fallback for single-node and test environments.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_LOCAL_EXPORT_DIR = Path(os.getenv("LOCAL_EXPORT_DIR", "reports")).resolve()


def _s3_configured() -> bool:
    return bool((os.getenv("S3_BUCKET") or "").strip())


def upload_export_bytes(
    object_key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload export bytes to S3/R2 if configured, else save locally.

    Returns either an ``s3://bucket/key`` URI or the local file path.
    """
    bucket = (os.getenv("S3_BUCKET") or "").strip()
    if bucket:
        try:
            import boto3  # type: ignore

            client = boto3.client(
                "s3",
                endpoint_url=(os.getenv("S3_ENDPOINT_URL") or "").strip() or None,
                region_name=(os.getenv("AWS_REGION") or "auto").strip(),
            )
            client.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=data,
                ContentType=content_type,
            )
            return f"s3://{bucket}/{object_key}"
        except Exception as exc:
            logger.warning("S3 upload failed (%s); falling back to local storage.", exc)

    _LOCAL_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(object_key).name
    dest = _LOCAL_EXPORT_DIR / safe_name
    dest.write_bytes(data)
    return str(dest)


def get_presigned_download_url(object_key: str, expires_in: int = 3600) -> Optional[str]:
    """Generate a time-limited pre-signed URL when S3/R2 is configured."""
    bucket = (os.getenv("S3_BUCKET") or "").strip()
    if not bucket:
        return None
    try:
        import boto3  # type: ignore

        client = boto3.client(
            "s3",
            endpoint_url=(os.getenv("S3_ENDPOINT_URL") or "").strip() or None,
            region_name=(os.getenv("AWS_REGION") or "auto").strip(),
        )
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=expires_in,
        )
    except Exception as exc:
        logger.warning("Failed to generate presigned URL for %s: %s", object_key, exc)
        return None
