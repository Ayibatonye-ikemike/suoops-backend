from __future__ import annotations

import logging
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class S3Client:
    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        presign_ttl: int | None = None,
    ) -> None:
        """Initialize S3 client.

        Backward-compatible with tests that pass explicit endpoint/access/bucket kwargs.
        Falls back to settings when parameters are omitted.
        """
        self.bucket = bucket or settings.S3_BUCKET
        self._explicit_endpoint = endpoint or settings.S3_ENDPOINT or None
        self._access_key = access_key or settings.S3_ACCESS_KEY or None
        self._secret_key = secret_key or settings.S3_SECRET_KEY or None
        self._presign_ttl = presign_ttl or settings.S3_PRESIGN_TTL
        self._client = self._initialize_client()
        self._filesystem_root: Path | None = None

    def upload_bytes(self, data: bytes, key: str, content_type: str = "application/pdf") -> str:
        if self._client is not None:
            try:
                self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
                url = self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=self._presign_ttl,
                )
                logger.debug("Uploaded %s to bucket %s", key, self.bucket)
                return url
            except (BotoCoreError, ClientError) as exc:
                logger.exception("S3 upload failed for %s: %s", key, exc)
                if settings.ENV.lower() == "prod":
                    raise RuntimeError("Failed to upload PDF to object storage") from exc
        local_url = self._write_to_filesystem(data, key)
        logger.debug("Stored %s locally at %s", key, local_url)
        return local_url

    def _initialize_client(self):
        try:
            session = boto3.session.Session(
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
            )
            endpoint = self._explicit_endpoint
            region = getattr(settings, "S3_REGION", "us-east-1")
            
            # For AWS S3, don't set endpoint_url (let boto3 use default AWS endpoints)
            client_kwargs = {
                "service_name": "s3",
                "region_name": region,
                "config": Config(signature_version="s3v4"),
            }
            
            # Only set endpoint_url for non-AWS S3-compatible services
            if endpoint:
                client_kwargs["endpoint_url"] = endpoint
            
            client = session.client(**client_kwargs)
            # Ensure bucket exists; create if missing in non-prod setups
            try:
                client.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code in {"404", "NoSuchBucket"} and settings.ENV.lower() != "prod":
                    logger.info("Bucket %s missing; attempting creation", self.bucket)
                    create_kwargs = {"Bucket": self.bucket}
                    if endpoint and "localhost" in endpoint:
                        create_kwargs["CreateBucketConfiguration"] = {
                            "LocationConstraint": "us-east-1",
                        }
                    client.create_bucket(**create_kwargs)
                else:
                    raise
            return client
        except (BotoCoreError, ClientError) as exc:
            logger.warning("Falling back to filesystem storage for bucket %s: %s", self.bucket, exc)
            return None

    def _write_to_filesystem(self, data: bytes, key: str) -> str:
        base = self._ensure_filesystem_root()
        target = base / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target.resolve().as_uri()

    def _ensure_filesystem_root(self) -> Path:
        if self._filesystem_root is None:
            root = Path("storage") / self.bucket
            root.mkdir(parents=True, exist_ok=True)
            self._filesystem_root = root
            logger.info("Using filesystem storage fallback at %s", root)
        return self._filesystem_root


# Singleton instance for application use
s3_client = S3Client()
