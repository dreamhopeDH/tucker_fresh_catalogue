from __future__ import annotations

import io
import json
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class B2ImageStore:
    def __init__(
        self,
        endpoint: str,
        key_id: str,
        application_key: str,
        bucket: str,
        prefix: str = "test",
        client=None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=application_key,
            config=Config(signature_version="s3v4"),
        )

    @property
    def manifest_key(self) -> str:
        return f"{self.prefix}/state/image-manifest.json"

    def download_manifest(self) -> dict:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.manifest_key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return {}
            raise
        return json.loads(response["Body"].read().decode("utf-8"))

    def upload_manifest(self, manifest: dict) -> None:
        payload = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        self.client.upload_fileobj(
            io.BytesIO(payload),
            self.bucket,
            self.manifest_key,
            ExtraArgs={
                "ContentType": "application/json",
                "CacheControl": "no-cache",
            },
        )

    def upload_image(self, local_path: Path, object_key: str) -> None:
        self.client.upload_file(
            str(local_path),
            self.bucket,
            object_key,
            ExtraArgs={
                "ContentType": "image/webp",
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
