import logging
from pathlib import Path
from urllib.parse import urlparse

import boto3
import requests

logging.getLogger("botocore").setLevel(logging.INFO)
logging.getLogger("boto3").setLevel(logging.INFO)

class S3Handler:
    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str, region_name: str, default_bucket: str):
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )
        self.default_bucket = default_bucket

    # ---------- Helper ----------
    def _parse_s3_url(self, url_or_key: str) -> tuple[str, str] | None:
        parsed = urlparse(url_or_key)
        if parsed.scheme in ("http", "https"):
            # URL
            if parsed.netloc.startswith("s3"):
                parts = parsed.path.lstrip("/").split("/", 1)
                if len(parts) < 2:
                    raise ValueError(f"Invalid S3 URL: {url_or_key}")
                return parts[0], parts[1]
            if ".s3." in parsed.netloc:
                bucket = parsed.netloc.split(".s3.")[0]
                key = parsed.path.lstrip("/")
                return bucket, key
            return None
        else:
            return self.default_bucket, url_or_key

    def _is_presigned_url(self, url: str) -> bool:
        return "X-Amz-Signature" in url or "X-Amz-Credential" in url

    # ---------- Validation ----------
    def validate(self, url_or_key: str, allowed_content_type: list[str], max_size: int) -> dict:
        if self._is_presigned_url(url_or_key):
            # Validate presigned URL bằng HTTP HEAD
            resp = requests.head(url_or_key)
            if resp.status_code != 200:
                raise ValueError(f"Cannot access presigned URL: {resp.status_code} {resp.text}")

            file_name = Path(urlparse(url_or_key).path).name
            size = int(resp.headers.get("Content-Length", 0))
            ctype = resp.headers.get("Content-Type")

            if not ctype or ctype not in allowed_content_type:
                raise ValueError(f"[{file_name}] Invalid Content-Type: {ctype}, allowed={allowed_content_type}")
            if size > max_size:
                raise ValueError(f"[{file_name}] File too large ({size} bytes > {max_size} bytes)")

            return {"file_name": file_name, "size": size, "content_type": ctype}

        # Validate url with S3 key
        bucket, key = self._parse_s3_url(url_or_key)
        file_name = Path(key).name
        try:
            resp = self.s3.head_object(Bucket=bucket, Key=key)
            size = resp["ContentLength"]
            ctype = resp.get("ContentType")
        except Exception as e:
            raise ValueError(f"[{file_name}] Cannot access s3://{bucket}/{key}: {e}")

        if not ctype or ctype not in allowed_content_type:
            raise ValueError(f"[{file_name}] Invalid Content-Type: {ctype}, allowed={allowed_content_type}")
        if size > max_size:
            raise ValueError(f"[{file_name}] File too large ({size} bytes > {max_size} bytes)")

        return {"file_name": file_name, "size": size, "content_type": ctype}

    # ---------- Download ----------
    def download(self, url_or_key: str, folder_path: Path, file_name: str = None) -> str:
        folder_path.mkdir(parents=True, exist_ok=True)
        url_path = Path(urlparse(url_or_key).path)

        if self._is_presigned_url(url_or_key):
            # Download presigned URL
            if not file_name:
                file_name = url_path.stem

            file_path = folder_path / f"{file_name}{url_path.suffix}"
            try:
                with requests.get(url_or_key, stream=True) as r:
                    r.raise_for_status()
                    with open(file_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
            except Exception as e:
                raise ValueError(f"Download failed for presigned URL: {e}")

            return str(file_path)

        else:
            # Download from S3 key
            bucket, key = self._parse_s3_url(url_or_key)
            if not file_name:
                file_name = Path(key).stem
            file_path = folder_path / f"{file_name}{url_path.suffix}"

            try:
                self.s3.download_file(bucket, key, str(file_path))
            except Exception as e:
                raise ValueError(f"Download failed for s3://{bucket}/{key}: {e}")

            return str(file_path)
