# -*- coding: utf-8 -*-
"""
storage.py — เก็บไฟล์ (upload รูป) แบบ cross-platform
- STORAGE_BACKEND=cloud  (+ S3_* env) → upload ไป S3 / S3-compatible (Cloudinary R2, MinIO, Wasabi...)
- STORAGE_BACKEND=local (ค่าเริ่มต้น, สำหรับ dev) → เขียนลง local disk

คืน URL เต็ม (https://...) เสมอในโหมด cloud เพื่อให้ Render ฟรี (ไม่มี disk ถาวร) ใช้ได้
"""
import os
import uuid
import shutil

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_REGION = os.environ.get("S3_REGION", "auto")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")  # e.g. https://<acct>.r2.cloudflarestorage.com
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_PUBLIC_BASE = os.environ.get("S3_PUBLIC_BASE", "")  # public CDN/base URL prefix

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}

# local (dev) dir
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _validate(content: bytes, filename: str) -> str:
    """คืน ext ที่ปลอดภัย; raise ถ้าไม่รองรับ"""
    ext = os.path.splitext(filename or "")[1].lower() or ".jpg"
    if ext not in ALLOWED_EXT:
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="ชนิดไฟล์ไม่รองรับ (ใช้ jpg/png/webp)")
    return ext


def save_upload(content: bytes, filename: str) -> dict:
    """บันทึกไฟล์ → คืน {url, filename, size, backend}"""
    ext = _validate(content, filename)
    key = f"uploads/{uuid.uuid4().hex}{ext}"
    if STORAGE_BACKEND == "cloud":
        return _save_s3(content, key, filename)
    return _save_local(content, key, filename)


def _save_local(content: bytes, key: str, filename: str) -> dict:
    path = os.path.join(UPLOAD_DIR, os.path.basename(key))
    with open(path, "wb") as f:
        f.write(content)
    return {"url": f"/uploads/{os.path.basename(key)}", "filename": filename, "size": len(content), "backend": "local"}


def _save_s3(content: bytes, key: str, filename: str) -> dict:
    import boto3
    from botocore.client import Config
    from fastapi import HTTPException
    if not S3_BUCKET:
        raise HTTPException(status_code=500, detail="S3_BUCKET ไม่ได้ตั้งค่า")
    try:
        client = boto3.client(
            "s3",
            region_name=S3_REGION,
            endpoint_url=S3_ENDPOINT or None,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            config=Config(signature_version="s3v4"),
        )
        content_type = "image/" + key.rsplit(".", 1)[-1].lower().replace("jpg", "jpeg")
        client.put_object(Bucket=S3_BUCKET, Key=key, Body=content, ContentType=content_type)
        # public base URL หรือ endpoint+bucket
        if S3_PUBLIC_BASE:
            url = f"{S3_PUBLIC_BASE.rstrip('/')}/{key}"
        elif S3_ENDPOINT:
            url = f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{key}"
        else:
            url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
        return {"url": url, "filename": filename, "size": len(content), "backend": "cloud"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"อัปโหลดไป cloud ล้มเหลว: {e}")
