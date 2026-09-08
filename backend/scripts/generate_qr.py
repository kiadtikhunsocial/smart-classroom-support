"""
generate_qr.py — สร้าง QR Code สำหรับอุปกรณ์แต่ละตัว
ใช้: python scripts/generate_qr.py
Output: qr_codes/{device_id}.png
"""

import json
import sys
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "qr_codes"
DEVICES_FILE = SCRIPT_DIR / "devices.json"

BASE_URL = "http://localhost:5173/device"


def generate(device_id: str, outfile: Path) -> None:
    url = f"{BASE_URL}/{device_id}"
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(outfile)
    print(f"  OK {outfile.name}  →  {url}")


def main() -> None:
    if not DEVICES_FILE.exists():
        print(f"❌ {DEVICES_FILE} ไม่พบ — รัน seed_db.py ก่อน")
        sys.exit(1)

    devices = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n📷 สร้าง QR {len(devices)} อุปกรณ์ → {OUTPUT_DIR}/\n")

    done = 0
    for d in devices:
        did = d.get("device_id") or d.get("id")
        if not did:
            print(f"  ⚠ ข้าม: {d}")
            continue
        out = OUTPUT_DIR / f"{did}.png"
        if out.exists():
            print(f"  ⊘ มีอยู่แล้ว: {out.name}")
            continue
        try:
            generate(did, out)
            done += 1
        except Exception as e:
            print(f"  ✘ ล้มเหลว {did}: {e}")

    print(f"\n✅ เสร็จ {done} ไฟล์")


if __name__ == "__main__":
    main()
