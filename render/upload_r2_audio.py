"""Upload final.mp3 to Cloudflare R2 and POST an HMAC-signed success callback.

Env:
  SESSION_ID, CALLBACK_URL, CALLBACK_SECRET
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL

Usage: python upload_r2_audio.py <final.mp3>
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
        print("Usage: upload_r2_audio.py <final.mp3>", file=sys.stderr)
        sys.exit(2)

    final_path = Path(sys.argv[1]).resolve()
    size       = final_path.stat().st_size

    session_id   = os.environ["SESSION_ID"]
    callback_url = os.environ["CALLBACK_URL"]
    secret       = os.environ.get("CALLBACK_SECRET", "")

    account_id = os.environ["R2_ACCOUNT_ID"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]
    bucket     = os.environ["R2_BUCKET"]
    public_base = os.environ["R2_PUBLIC_BASE_URL"].rstrip("/")

    key      = f"audio/{session_id}.mp3"
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
        ExtraArgs={"ContentType": "audio/mpeg"},
    )

    audio_url = f"{public_base}/{key}"

    body = json.dumps({
        "session_id": session_id,
        "status": "succeeded",
        "audio_url": audio_url,
        "size_bytes": size,
        "ts": int(time.time()),
    }).encode()

    headers: dict = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Signature"] = sig

    MAX_ATTEMPTS = 3
    RETRY_DELAY  = 5

    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.post(callback_url, data=body, headers=headers, timeout=30)
            print(f"Callback (attempt {attempt}): {r.status_code} {r.text[:300]}", flush=True)
            r.raise_for_status()
            last_err = None
            break
        except Exception as exc:
            last_err = exc
            print(f"[upload_r2_audio] Callback attempt {attempt} failed: {exc}", flush=True)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY)

    if last_err:
        print(
            f"[upload_r2_audio] WARNING: all callback attempts failed. "
            f"Audio is at {audio_url} — update session manually if needed.",
            flush=True,
        )


if __name__ == "__main__":
    main()
