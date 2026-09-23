"""
generate_qr.py — สร้าง QR Code ของอุปกรณ์ "จากฐานข้อมูลจริง"
แยกเป็นหมวด: qr_codes/<รหัสโรงเรียน>/<หมวดอุปกรณ์>/<รหัสอุปกรณ์>.png
พร้อมหน้า index.html ที่พิมพ์ออกมาติดเครื่องได้ (เห็นชื่ออุปกรณ์/ห้อง ไม่ใช่แค่รหัส)

เดิมสคริปต์นี้อ่าน scripts/devices.json ซึ่งเป็นสแนปช็อตรหัสรูปแบบเก่า
(DEV-2024-00123) ที่ไม่มีอยู่ในฐานข้อมูลอีกแล้ว → QR ที่ได้สแกนแล้วขึ้น
"ไม่พบอุปกรณ์" ตอนนี้จึง query จาก devices ตรง ๆ เพื่อให้รหัสตรงกับของจริงเสมอ

ใช้:
    python scripts/generate_qr.py                    # ทุกโรงเรียน (ข้ามไฟล์ที่มีแล้ว)
    python scripts/generate_qr.py --org SCHDEMO      # เฉพาะโรงเรียนเดียว
    python scripts/generate_qr.py --dry-run          # ดูว่าจะได้อะไร ไม่เขียนไฟล์
    python scripts/generate_qr.py --overwrite        # สร้างทับของเดิม
    python scripts/generate_qr.py --prune-stale      # ลบ .png ที่ไม่ตรงกับอุปกรณ์ปัจจุบัน

URL ใน QR ปรับได้ด้วย --base-url หรือ env QR_BASE_URL
(ต้องเป็นหน้าสแกนที่รับ ?device= เช่น https://<host>/scan)
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import qrcode
from qrcode.constants import ERROR_CORRECT_M

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

# ให้ import app.* ได้ไม่ว่าจะรันจาก backend/ หรือจากรากโปรเจกต์
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import Device, Organization, SessionLocal  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

# หมวดอุปกรณ์ใช้ตัวเดียวกับฝั่ง API เพื่อให้โฟลเดอร์ตรงกับตัวกรองในหน้าเว็บ
try:
    from app.main import device_category_of  # noqa: E402
except Exception:  # pragma: no cover - import app.main ไม่ได้ก็ยังสร้าง QR ได้
    def device_category_of(_device_type: Optional[str]) -> Optional[str]:
        return None

DEFAULT_OUTPUT_DIR = REPO_ROOT / "qr_codes"
DEFAULT_BASE_URL = os.environ.get("QR_BASE_URL", "https://iwasmart-service.vercel.app/scan")

# ชื่อโฟลเดอร์ของแต่ละหมวด — ตั้งเป็น ASCII เพื่อให้พาธพอร์ตข้ามเครื่อง/ระบบไฟล์
# และใช้ใน URL ได้ตรง ๆ (ชื่อหมวดภาษาไทยยังใช้แสดงในหน้า index/manifest ตามเดิม)
# คีย์ต้องตรงกับ DEVICE_CATEGORY_TYPES ใน app/main.py
CATEGORY_DIR_SLUG: dict[str, str] = {
    "จอแสดงภาพ": "01-display",
    "คอมพิวเตอร์": "02-computer",
    "ระบบเครือข่าย": "03-network",
    "ภาพและเสียง": "04-audio-video",
    "อุปกรณ์ต่อพ่วง": "05-peripheral",
    "ไฟฟ้า/สำรองไฟ": "06-power",
    "ซอฟต์แวร์": "07-software",
    "อื่น ๆ": "08-other",
}


def as_text(value: Any) -> Optional[str]:
    """คืนค่าเป็น str — รองรับทั้ง Enum (มี .value) และ str ธรรมดา"""
    if value is None:
        return None
    inner = getattr(value, "value", value)
    text = str(inner).strip()
    return text or None


def first_attr(obj: Any, *names: str) -> Optional[str]:
    """หยิบ attribute ตัวแรกที่มีค่า — ชื่อคอลัมน์ห้อง/อาคารต่างกันได้ตามสคีมา"""
    if obj is None:
        return None
    for name in names:
        text = as_text(getattr(obj, name, None))
        if text:
            return text
    return None


def slugify(value: Optional[str], fallback: str) -> str:
    """ทำชื่อโฟลเดอร์ให้ปลอดภัยกับทุกระบบไฟล์ (กัน / \\ : ช่องว่าง ฯลฯ)

    ต้องเก็บอักขระผสม (สระ/วรรณยุกต์ไทย) ไว้ด้วย: ตัวพวกนี้ isalnum() เป็น False
    ถ้าตัดออกจะได้ชื่อเพี้ยนแบบ "ระบบเคร-อข-าย"
    """
    cleaned = "".join(
        ch
        if (ch.isalnum() or ch in "-_." or unicodedata.category(ch).startswith("M"))
        else "-"
        for ch in (value or "").strip()
    )
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-._")
    return cleaned or fallback


def category_dir_name(category: Optional[str]) -> str:
    """หมวดหมู่ → ชื่อโฟลเดอร์ (ใช้สลัก ASCII ที่กำหนดไว้ก่อน ค่อย fallback เป็น slugify)"""
    if not category:
        return CATEGORY_DIR_SLUG["อื่น ๆ"]
    mapped = CATEGORY_DIR_SLUG.get(category)
    if mapped:
        return mapped
    return slugify(category, CATEGORY_DIR_SLUG["อื่น ๆ"])


def device_rows(session, org_code: Optional[str]) -> list[dict[str, Any]]:
    """ดึงอุปกรณ์ + โรงเรียน + ห้อง มาเป็น dict ธรรมดา (ปิด session แล้วยังใช้ได้)"""
    stmt = (
        select(Device, Organization)
        .join(Organization, Organization.id == Device.organization_id)
        .options(selectinload(Device.room))
        .order_by(Organization.code, Device.device_id)
    )
    if org_code:
        stmt = stmt.where(Organization.code == org_code)

    rows: list[dict[str, Any]] = []
    for device, org in session.execute(stmt).all():
        device_id = as_text(device.device_id)
        if not device_id:
            continue
        device_type = as_text(device.device_type)
        room = getattr(device, "room", None)
        room_name = first_attr(room, "name", "room_name", "title")
        room_code = first_attr(room, "code", "room_code", "number")
        building = first_attr(
            getattr(room, "building", None), "name", "building_name", "code"
        )
        rows.append({
            "device_id": device_id,
            "device_type": device_type,
            "category": as_text(device_category_of(device_type)) or "other",
            "brand": first_attr(device, "brand"),
            "model": first_attr(device, "model"),
            "org_code": as_text(org.code) or f"ORG{org.id}",
            "org_name": first_attr(org, "short_name", "name") or "-",
            "building": building,
            "room_code": room_code,
            "room_name": room_name,
        })
    return rows


def device_label(row: dict[str, Any]) -> str:
    """ป้ายกำกับที่มนุษย์อ่านรู้เรื่อง — ประเภท + ห้อง ไม่ใช่แค่รหัส"""
    parts = [row["device_type"] or "อุปกรณ์"]
    brand_model = " ".join(p for p in (row.get("brand"), row.get("model")) if p)
    if brand_model:
        parts.append(brand_model)
    place = row.get("room_name") or row.get("room_code")
    if place:
        parts.append(f"ห้อง {place}" if not str(place).startswith("ห้อง") else str(place))
    if row.get("building"):
        parts.append(str(row["building"]))
    return " · ".join(parts)


def qr_url(base_url: str, device_id: str) -> str:
    base = base_url.rstrip("/")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}device={quote(device_id, safe='')}"


def write_qr(url: str, outfile: Path) -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    outfile.parent.mkdir(parents=True, exist_ok=True)
    img.save(outfile)


PAGE_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; font-family: "Segoe UI", "Noto Sans Thai", Tahoma, sans-serif;
       background: #f4f5f7; color: #16181d; }
h1 { font-size: 1.4rem; margin: 0 0 4px; }
p.sub { margin: 0 0 24px; color: #5a616e; font-size: .9rem; }
h2 { font-size: 1.05rem; margin: 28px 0 12px; padding-bottom: 6px;
     border-bottom: 2px solid #d8dbe2; }
.grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
.card { background: #fff; border: 1px solid #d8dbe2; border-radius: 12px; padding: 12px;
        display: flex; flex-direction: column; align-items: center; gap: 8px;
        page-break-inside: avoid; break-inside: avoid; }
.card img { width: 100%; max-width: 160px; height: auto; image-rendering: pixelated; }
.code { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: .8rem;
        font-weight: 700; word-break: break-all; text-align: center; }
.label { font-size: .78rem; color: #5a616e; text-align: center; line-height: 1.45; }
ul.schools { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px;
             grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
ul.schools a { display: block; background: #fff; border: 1px solid #d8dbe2; border-radius: 12px;
               padding: 14px 16px; text-decoration: none; color: inherit; }
ul.schools a:hover, ul.schools a:focus-visible { border-color: #3b6fd4; outline: none; }
ul.schools strong { display: block; font-size: .98rem; }
ul.schools span { font-size: .8rem; color: #5a616e; }
@media print {
  body { background: #fff; padding: 0; }
  .card { border-color: #999; }
}
"""


