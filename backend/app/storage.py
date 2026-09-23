# -*- coding: utf-8 -*-
"""
storage.py — เก็บไฟล์แนบ + ความปลอดภัยไฟล์แนบ (Blueprint §41 File Attachment Security)

ข้อกำหนดตาม §41 และวิธีที่ไฟล์นี้ทำ:
  * ชนิดไฟล์      → JPG / PNG / PDF เป็นชุดหลักของ MVP (เพิ่ม WEBP/GIF/HEIC เพราะกล้องมือถือ
                    และไฟล์ที่ผู้ใช้เดิมอัปโหลดไว้ใช้สกุลเหล่านี้ — ทุกชนิดต้องผ่านลายเซ็นไฟล์)
  * ขนาด          → ค่าเริ่มต้น 10 MB ต่อไฟล์ ปรับได้ด้วย MAX_UPLOAD_MB
  * Validation    → ตรวจ 3 ชั้น: content signature (magic bytes) + นามสกุล + MIME ที่ client แจ้ง
                    ต้องสอดคล้องกันทั้งสามชั้น ไม่ตรง = 415 (ชั้นที่เชื่อถือคือเนื้อไฟล์)
  * Storage Name  → เปลี่ยนชื่อเป็น uuid4().hex + สกุลที่ได้จากเนื้อไฟล์ ไม่ใช้ชื่อเดิมจากผู้ใช้เลย
                    (กัน path traversal / ชื่อไฟล์แปลก / ไฟล์ทับกัน)
  * Access        → URL ที่คืนไปมีลายเซ็น HMAC ของชื่อไฟล์ (คีย์จาก UPLOAD_URL_SECRET หรือ JWT_SECRET)
                    ปลายทาง GET /uploads/{name} ใน main.py จะยอมให้ดาวน์โหลดเมื่อ "ลายเซ็นถูกต้อง"
                    เท่านั้น — ไม่มีการ list ไดเรกทอรีอีก
                    ลายเซ็นไม่มีวันหมดอายุโดยเจตนา เพราะ URL ถูกเก็บลง DB และส่งต่อใน LINE
  * Malware       → ยังไม่สแกน (ต้องมี ClamAV/บริการภายนอก) — ดู NOTE ท้ายไฟล์

โหมดเก็บไฟล์:
  * STORAGE_BACKEND=local (ค่าเริ่มต้น, dev) → เขียนลง backend/uploads แล้วเสิร์ฟผ่าน /uploads/{name}
  * STORAGE_BACKEND=cloud (+ S3_*)          → upload ไป S3 / S3-compatible (R2, MinIO, Wasabi...)
    object เป็น private เสมอ และ backend เสิร์ฟผ่าน URL ที่ลงลายเซ็น เพื่อไม่เปิด bucket/CDN
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import unicodedata
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_REGION = os.environ.get("S3_REGION", "auto")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")  # e.g. https://<acct>.r2.cloudflarestorage.com
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")

# ── ขนาดสูงสุดต่อไฟล์ (§41: "≤ 10 MB ต่อไฟล์ ปรับตาม server") ──────────
try:
    MAX_UPLOAD_MB = max(1, int(os.environ.get("MAX_UPLOAD_MB", "10")))
except ValueError:
    MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# ── ชนิดไฟล์ที่รองรับ: สกุลมาตรฐาน → MIME ที่จะเสิร์ฟกลับ ──────────────
MIME_BY_EXT: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
}
ALLOWED_EXT = frozenset(MIME_BY_EXT)

# สกุลที่ผู้ใช้พิมพ์มา → สกุลมาตรฐานที่เราใช้เก็บ
_EXT_ALIAS: dict[str, str] = {
    ".jpg": ".jpg", ".jpeg": ".jpg", ".jpe": ".jpg",
    ".png": ".png",
    ".webp": ".webp",
    ".gif": ".gif",
    ".heic": ".heic", ".heif": ".heic",
    ".pdf": ".pdf",
}

# MIME ที่ client แจ้ง → สกุลมาตรฐาน (ค่า None = แจ้งมาแบบไม่ระบุชนิด ให้ตัดสินจากเนื้อไฟล์)
_EXT_BY_CLIENT_MIME: dict[str, Optional[str]] = {
    "": None,
    "application/octet-stream": None,
    "binary/octet-stream": None,
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/pjpeg": ".jpg",
    "image/png": ".png", "image/x-png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic", "image/heif": ".heic",
    "image/heic-sequence": ".heic", "image/heif-sequence": ".heic",
    "application/pdf": ".pdf", "application/x-pdf": ".pdf",
}

# ชื่อไฟล์ที่ระบบสร้างเองเท่านั้น: uuid4().hex (32 hex) + สกุลที่รองรับ
_UPLOAD_NAME_RE = re.compile(
    r"^[0-9a-f]{32}\.(?:" + "|".join(e.lstrip(".") for e in sorted(ALLOWED_EXT)) + r")$"
)

# ไฟล์ที่ต้องบังคับดาวน์โหลด ไม่เปิดแสดงในเบราว์เซอร์ (กัน PDF ที่ฝัง JS ทำงานใน origin เดียวกัน)
_ATTACHMENT_ONLY_EXT = frozenset({".pdf"})

# local (dev) dir
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _http_error(status: int, detail: str):
    """สร้าง HTTPException แบบ import ตอนใช้ เพื่อให้ไฟล์นี้ทดสอบได้โดยไม่ต้องมี FastAPI ครบ"""
    from fastapi import HTTPException

    return HTTPException(status_code=status, detail=detail)


# ─── ชั้นที่ 1: ลายเซ็นเนื้อไฟล์ (content signature / magic bytes) ──────
def sniff_ext(content: bytes) -> Optional[str]:
    """เดาสกุลจากไบต์ต้นไฟล์จริง — คืน None ถ้าไม่ใช่ชนิดที่รองรับ

    เชื่อผลจากฟังก์ชันนี้เป็นหลัก เพราะนามสกุลและ MIME ที่ client ส่งมาปลอมได้
    """
    if not content:
        return None
    head = content[:64]
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if head[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[4:8] == b"ftyp" and content[8:12] in (
        b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1",
    ):
        return ".heic"
    # PDF: ตามสเปกอนุญาตให้มีไบต์นำหน้าได้เล็กน้อย ตรวจใน 1 KB แรก
    if b"%PDF-" in content[:1024]:
        return ".pdf"
    return None


def normalize_ext(filename: str) -> Optional[str]:
    """สกุลจากชื่อไฟล์ที่ผู้ใช้ส่งมา → สกุลมาตรฐาน (None = ไม่มีสกุล/ไม่รองรับ)"""
    raw = os.path.splitext(os.path.basename(filename or ""))[1].lower()
    if not raw:
        return None
    return _EXT_ALIAS.get(raw, "")  # "" = มีสกุลแต่ไม่รองรับ (ต่างจาก None = ไม่มีสกุล)


def safe_original_name(filename: str) -> str:
    """ชื่อไฟล์เดิมสำหรับ 'แสดงผล' เท่านั้น — ตัด path, อักขระควบคุม และความยาว"""
    base = os.path.basename((filename or "").replace("\\", "/"))
    base = unicodedata.normalize("NFC", base)
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '"\\/\r\n\t')
    base = base.strip() or "file"
    return base[:120]


# ─── ชั้นที่ 2+3: นามสกุล + MIME ที่ client แจ้ง ต้องตรงกับเนื้อไฟล์ ────
def validate_upload(content: bytes, filename: str, content_type: Optional[str] = None) -> str:
    """ตรวจไฟล์ตาม §41 ทั้งสามชั้น → คืนสกุลมาตรฐานที่จะใช้เก็บ

    raise HTTPException: 400 ไฟล์ว่าง / 413 ใหญ่เกิน / 415 ชนิดไม่รองรับหรือไม่สอดคล้อง
    """
    if not content:
        raise _http_error(400, "ไฟล์ว่าง — กรุณาเลือกไฟล์ใหม่")
    if len(content) > MAX_UPLOAD_BYTES:
        raise _http_error(413, f"ไฟล์เกิน {MAX_UPLOAD_MB} MB")

    sniffed = sniff_ext(content)
    if sniffed is None:
        raise _http_error(415, "ชนิดไฟล์ไม่รองรับ (รับ jpg / png / pdf / webp / gif / heic)")

    ext_from_name = normalize_ext(filename)
    if ext_from_name == "":
        raise _http_error(415, "นามสกุลไฟล์ไม่รองรับ (รับ jpg / png / pdf / webp / gif / heic)")
    if ext_from_name and ext_from_name != sniffed:
        raise _http_error(415, "นามสกุลไฟล์ไม่ตรงกับเนื้อไฟล์จริง")

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in _EXT_BY_CLIENT_MIME:
        raise _http_error(415, f"ชนิดไฟล์ (MIME) ไม่รองรับ: {declared}")
    ext_from_mime = _EXT_BY_CLIENT_MIME[declared]
    if ext_from_mime and ext_from_mime != sniffed:
        raise _http_error(415, "ชนิดไฟล์ (MIME) ไม่ตรงกับเนื้อไฟล์จริง")

    return sniffed


# ─── ลายเซ็น URL ไฟล์แนบ (§41 Access) ──────────────────────────────────
def _url_secret() -> bytes:
    return (
        os.environ.get("UPLOAD_URL_SECRET")
        or os.environ.get("JWT_SECRET")
        or "dev-secret-change-me"
    ).encode("utf-8")


def sign_upload_name(name: str) -> str:
    """ลายเซ็นของชื่อไฟล์ — ผูกกับ secret ของเซิร์ฟเวอร์ เดาไม่ได้จากชื่อไฟล์"""
    return hmac.new(_url_secret(), f"upload:{name}".encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def verify_upload_signature(name: str, sig: Optional[str]) -> bool:
    if not sig:
        return False
    return hmac.compare_digest(sign_upload_name(name), sig.strip().lower())


def signed_upload_url(name: str) -> str:
    """URL ที่ใช้ดาวน์โหลดได้จริง (แนบลายเซ็น) — เก็บลง DB ได้ เพราะไม่หมดอายุ"""
    return f"/uploads/{name}?s={sign_upload_name(name)}"


def is_safe_upload_name(name: str) -> bool:
    """ชื่อไฟล์ต้องเป็นรูปที่ระบบสร้างเองเท่านั้น (uuid4().hex + สกุลที่รองรับ)"""
    return bool(_UPLOAD_NAME_RE.match(name or ""))


def is_servable_upload_name(name: str) -> bool:
    """ชื่อไฟล์ที่ยอมเสิร์ฟได้ — ครอบไฟล์เก่าที่อัปโหลดไว้ก่อนมีกฎ uuid ด้วย

    เงื่อนไข: ต้องเป็นชื่อไฟล์เดี่ยว (ไม่มี / \\ .. หรือ NUL) และสกุลอยู่ในชุดที่รองรับ
    ส่วน "สิทธิ์เข้าถึง" ตรวจแยกที่ปลายทาง (ลายเซ็น URL หรือผู้ใช้ที่ล็อกอินอยู่)
    """
    if not name or name in (".", "..") or len(name) > 200:
        return False
    if "/" in name or "\\" in name or "\x00" in name:
        return False
    if os.path.basename(name) != name:
        return False
    return _EXT_ALIAS.get(os.path.splitext(name)[1].lower(), "") in ALLOWED_EXT


def local_upload_path(name: str) -> Optional[str]:
    """path จริงในเครื่องของไฟล์แนบ — คืน None ถ้าชื่อไม่ปลอดภัยหรือหลุดออกนอกโฟลเดอร์"""
    if not is_servable_upload_name(name):
        return None
    root = os.path.realpath(UPLOAD_DIR)
    path = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, path]) != root:
        return None
    return path


def mime_for_name(name: str) -> str:
    ext = os.path.splitext(name or "")[1].lower()
    return MIME_BY_EXT.get(_EXT_ALIAS.get(ext, ""), "application/octet-stream")


def is_inline_viewable(name: str) -> bool:
    """True = ให้เบราว์เซอร์แสดงในหน้า (รูป) / False = บังคับดาวน์โหลด (pdf)"""
    ext = _EXT_ALIAS.get(os.path.splitext(name or "")[1].lower(), "")
    return bool(ext) and ext not in _ATTACHMENT_ONLY_EXT


# ─── บันทึกไฟล์ ────────────────────────────────────────────────────────
def save_upload(content: bytes, filename: str, content_type: Optional[str] = None) -> dict:
    """ตรวจตาม §41 แล้วบันทึก → {url, filename, size, mime_type, backend}"""
    ext = validate_upload(content, filename, content_type)
    name = f"{uuid.uuid4().hex}{ext}"
    original = safe_original_name(filename)
    mime = MIME_BY_EXT[ext]
    if STORAGE_BACKEND == "cloud":
        return _save_s3(content, f"uploads/{name}", original, mime, ext)
    return _save_local(content, name, original, mime)


def _save_local(content: bytes, name: str, original: str, mime: str) -> dict:
    path = local_upload_path(name)
    if path is None:  # ไม่ควรเกิด: ชื่อสร้างจาก uuid เอง
        raise _http_error(500, "ชื่อไฟล์ที่สร้างไม่ถูกต้อง")
    with open(path, "wb") as f:
        f.write(content)
    return {
        "url": signed_upload_url(name),
        "filename": original,
        "size": len(content),
        "mime_type": mime,
        "backend": "local",
    }


def _save_s3(content: bytes, key: str, original: str, mime: str, ext: str) -> dict:
    try:
        client = _s3_client()
        extra = {
            "Bucket": S3_BUCKET,
            "Key": key,
            "Body": content,
            "ContentType": mime,
        }
        if ext in _ATTACHMENT_ONLY_EXT:
            extra["ContentDisposition"] = f'attachment; filename="{original}"'
        client.put_object(**extra)
        return {
            # Do not return a public object-store URL.  The same signed proxy URL
            # works for local disks and private S3/R2 buckets.
            "url": signed_upload_url(os.path.basename(key)),
            "filename": original,
            "size": len(content),
            "mime_type": mime,
            "backend": "cloud",
        }
    except Exception as e:
        from fastapi import HTTPException

        if isinstance(e, HTTPException):
            raise
        logger.exception("Cloud upload failed")
        raise _http_error(502, "อัปโหลดไฟล์ไม่สำเร็จ กรุณาลองใหม่") from e


def _s3_client():
    """Create the private S3/R2 client only when cloud storage is used."""
    import boto3
    from botocore.client import Config

    if not S3_BUCKET:
        raise _http_error(500, "S3_BUCKET ไม่ได้ตั้งค่า")
    return boto3.client(
        "s3",
        region_name=S3_REGION,
        endpoint_url=S3_ENDPOINT or None,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def read_cloud_upload(name: str) -> Optional[bytes]:
    """Read one private object for the authenticated/signed download endpoint.

    Files are capped at upload time, so returning bytes avoids exposing an object-store
    URL while keeping the response path simple and bounded.
    """
    if STORAGE_BACKEND != "cloud" or not is_servable_upload_name(name):
        return None
    try:
        response = _s3_client().get_object(Bucket=S3_BUCKET, Key=f"uploads/{name}")
        return response["Body"].read()
    except Exception as exc:
        # The route deliberately treats missing/private object errors as not found;
        # callers must not receive provider configuration details.
        if getattr(exc, "response", {}).get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise _http_error(502, "อ่านไฟล์จาก cloud storage ไม่สำเร็จ")


# NOTE (§41 Malware): ยังไม่มีการสแกนไวรัส เพราะต้องมี ClamAV daemon หรือบริการภายนอก
# ซึ่งไม่มีใน Render free tier. จุดที่จะเสียบได้คือใน save_upload() หลัง validate_upload()
# ผ่านแล้วและก่อนเขียนไฟล์ — ถ้าเปิดใช้ ให้เรียก scanner ที่นั่นและตอบ 422 เมื่อพบสิ่งผิดปกติ
