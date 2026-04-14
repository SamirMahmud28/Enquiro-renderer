# researchgpt-renderer

GitHub Actions renderer for the Enquiro (ResearchGPT) Paper-to-Animation feature.

The backend dispatches a `workflow_dispatch` event with a Manim source file and narration JSON. This repo renders each scene with Manim, generates narration with Kokoro ONNX TTS, merges audio + video with ffmpeg, uploads the final MP4 to Cloudflare R2, and POSTs an HMAC-signed callback to the backend.

## Required repo secrets

| Name | Purpose |
|---|---|
| `ANIMATION_CALLBACK_SECRET` | HMAC-SHA256 secret shared with the backend |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| `R2_BUCKET` | R2 bucket name (e.g. `enquiro-animations`) |
| `R2_PUBLIC_BASE_URL` | Public base URL for the bucket (e.g. `https://pub-xxx.r2.dev`) |

## Inputs (from `workflow_dispatch`)

- `run_id` — ResearchGPT run ID
- `manim_code` — full Python source defining one or more `Scene` subclasses
- `narration` — JSON `{"segments": [{"scene_id", "duration_s", "text"}, ...]}`
- `voice` — Kokoro voice id (default `af_sarah`)
- `callback_url` — backend endpoint for the signed completion POST

## Callback contract

On success the runner POSTs to `callback_url` with header `X-Signature: <hex hmac-sha256(body, ANIMATION_CALLBACK_SECRET)>` and body:

```json
{"run_id":"...","status":"succeeded","video_url":"https://.../animations/<run>.mp4","duration_s":120,"size_bytes":12345678,"ts":1700000000}
```

On failure (any step) a `status: "failed"` callback is sent so the backend can refund the quota.

## Local sanity check

```bash
pip install -r render/requirements.txt
python render/render_scene.py path/to/scene.py out/scenes
python render/generate_audio.py path/to/narration.json out/audio
python render/merge.py out/scenes out/audio out/final.mp4
```