def render_school_page(org_code: str, org_name: str, rows: list[dict[str, Any]]) -> str:
    """หน้า QR ของโรงเรียนหนึ่ง — จัดกลุ่มตามหมวดอุปกรณ์"""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row)

    blocks: list[str] = []
    for category in sorted(by_category):
        items = sorted(by_category[category], key=lambda r: r["device_id"])
        cards = "\n".join(
            f"""      <div class="card">
        <img src="{html.escape(r['_rel_path'])}" alt="QR ของ {html.escape(r['device_id'])}">
        <div class="code">{html.escape(r['device_id'])}</div>
        <div class="label">{html.escape(device_label(r))}</div>
      </div>"""
            for r in items
        )
        blocks.append(
            f"""    <h2>{html.escape(category)} ({len(items)})</h2>
    <div class="grid">
{cards}
    </div>"""
        )

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QR อุปกรณ์ — {html.escape(org_name)} ({html.escape(org_code)})</title>
<style>{PAGE_CSS}</style>
</head>
<body>
  <h1>QR อุปกรณ์ — {html.escape(org_name)}</h1>
  <p class="sub">รหัสโรงเรียน {html.escape(org_code)} · ทั้งหมด {len(rows)} เครื่อง · สแกนเพื่อแจ้งซ่อม</p>
{chr(10).join(blocks)}
</body>
</html>
"""


def render_root_page(groups: dict[str, dict[str, Any]]) -> str:
    items = "\n".join(
        f"""    <li><a href="{html.escape(info['dir'])}/index.html">
      <strong>{html.escape(info['org_name'])}</strong>
      <span>{html.escape(code)} · {info['count']} เครื่อง</span>
    </a></li>"""
        for code, info in sorted(groups.items())
    )
    total = sum(info["count"] for info in groups.values())
    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QR อุปกรณ์ — ทุกโรงเรียน</title>
<style>{PAGE_CSS}</style>
</head>
<body>
  <h1>QR อุปกรณ์ทั้งระบบ</h1>
  <p class="sub">{len(groups)} โรงเรียน · {total} เครื่อง — เลือกโรงเรียนเพื่อดู/พิมพ์ QR</p>
  <ul class="schools">
{items}
  </ul>
</body>
</html>
"""


