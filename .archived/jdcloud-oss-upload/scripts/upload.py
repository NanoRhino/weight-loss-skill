# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3>=1.34"]
# ///
"""
Upload a local file to JD Cloud OSS and return a presigned URL (15 min expiry).

Usage:
  uv run upload.py <file_path> [--bucket BUCKET] [--prefix PREFIX] [--expires 900]

Environment variables (required):
  JD_OSS_ACCESS_KEY   - JD Cloud access key
  JD_OSS_SECRET_KEY   - JD Cloud secret key
  JD_OSS_ENDPOINT     - OSS endpoint (e.g. https://s3.cn-north-1.jdcloud-oss.com)
  JD_OSS_BUCKET       - Default bucket name (overridden by --bucket)

Prints:
  URL: <presigned-url>
  MEDIA: <presigned-url>   (for OpenClaw auto-attach)
"""

import argparse
import os
import sys
import hashlib
import time
from pathlib import Path

import boto3
from botocore.config import Config


def get_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"Error: {name} environment variable is not set", file=sys.stderr)
        sys.exit(1)
    return val


def upload_and_presign(
    file_path: str,
    bucket: str | None = None,
    prefix: str = "",
    expires: int = 900,
) -> str:
    access_key = get_env("JD_OSS_ACCESS_KEY")
    secret_key = get_env("JD_OSS_SECRET_KEY")
    endpoint = get_env("JD_OSS_ENDPOINT")
    bucket = bucket or os.environ.get("JD_OSS_BUCKET", "").strip()
    if not bucket:
        print("Error: No bucket specified (--bucket or JD_OSS_BUCKET)", file=sys.stderr)
        sys.exit(1)

    path = Path(file_path)
    if not path.is_file():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # Generate unique key: prefix/timestamp-hash-filename
    file_hash = hashlib.md5(path.read_bytes()).hexdigest()[:8]
    ts = int(time.time())
    key = f"{prefix.strip('/')}/{ts}-{file_hash}-{path.name}" if prefix else f"{ts}-{file_hash}-{path.name}"

    # Extract region from endpoint (e.g. s3.cn-north-1.jdcloud-oss.com -> cn-north-1)
    import re
    region_match = re.search(r's3\.([^.]+)\.', endpoint)
    region = region_match.group(1) if region_match else "cn-north-1"

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
        ),
    )

    # Upload
    content_type_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
        ".mp4": "video/mp4", ".svg": "image/svg+xml",
    }
    content_type = content_type_map.get(path.suffix.lower(), "application/octet-stream")

    s3.upload_file(
        str(path), bucket, key,
        ExtraArgs={"ContentType": content_type},
    )

    # Generate presigned URL
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )

    return url


def main():
    parser = argparse.ArgumentParser(description="Upload file to JD Cloud OSS and get presigned URL")
    parser.add_argument("file", help="Path to file to upload")
    parser.add_argument("--bucket", "-b", help="OSS bucket name (or JD_OSS_BUCKET env)")
    parser.add_argument("--prefix", "-p", default="openclaw-uploads", help="Key prefix (default: openclaw-uploads)")
    parser.add_argument("--expires", "-e", type=int, default=900, help="URL expiry in seconds (default: 900 = 15min)")
    args = parser.parse_args()

    url = upload_and_presign(args.file, bucket=args.bucket, prefix=args.prefix, expires=args.expires)
    print(f"URL: {url}")
    print(f"MEDIA: {url}")


if __name__ == "__main__":
    main()
