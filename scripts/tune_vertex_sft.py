"""Create and monitor a Vertex AI supervised fine-tuning job for the Smart Classroom assistant.

Fine-tuning is no longer available through the Gemini API with an API key, so tuning runs on
Vertex AI (`projects.locations.tuningJobs`) with OAuth credentials and datasets on Cloud Storage.

Prerequisites:
  1. python scripts/convert_to_vertex_sft.py
  2. gcloud auth application-default login   (or export GOOGLE_ACCESS_TOKEN=...)
  3. a Cloud Storage bucket in the same region family as the tuning job

Typical run:
    python scripts/tune_vertex_sft.py \
        --project my-gcp-project \
        --bucket gs://my-bucket/smart-classroom/tuning

The job resource, tuned model and serving endpoint are written to
training_data/tuning_job.json so the backend can be pointed at the result.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
VERTEX_DIR = ROOT / "training_data" / "vertex"
RESULT_PATH = ROOT / "training_data" / "tuning_job.json"

# Regions where Gemini supervised fine-tuning jobs can run.
TUNING_REGIONS = ("us-central1", "europe-west4")
# Base models documented as supporting supervised fine-tuning.
TUNABLE_BASE_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
)
ADAPTER_SIZES = {1: "ADAPTER_SIZE_ONE", 2: "ADAPTER_SIZE_TWO", 4: "ADAPTER_SIZE_FOUR", 8: "ADAPTER_SIZE_EIGHT", 16: "ADAPTER_SIZE_SIXTEEN"}
# Vertex documents a lower maximum adapter size for Gemini 2.5 Pro.
ALLOWED_ADAPTER_SIZES = {
    "gemini-2.5-pro": frozenset({1, 2, 4, 8}),
    **{model: frozenset(ADAPTER_SIZES) for model in TUNABLE_BASE_MODELS if model != "gemini-2.5-pro"},
}
TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


def access_token() -> str:
    """Bearer token for Vertex AI: explicit env var first, then the gcloud CLI."""
    token = os.environ.get("GOOGLE_ACCESS_TOKEN", "").strip()
    if token:
        return token
    gcloud = shutil.which("gcloud")
    if not gcloud:
        raise SystemExit(
            "ไม่พบ credential — ตั้งค่า GOOGLE_ACCESS_TOKEN หรือติดตั้ง gcloud "
            "แล้วรัน `gcloud auth application-default login`"
        )
    result = subprocess.run(
        [gcloud, "auth", "print-access-token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(f"gcloud auth print-access-token ล้มเหลว: {result.stderr.strip()}")
    return result.stdout.strip()


def upload_datasets(bucket_prefix: str) -> tuple[str, str]:
    """Copy the converted JSONL files to Cloud Storage with gcloud storage."""
    gcloud = shutil.which("gcloud")
    if not gcloud:
        raise SystemExit("ต้องมี gcloud CLI เพื่ออัปโหลดไฟล์ หรือส่ง --train-uri/--validation-uri เอง")
    prefix = bucket_prefix.rstrip("/")
    if not prefix.startswith("gs://"):
        raise SystemExit("--bucket ต้องเริ่มด้วย gs://")

    uris: list[str] = []
    for name in ("train_sft.jsonl", "validation_sft.jsonl"):
        local = VERTEX_DIR / name
        if not local.exists():
            raise SystemExit(f"ไม่พบ {local} — รัน scripts/convert_to_vertex_sft.py ก่อน")
        remote = f"{prefix}/{name}"
        result = subprocess.run(
            [gcloud, "storage", "cp", str(local), remote],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"อัปโหลด {name} ไม่สำเร็จ: {result.stderr.strip()}")
        print(f"[upload] {local.name} -> {remote}")
        uris.append(remote)
    return uris[0], uris[1]


def require_approved_dataset() -> None:
    """Refuse cloud upload/job creation until a reviewer approves the manifest."""
    manifest_path = VERTEX_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"ไม่พบ {manifest_path} — รัน scripts/convert_to_vertex_sft.py ก่อน")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"อ่าน {manifest_path} ไม่ได้: {exc}") from exc
    if manifest.get("status") != "approved_for_production_tuning":
        raise SystemExit(
            "ชุดข้อมูลยังไม่อนุมัติสำหรับ production tuning — ตรวจ PII/ลิขสิทธิ์/คุณภาพโดยมนุษย์ "
            "แล้วจึงเปลี่ยน status ใน training_data/vertex/manifest.json เป็น approved_for_production_tuning"
        )


def create_job(
    client: httpx.Client,
    base_url: str,
    token: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        base_url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=60.0,
    )
    if response.status_code >= 400:
        raise SystemExit(f"สร้าง tuning job ไม่สำเร็จ (HTTP {response.status_code}): {response.text}")
    return response.json()


def get_job(client: httpx.Client, name: str, region: str, token: str) -> dict[str, Any]:
    url = f"https://{region}-aiplatform.googleapis.com/v1/{name}"
    response = client.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60.0)
    if response.status_code >= 400:
        raise SystemExit(f"อ่านสถานะ job ไม่สำเร็จ (HTTP {response.status_code}): {response.text}")
    return response.json()


def summarize(job: dict[str, Any]) -> dict[str, Any]:
    tuned = job.get("tunedModel") or {}
    return {
        "name": job.get("name", ""),
        "state": job.get("state", "JOB_STATE_UNSPECIFIED"),
        "base_model": job.get("baseModel", ""),
        "tuned_model": tuned.get("model", ""),
        "tuned_endpoint": tuned.get("endpoint", ""),
        "experiment": job.get("experiment", ""),
        "error": (job.get("error") or {}).get("message", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="สร้าง Vertex AI supervised fine-tuning job")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""), help="GCP project id")
    parser.add_argument("--region", default="us-central1", choices=TUNING_REGIONS)
    parser.add_argument("--base-model", default="gemini-2.5-flash", choices=TUNABLE_BASE_MODELS)
    parser.add_argument("--bucket", default="", help="gs://bucket/prefix สำหรับอัปโหลดชุดข้อมูล")
    parser.add_argument("--train-uri", default="", help="gs:// URI ของ train (ถ้าอัปโหลดเองแล้ว)")
    parser.add_argument("--validation-uri", default="", help="gs:// URI ของ validation")
    parser.add_argument("--display-name", default="smart-classroom-assistant", help="ชื่อโมเดลที่ tune แล้ว")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--adapter-size", type=int, default=4, choices=sorted(ADAPTER_SIZES))
    parser.add_argument("--learning-rate-multiplier", type=float, default=1.0)
    parser.add_argument("--poll-interval", type=int, default=60, help="วินาทีระหว่างเช็คสถานะ")
    parser.add_argument("--timeout-minutes", type=int, default=240, help="เลิกรอเมื่อครบเวลานี้ (job ยังรันต่อ)")
    parser.add_argument("--no-wait", action="store_true", help="สร้าง job แล้วจบ ไม่ต้องรอ")
    parser.add_argument("--acknowledge-data-review", action="store_true", help="ยืนยันว่าตรวจ PII, สิทธิ์ข้อมูล และค่าใช้จ่ายแล้ว")
    args = parser.parse_args()

    if not args.project:
        raise SystemExit("ต้องระบุ --project หรือ export GOOGLE_CLOUD_PROJECT")
    if args.epochs < 1:
        raise SystemExit("--epochs ต้องมากกว่า 0")
    if args.adapter_size not in ALLOWED_ADAPTER_SIZES[args.base_model]:
        allowed = ", ".join(map(str, sorted(ALLOWED_ADAPTER_SIZES[args.base_model])))
        raise SystemExit(f"{args.base_model} รองรับ --adapter-size ได้เฉพาะ {allowed}")
    if not args.acknowledge_data_review:
        raise SystemExit("ต้องระบุ --acknowledge-data-review ก่อนอัปโหลดข้อมูลหรือสร้าง tuning job")
    require_approved_dataset()

    train_uri, validation_uri = args.train_uri.strip(), args.validation_uri.strip()
    if args.bucket:
        train_uri, validation_uri = upload_datasets(args.bucket)
    if not train_uri:
        raise SystemExit("ต้องมี --bucket (อัปโหลดให้) หรือ --train-uri")
    if not train_uri.startswith("gs://") or (validation_uri and not validation_uri.startswith("gs://")):
        raise SystemExit("dataset URI ต้องเป็น gs://")

    spec: dict[str, Any] = {
        "trainingDatasetUri": train_uri,
        "hyperParameters": {
            "epochCount": args.epochs,
            "learningRateMultiplier": args.learning_rate_multiplier,
            "adapterSize": ADAPTER_SIZES[args.adapter_size],
        },
    }
    if validation_uri:
        spec["validationDatasetUri"] = validation_uri

    body = {
        "baseModel": args.base_model,
        "tunedModelDisplayName": args.display_name,
        "supervisedTuningSpec": spec,
    }

    token = access_token()
    base_url = (
        f"https://{args.region}-aiplatform.googleapis.com/v1/"
        f"projects/{args.project}/locations/{args.region}/tuningJobs"
    )

    with httpx.Client() as client:
        job = create_job(client, base_url, token, body)
        info = summarize(job)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        RESULT_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if args.no_wait or not info["name"]:
            return

        deadline = time.time() + args.timeout_minutes * 60
        while time.time() < deadline:
            time.sleep(max(10, args.poll_interval))
            # The token can expire during long jobs; refresh on every poll.
            token = access_token()
            info = summarize(get_job(client, info["name"], args.region, token))
            print(f"[{time.strftime('%H:%M:%S')}] state={info['state']}")
            RESULT_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if info["state"] in TERMINAL_STATES:
                break
        else:
            print("หมดเวลารอ — job ยังทำงานต่อ ตรวจสถานะซ้ำได้ด้วย --no-wait แล้วดู tuning_job.json", file=sys.stderr)
            return

    print(json.dumps(info, ensure_ascii=False, indent=2))
    if info["state"] != "JOB_STATE_SUCCEEDED":
        raise SystemExit(f"tuning ไม่สำเร็จ: {info['state']} {info['error']}".strip())
    if info["tuned_endpoint"]:
        print(f"\nตั้งค่าใน .env เพื่อใช้งาน:\nGEMINI_TUNED_ENDPOINT={info['tuned_endpoint']}")


if __name__ == "__main__":
    main()