def prune_stale(output_dir: Path, keep: set[Path]) -> int:
    """ลบ .png ที่ไม่ตรงกับอุปกรณ์ปัจจุบัน (เช่นรหัสรูปแบบเก่าที่ค้างอยู่)"""
    removed = 0
    for png in sorted(output_dir.rglob("*.png")):
        if png.resolve() in keep:
            continue
        try:
            png.unlink()
            print(f"  - ลบไฟล์ที่ไม่ตรงกับอุปกรณ์แล้ว: {png.relative_to(output_dir)}")
            removed += 1
        except OSError as exc:
            print(f"  ! ลบ {png.name} ไม่สำเร็จ: {exc}")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="สร้าง QR อุปกรณ์จากฐานข้อมูล")
    parser.add_argument("--org", help="รหัสโรงเรียน (Organization.code) เฉพาะโรงเรียนเดียว")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_DIR, help="โฟลเดอร์ปลายทาง")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="URL หน้าสแกน")
    parser.add_argument("--overwrite", action="store_true", help="สร้างทับไฟล์ที่มีอยู่")
    parser.add_argument("--dry-run", action="store_true", help="แสดงผลลัพธ์ แต่ไม่เขียนไฟล์")
    parser.add_argument(
        "--prune-stale", action="store_true",
        help="ลบ .png ที่ไม่ตรงกับอุปกรณ์ในฐานข้อมูล (ใช้ล้างรหัสรูปแบบเก่า)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        rows = device_rows(session, args.org)
    finally:
        session.close()

    if not rows:
        target = f"โรงเรียน {args.org}" if args.org else "ฐานข้อมูล"
        print(f"✗ ไม่พบอุปกรณ์ใน{target} — รัน python scripts/seed_db.py ก่อน")
        return 1

    output_dir: Path = args.out
    print(f"\nสร้าง QR {len(rows)} เครื่อง → {output_dir}")
    print(f"URL: {qr_url(args.base_url, rows[0]['device_id'])}\n")

    groups: dict[str, dict[str, Any]] = {}
    keep: set[Path] = set()
    created = skipped = failed = 0

    for row in rows:
        org_dir = slugify(row["org_code"], "unknown-org")
        cat_dir = category_dir_name(row["category"])
        filename = f"{slugify(row['device_id'], 'device')}.png"
        outfile = output_dir / org_dir / cat_dir / filename
        row["_rel_path"] = f"{cat_dir}/{filename}"
        keep.add(outfile.resolve())

        info = groups.setdefault(
            row["org_code"],
            {"dir": org_dir, "org_name": row["org_name"], "count": 0, "rows": []},
        )
        info["count"] += 1
        info["rows"].append(row)

        rel = outfile.relative_to(output_dir)
        if args.dry_run:
            print(f"  · {rel}  ({device_label(row)})")
            continue
        if outfile.exists() and not args.overwrite:
            skipped += 1
            continue
        try:
            write_qr(qr_url(args.base_url, row["device_id"]), outfile)
            created += 1
            print(f"  + {rel}  ({device_label(row)})")
        except Exception as exc:
            failed += 1
            print(f"  ! {rel} ล้มเหลว: {exc!r}")

    if args.dry_run:
        print(f"\n(dry-run) {len(rows)} เครื่อง / {len(groups)} โรงเรียน — ไม่มีการเขียนไฟล์")
        return 0

    # หน้า index ต่อโรงเรียน + หน้ารวม — ใช้พิมพ์ติดเครื่อง และเห็นว่าเป็นอุปกรณ์อะไร
    for code, info in groups.items():
        school_dir = output_dir / info["dir"]
        school_dir.mkdir(parents=True, exist_ok=True)
        (school_dir / "index.html").write_text(
            render_school_page(code, info["org_name"], info["rows"]),
            encoding="utf-8",
        )
    if not args.org:
        (output_dir / "index.html").write_text(render_root_page(groups), encoding="utf-8")

    manifest = {
        "base_url": args.base_url,
        "total_devices": len(rows),
        "schools": [
            {
                "org_code": code,
                "org_name": info["org_name"],
                "directory": info["dir"],
                "device_count": info["count"],
                "devices": [
                    {
                        "device_id": r["device_id"],
                        "device_type": r["device_type"],
                        "category": r["category"],
                        "building": r["building"],
                        "room": r["room_name"] or r["room_code"],
                        "label": device_label(r),
                        "file": f"{info['dir']}/{r['_rel_path']}",
                        "url": qr_url(args.base_url, r["device_id"]),
                    }
                    for r in sorted(info["rows"], key=lambda x: x["device_id"])
                ],
            }
            for code, info in sorted(groups.items())
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    removed = prune_stale(output_dir, keep) if args.prune_stale else 0

    print(
        f"\n✅ สร้างใหม่ {created} · ข้ามที่มีแล้ว {skipped} · ล้มเหลว {failed}"
        + (f" · ลบไฟล์ค้าง {removed}" if args.prune_stale else "")
    )
    print(f"   เปิดดู/พิมพ์: {output_dir / 'index.html'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
