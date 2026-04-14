"""Upload final.mp4 to Cloudflare R2 and POST an HMAC-signed success callback.

Env:
  RUN_ID, CALLBACK_URL, CALLBACK_SECRET
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL

Usage: python upload_r2.py <final.mp4>
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import boto3
import requests


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: upload_r2.py <final.mp4>", file=sys.stderr)
        sys.exit(2)

    final_path = Path(sys.argv[1]).resolve()
    size = final_path.stat().st_size

    run_id = os.environ["RUN_ID"]
    callback_url = os.environ["CALLBACK_URL"]
    secret = os.environ["CALLBACK_SECRET"]

    account_id = os.environ["R2_ACCOUNT_ID"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]
    bucket = os.environ["R2_BUCKET"]
    public_base = os.environ["R2_PUBLIC_BASE_URL"].rstrip("/")

    key = f"animations/{run_id}.mp4"
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    print(f">> uploading {final_path} ({size} bytes) -> r2://{bucket}/{key}", flush=True)
    s3.upload_file(
        str(final_path), bucket, key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    video_url = f"{public_base}/{key}"

    # probe duration (ffprobe is available on the runner)
    import subprocess
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(final_path),
        ])
        duration_s = int(float(json.loads(out)["format"]["duration"]))
    except Exception:
        duration_s = 0

    body = json.dumps({
        "run_id": run_id,
        "status": "succeeded",
        "video_url": video_url,
        "duration_s": duration_s,
        "size_bytes": size,
        "ts": int(time.time()),
    }).encode()

    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = requests.post(
        callback_url,
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
        timeout=30,
    )
    print(f"Callback: {r.status_code} {r.text[:300]}", flush=True)
    r.raise_for_status()


if __name__ == "__main__":
    main()
