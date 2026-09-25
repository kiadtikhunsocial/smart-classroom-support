#!/usr/bin/env python3
"""seed_mockup_5_schools.py — สร้างข้อมูล mockup สำหรับเดโม/ทดสอบ

ปริมาณข้อมูลที่สร้าง
  • 5 โรงเรียน (organizations code SCH-M01..SCH-M05) × 5 ห้อง = 25 ห้อง
  • 100 อุปกรณ์ แบ่งไม่เท่ากันตามขนาดโรงเรียน (10 / 15 / 20 / 25 / 30)
    รหัสอุปกรณ์ขึ้นต้นด้วยรหัสของโรงเรียนนั้นเสมอ —
    <รหัสโรงเรียน>-<อาคาร>-<ห้อง>-<ประเภท>-<ลำดับ> เช่น SCHM01-B1-R101-DISP-01
    (รูปแบบเดียวกับ generate_device_id ของ API → สองโรงเรียนไม่ได้รหัสซ้ำกัน)
    ครอบคลุมประเภทอุปกรณ์ตัวอย่างที่ระบบรองรับ
  • 12 ใบแจ้งซ่อมต่อโรงเรียน + ชุด "ซ่อมซ้ำ" อีก 3 ใบใน 2 โรงเรียนแรก
    (ไว้ให้ PM Rule 1 REPEATED_FAILURE จับได้จริง)
  • ประวัติเปลี่ยนสถานะ (ticket_updates) ตามเส้นทางสถานะที่ถูกต้อง
  • แผน PM 6 แผน + งาน PM คละสถานะ pending/overdue/done/skipped
  • device_health_flags ตัวอย่างของทั้ง 3 กฎใน §38
  • ผู้ใช้ทดสอบ: admin_school + it_support ต่อโรงเรียน
  • audit_logs ตัวอย่าง (ทุกแถวติดแท็ก user_agent = "seed-mockup/1.0")

การใช้งาน
    python scripts/seed_mockup_5_schools.py --password <local-demo-password>
    python scripts/seed_mockup_5_schools.py --purge         # ลบเฉพาะข้อมูล mockup ชุดนี้แล้วสร้างใหม่

หมายเหตุความปลอดภัย: บัญชีที่สร้างเป็นบัญชีทดสอบรหัสผ่านเดียวกันทั้งชุด
ห้ามรันสคริปต์นี้กับฐานข้อมูล production
ปลายทางคือ DATABASE_URL ของ app.models (ค่าเริ่มต้น: postgres@localhost:5432/smart_classroom)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

# สคริปต์อยู่ที่ backend/scripts/ → path ที่ต้องเพิ่มคือ backend/ (พาเรนต์)
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

import random

from sqlalchemy import select, text

from app.models import (
    AuditLog,
    Device,
    DeviceHealthFlag,
    DeviceStatus,
    DeviceType,
    Organization,
    PMPlan,
    PMTask,
    Priority,
    RepairTicket,
    Room,
    SessionLocal,
    TicketStatus,
    TicketUpdate,
    User,
    UserRole,
    init_db,
    priority_enum,
    ticket_status_enum,
)
from demo_safety import require_local_demo_database

# ---------------------------------------------------------------------------
# ค่าคงที่
# ---------------------------------------------------------------------------

RND_SEED = 20260918                 # sync กับวันที่ทำเดโม → ข้อมูลซ้ำได้เหมือนกันทุกครั้ง
PBKDF2_ITERATIONS = 100_000         # ต้องตรงกับ app.main.hash_password
SEED_TAG = "seed-mockup/1.0"        # แท็กใน audit_logs.user_agent สำหรับ --purge


def mock_serial(brand: str, purchased: datetime, school_idx: int, d_idx: int) -> str:
    """หมายเลขสินค้า (Serial Number) หน้าตาเหมือนของผู้ผลิตจริง

    รูปแบบ: <2 ตัวอักษรยี่ห้อ><ปีที่ซื้อ 2 หลัก><สัปดาห์ 2 หลัก>-<เช็คซัม 6 หลัก>
    เช่น TI2417-8C3D1A

    เลิกใช้รูปแบบเดิม TIP-0105-MOCK เพราะหน้า "ตรวจสอบประกัน" ให้ผู้ใช้พิมพ์
    หมายเลขนี้ลงเว็บจริง คำว่า MOCK ทำให้ตอนสาธิตดูไม่เหมือนสินค้าที่ซื้อมา
    เช็คซัมคิดจาก brand/โรงเรียน/ลำดับ จึงได้ค่าเดิมทุกครั้งที่รันซ้ำ
    (idempotent เหมือนเดิม) และไม่ชนกันระหว่างโรงเรียน
    """
    letters = re.sub(r"[^A-Za-z]", "", brand).upper() or "IWA"
    prefix = (letters + "XX")[:2]
    digest = hashlib.sha1(
        f"{brand}|{school_idx}|{d_idx}".encode("utf-8")
    ).hexdigest().upper()
    week = purchased.isocalendar()[1]
    return f"{prefix}{purchased:%y}{week:02d}-{digest[:6]}"


#: แหล่งงบประมาณที่โรงเรียนใช้จัดซื้อครุภัณฑ์จริง
BUDGET_SOURCES = (
    "งบอุดหนุนรายหัว",
    "งบลงทุน (ครุภัณฑ์การศึกษา)",
    "เงินรายได้สถานศึกษา",
    "งบอุดหนุน อบจ./เทศบาล",
    "เงินบริจาค/ผ้าป่าเพื่อการศึกษา",
)

#: ผู้ขาย/ผู้ติดตั้งสมมติ พร้อมเบอร์ติดต่อเคลมประกัน
VENDORS = (
    ("บจก. ทิปส์ เอ็ดดูเคชั่น ซัพพลาย", "02-123-4567"),
    ("บจก. สมาร์ทคลาส เทคโนโลยี", "02-234-5678"),
    ("หจก. ไอทีภูมิภาค เซอร์วิส", "043-345-678"),
    ("บจก. เน็ตเวิร์ค โซลูชั่น ไทย", "053-456-789"),
)

#: เงื่อนไขประกันที่พบในสัญญาจัดซื้อของโรงเรียน
WARRANTY_TERMS = (
    "on-site 3 ปี (อะไหล่ + ค่าแรง)",
    "on-site 2 ปี ปีที่ 3 ส่งซ่อมที่ศูนย์",
    "carry-in 1 ปี",
    "on-site 5 ปี เฉพาะพาเนล/จอ",
)

#: อุปกรณ์เครือข่ายมี IP จัดการ — ใส่ไว้ให้ช่างเห็นในหน้ารายละเอียดอุปกรณ์
NETWORK_TYPES = {DeviceType.ROUTER, DeviceType.SWITCH, DeviceType.ACCESS_POINT}


def thai_fiscal_year(d: datetime) -> int:
    """ปีงบประมาณไทย (พ.ศ.) — ปีงบเริ่ม 1 ตุลาคม"""
    year = d.year + 543
    return year + 1 if d.month >= 10 else year


def mock_device_notes(
    *,
    brand: str,
    model: str,
    dev_type: str,
    purchased: datetime,
    warranty: Optional[datetime],
    school_idx: int,
    d_idx: int,
    room,
) -> str:
    """หมายเหตุอุปกรณ์แบบทะเบียนทรัพย์สินจริง

    เดิม notes เป็นข้อความเดียวกันทุกเครื่อง ("ข้อมูลตัวอย่างสำหรับเดโม") ทำให้
    หน้ารายละเอียดอุปกรณ์ไม่มีอะไรให้ดู ตอนนี้ใส่เลขครุภัณฑ์ / แหล่งงบ / ผู้ขาย /
    เงื่อนไขประกัน ซึ่งเป็นข้อมูลที่เจ้าหน้าที่ใช้ตอนเคลมประกันจริง
    ค่าทั้งหมดคิดจาก hash ของ (โรงเรียน, ลำดับ, ยี่ห้อ) จึงคงที่ทุกครั้งที่รันซ้ำ
    """
    seed = int(
        hashlib.sha1(f"notes|{school_idx}|{d_idx}|{brand}".encode("utf-8")).hexdigest()[:8],
        16,
    )
    budget = BUDGET_SOURCES[seed % len(BUDGET_SOURCES)]
    vendor, vendor_tel = VENDORS[(seed // 7) % len(VENDORS)]
    term = WARRANTY_TERMS[(seed // 13) % len(WARRANTY_TERMS)]
    fiscal = thai_fiscal_year(purchased)
    asset_no = f"{7440 + (seed % 60):04d}-{(seed // 3) % 1000:03d}-{d_idx:04d}/{fiscal}"

    lines = [
        f"เลขครุภัณฑ์ {asset_no}",
        f"งบประมาณ: {budget} ปีงบ {fiscal}",
        f"ผู้ขาย/ผู้ติดตั้ง: {vendor} โทร {vendor_tel}",
        f"เงื่อนไขประกัน: {term}",
        f"ตรวจรับเมื่อ {purchased:%d/%m/%Y} — {brand} {model}",
    ]
    if warranty is None:
        lines.append("ประกัน: ยังไม่บันทึกวันสิ้นสุด รอสำเนาใบส่งของจากงานพัสดุ")
    if dev_type in NETWORK_TYPES:
        lines.append(
            f"IP จัดการ: 10.{school_idx}.{(seed % 200) + 1}.{(d_idx % 200) + 10}"
            f" / VLAN {100 + (d_idx % 4) * 10}"
        )
    if room is not None:
        lines.append(f"ติดตั้งที่ {room.name} ({room.code})")
    lines.append("ข้อมูลตัวอย่างสำหรับเดโม (mockup)")
    return "\n".join(lines)

#: บทบาทสำรอง — ฐานข้อมูลบางชุดยังไม่มีค่า owner/admin_school ใน user_role_enum
#: (โมเดลประกาศไว้แล้วแต่ยังไม่ได้ migrate) จึงเลือกค่าที่ใช้ได้จริงตามลำดับนี้
ROLE_FALLBACK: dict[str, tuple[str, ...]] = {
    UserRole.ADMIN_SCHOOL: ("admin_school", "admin", "super_admin"),
    UserRole.IT_SUPPORT: ("it_support", "admin", "super_admin"),
}

SLA_RESOLVE_HOURS = {
    Priority.CRITICAL: 2,
    Priority.HIGH: 8,
    Priority.NORMAL: 24,
    Priority.LOW: 72,
}

REPORTERS = [
    ("ครูสมศรี ใจดี", "somsri@example.ac.th", "081-234-5671"),
    ("ครูวิชัย ตั้งมั่น", "wichai@example.ac.th", "081-234-5672"),
    ("ครูปราณี ทองสุข", "pranee@example.ac.th", "081-234-5673"),
    ("ครูอนันต์ พูลผล", "anan@example.ac.th", "081-234-5674"),
    ("ครูมาลี ศรีสวัสดิ์", "malee@example.ac.th", "081-234-5675"),
    ("ธุรการ กชกร แสงเดือน", "kotchakorn@example.ac.th", "081-234-5676"),
]

SCHOOLS = [
    {
        "code": "SCH-M01",
        "name": "โรงเรียนบ้านหนองปลาไหล",
        "short_name": "หนองปลาไหล",
        "gps": (13.756331, 100.501762),
        "rooms": [
            ("101", "ห้องเรียน ป.1/1", "อาคารเรียน 1", "1"),
            ("102", "ห้องเรียน ป.2/1", "อาคารเรียน 1", "1"),
            ("201", "ห้องคอมพิวเตอร์", "อาคารเรียน 2", "2"),
            ("202", "ห้องเครือข่าย", "อาคารเรียน 2", "2"),
            ("301", "ห้องสมุดดิจิทัล", "อาคารเรียน 3", "3"),
        ],
    },
    {
        "code": "SCH-M02",
        "name": "โรงเรียนอนุบาลเมืองใหม่",
        "short_name": "อนุบาลเมืองใหม่",
        "gps": (18.787747, 98.993128),
        "rooms": [
            ("A11", "ห้องเรียนอนุบาล 1/1", "อาคารอนุบาล", "1"),
            ("A12", "ห้องเรียนอนุบาล 1/2", "อาคารอนุบาล", "1"),
            ("B21", "ห้องปฏิบัติการคอมพิวเตอร์", "อาคารประถม", "2"),
            ("B22", "ห้องสื่อการเรียนรู้", "อาคารประถม", "2"),
            ("C31", "ห้องประชุมเล็ก", "อาคารอำนวยการ", "3"),
        ],
    },
    {
        "code": "SCH-M03",
        "name": "โรงเรียนวัดราษฎร์บำรุง",
        "short_name": "วัดราษฎร์บำรุง",
        "gps": (14.970243, 102.098207),
        "rooms": [
            ("111", "ห้องเรียน ป.3/1", "อาคาร 1", "1"),
            ("112", "ห้องเรียน ป.4/1", "อาคาร 1", "1"),
            ("211", "ห้องคอมพิวเตอร์ 1", "อาคาร 2", "2"),
            ("212", "ห้องพักครู", "อาคาร 2", "2"),
            ("311", "ห้องโสตทัศนูปกรณ์", "อาคาร 3", "3"),
        ],
    },
    {
        "code": "SCH-M04",
        "name": "โรงเรียนเทศบาลสองพี่น้อง",
        "short_name": "เทศบาลสองพี่น้อง",
        "gps": (7.008104, 100.474677),
        "rooms": [
            ("D101", "ห้องเรียน ม.1/1", "อาคารมัธยม", "1"),
            ("D102", "ห้องเรียน ม.1/2", "อาคารมัธยม", "1"),
            ("D201", "ห้องคอมพิวเตอร์ ม.ต้น", "อาคารมัธยม", "2"),
            ("D202", "ห้องเซิร์ฟเวอร์", "อาคารมัธยม", "2"),
            ("E101", "ห้องสมุด", "อาคารกิจกรรม", "1"),
        ],
    },
    {
        "code": "SCH-M05",
        "name": "โรงเรียนสาธิตวิทยาลัยครู",
        "short_name": "สาธิตวิทยาลัยครู",
        "gps": (16.439999, 102.828003),
        "rooms": [
            ("S101", "ห้องเรียนสาธิต 1", "อาคารสาธิต", "1"),
            ("S102", "ห้องเรียนสาธิต 2", "อาคารสาธิต", "1"),
            ("S201", "ห้องปฏิบัติการ IT", "อาคารสาธิต", "2"),
            ("S202", "ห้องควบคุมระบบ", "อาคารสาธิต", "2"),
            ("S301", "ห้องประชุมใหญ่", "อาคารหอประชุม", "3"),
        ],
    },
]

# (device_type, brand, model, room_index) — แม่แบบอุปกรณ์ 20 แบบ ครอบคลุมทุก
# device_type ที่ enum รองรับ; แต่ละโรงเรียนหยิบตามโควตาใน DEVICE_COUNTS และวน
# ซ้ำเป็นชุดที่ 2 ถ้าโควตาเกิน 20 (รวมทั้งระบบ 100 อุปกรณ์)
DEVICE_BLUEPRINT = [
    (DeviceType.INTERACTIVE_DISPLAY, "TIPS", 'iClassBoard 75" 4K', 0),
    (DeviceType.COMPUTER_AIO, "TIPS", "OPS Mini PC i7-13650HX", 0),
    (DeviceType.SPEAKER, "TIPS", "Soundbar + Subwoofer", 0),
    (DeviceType.CAMERA, "TIPS", "AI Camera (built-in)", 0),
    (DeviceType.INTERACTIVE_DISPLAY, "Samsung", "WM75B", 1),
    (DeviceType.COMPUTER_AIO, "HP", "ProOne 440 G9", 1),
    (DeviceType.VISUALIZER, "IPEVO", "V4K Pro", 1),
    (DeviceType.MICROPHONE, "Shure", "MX418", 1),
    (DeviceType.COMPUTER_NOTEBOOK, "Lenovo", "ThinkPad E14 Gen 5", 2),
    (DeviceType.COMPUTER_DESKTOP, "Dell", "OptiPlex 7010", 2),
    (DeviceType.COMPUTER_TABLET, "Samsung", "Galaxy Tab A9+", 2),
    (DeviceType.PRINTER, "Brother", "DCP-T720DW", 2),
    (DeviceType.ROUTER, "MikroTik", "hAP ax3", 3),
    (DeviceType.ACCESS_POINT, "TP-Link", "EAP610", 3),
    (DeviceType.SWITCH, "Cisco", "CBS250-24T", 3),
    (DeviceType.UPS, "APC", "BX1100LI-MS", 3),
    (DeviceType.PROJECTOR, "Epson", "EB-X51", 4),
    (DeviceType.SPEAKER, "JBL", "Control 25-1", 4),
    (DeviceType.SOFTWARE_PICARO, "Picaro", "Picaro Classroom Suite", 4),
    (DeviceType.SOFTWARE_PHONICS_HERO, "Phonics Hero", "Phonics Hero School", 4),
]

# อาการเสียตามชนิดอุปกรณ์: (title, description, symptom_code, ai_category, priority)
#: จำนวนอุปกรณ์ต่อโรงเรียน (เรียงตาม SCHOOLS) — รวมต้องเท่ากับ 100 พอดี
#: ตั้งใจให้ไม่เท่ากัน เพื่อให้แดชบอร์ด/รายงานเห็นความต่างของขนาดโรงเรียนจริง
DEVICE_COUNTS = (10, 15, 20, 25, 30)
assert sum(DEVICE_COUNTS) == 100, "DEVICE_COUNTS ต้องรวมได้ 100 อุปกรณ์"
assert len(DEVICE_COUNTS) == len(SCHOOLS), "DEVICE_COUNTS ต้องมีจำนวนเท่ากับ SCHOOLS"

SYMPTOMS = {
    DeviceType.INTERACTIVE_DISPLAY: [
        ("จอสัมผัสไม่ตอบสนอง", "แตะหน้าจอแล้วเคอร์เซอร์ไม่ขยับ ต้องปิดเปิดเครื่องทุกครั้ง",
         "TOUCH_NO_RESPONSE", "touch", Priority.HIGH),
        ("จอไม่ขึ้นภาพ ไฟสถานะติดค้างสีแดง", "เปิดเครื่องแล้วมีเสียงลำโพงแต่หน้าจอดำสนิท",
         "NO_DISPLAY", "display", Priority.CRITICAL),
        ("ปากกาเขียนขาดเส้น", "เขียนบนกระดานแล้วเส้นขาดช่วง ต้องกดแรงกว่าปกติ",
         "PEN_INACCURATE", "touch", Priority.NORMAL),
    ],
    DeviceType.COMPUTER_AIO: [
        ("เครื่องบูตไม่ขึ้น ค้างที่โลโก้", "ค้างที่โลโก้ผู้ผลิตนานเกิน 10 นาที",
         "BOOT_FAIL", "os", Priority.HIGH),
        ("เครื่องช้ามาก เปิดโปรแกรมนาน", "ใช้งานสอนไม่ทัน ต้องรอโปรแกรมเปิดนานกว่า 2 นาที",
         "SLOW_PERFORMANCE", "performance", Priority.NORMAL),
    ],
    DeviceType.COMPUTER_NOTEBOOK: [
        ("แบตเตอรี่ไม่ชาร์จ", "เสียบสายชาร์จแล้วไฟไม่ติด ใช้ได้เฉพาะตอนเสียบไฟ",
         "BATTERY_FAIL", "power", Priority.NORMAL),
    ],
    DeviceType.COMPUTER_TABLET: [
        ("แท็บเล็ตเชื่อมต่อ Wi-Fi ไม่ได้", "ขึ้นว่าเชื่อมต่อแล้วแต่ไม่มีอินเทอร์เน็ต",
         "WIFI_FAIL", "network", Priority.NORMAL),
    ],
    DeviceType.COMPUTER_DESKTOP: [
        ("เครื่องดับเองระหว่างใช้งาน", "ดับเองวันละ 2-3 ครั้ง ไม่มีสัญญาณเตือนล่วงหน้า",
         "RANDOM_SHUTDOWN", "power", Priority.HIGH),
    ],
    DeviceType.ROUTER: [
        ("อินเทอร์เน็ตหลุดเป็นช่วง ๆ", "หลุดทุก 10-15 นาที ต้องรีสตาร์ตอุปกรณ์",
         "NET_UNSTABLE", "network", Priority.HIGH),
    ],
    DeviceType.ACCESS_POINT: [
        ("สัญญาณ Wi-Fi อ่อนในห้องเรียน", "ยืนห่างจากจุดติดตั้ง 5 เมตรสัญญาณเหลือขีดเดียว",
         "WIFI_WEAK", "network", Priority.NORMAL),
    ],
    DeviceType.SWITCH: [
        ("พอร์ตสวิตช์ใช้ไม่ได้ 2 พอร์ต", "เสียบสาย LAN แล้วไฟพอร์ตไม่ติดทั้งสองช่อง",
         "PORT_DEAD", "network", Priority.HIGH),
    ],
    DeviceType.SPEAKER: [
        ("ลำโพงไม่มีเสียง", "เปิดวิดีโอแล้วไม่มีเสียงออกลำโพง แต่หูฟังใช้ได้",
         "NO_SOUND", "audio", Priority.NORMAL),
        ("เสียงลำโพงแตกพร่า", "เร่งเสียงเกินครึ่งแล้วเสียงแตก",
         "SOUND_DISTORTED", "audio", Priority.LOW),
    ],
    DeviceType.CAMERA: [
        ("กล้องภาพมัว โฟกัสไม่เข้า", "ภาพมัวตลอดเวลา ใช้สอนออนไลน์ไม่ได้",
         "CAM_BLUR", "camera", Priority.NORMAL),
    ],
    DeviceType.VISUALIZER: [
        ("เครื่องฉายภาพวัตถุไม่แสดงภาพ", "ต่อ USB แล้วโปรแกรมมองไม่เห็นอุปกรณ์",
         "USB_NOT_DETECTED", "peripheral", Priority.LOW),
    ],
    DeviceType.MICROPHONE: [
        ("ไมโครโฟนมีเสียงรบกวน", "มีเสียงซ่าดังตลอดเวลาที่เปิดใช้",
         "MIC_NOISE", "audio", Priority.NORMAL),
    ],
    DeviceType.UPS: [
        ("UPS ร้องเตือนตลอดเวลา", "ไฟไม่ดับแต่ UPS ร้องและไฟ Replace Battery ติด",
         "UPS_BATTERY", "power", Priority.HIGH),
    ],
    DeviceType.PRINTER: [
        ("เครื่องพิมพ์กระดาษติด", "กระดาษติดในชุดดึงกระดาษทุกครั้งที่พิมพ์เกิน 5 แผ่น",
         "PAPER_JAM", "printer", Priority.LOW),
    ],
    DeviceType.PROJECTOR: [
        ("โปรเจกเตอร์ภาพซีดจาง", "ภาพจางมาก คาดว่าหลอดใกล้หมดอายุ",
         "LAMP_DIM", "display", Priority.NORMAL),
    ],
    DeviceType.SOFTWARE_PICARO: [
        ("เข้าโปรแกรม Picaro ไม่ได้", "ขึ้นข้อความ license expired ตอนเปิดโปรแกรม",
         "LICENSE_ERROR", "software", Priority.NORMAL),
    ],
    DeviceType.SOFTWARE_PHONICS_HERO: [
        ("Phonics Hero ล็อกอินไม่ผ่าน", "นักเรียนล็อกอินไม่ได้ทั้งห้อง ขึ้นว่ารหัสไม่ถูกต้อง",
         "LOGIN_FAIL", "software", Priority.HIGH),
    ],
}

GENERIC_SYMPTOM = (
    "อุปกรณ์ใช้งานไม่ได้ตามปกติ",
    "ผู้ใช้แจ้งว่าใช้งานไม่ได้ ขอให้เจ้าหน้าที่เข้าตรวจสอบ",
    "GENERAL_FAULT",
    "general",
    Priority.NORMAL,
)

# สถานะที่จะสุ่มให้ ticket (12 ใบต่อโรงเรียน)
TICKET_STATUS_MIX = [
    TicketStatus.NEW,
    TicketStatus.NEW,
    TicketStatus.ASSIGNED,
    TicketStatus.IN_PROGRESS,
    TicketStatus.IN_PROGRESS,
    TicketStatus.PENDING,
    TicketStatus.WAITING_PARTS,
    TicketStatus.RESOLVED,
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED,
    TicketStatus.CLOSED,
    TicketStatus.CANCELLED,
]

# เส้นทางสถานะที่ใช้สร้าง ticket_updates ให้ประวัติสมเหตุสมผล
STATUS_PATH = {
    TicketStatus.NEW: [TicketStatus.NEW],
    TicketStatus.ASSIGNED: [TicketStatus.NEW, TicketStatus.ASSIGNED],
    TicketStatus.IN_PROGRESS: [TicketStatus.NEW, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS],
    TicketStatus.PENDING: [TicketStatus.NEW, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS,
                           TicketStatus.PENDING],
    TicketStatus.WAITING_PARTS: [TicketStatus.NEW, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS,
                                 TicketStatus.WAITING_PARTS],
    TicketStatus.RESOLVED: [TicketStatus.NEW, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS,
                            TicketStatus.RESOLVED],
    TicketStatus.CLOSED: [TicketStatus.NEW, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS,
                          TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.CANCELLED: [TicketStatus.NEW, TicketStatus.CANCELLED],
}

STATUS_NOTE = {
    TicketStatus.NEW: "รับแจ้งจากผู้ใช้ผ่านการสแกน QR",
    TicketStatus.ASSIGNED: "มอบหมายเจ้าหน้าที่ IT เข้าตรวจสอบ",
    TicketStatus.IN_PROGRESS: "เจ้าหน้าที่เข้าหน้างานและเริ่มตรวจสอบอาการ",
    TicketStatus.PENDING: "รอผู้ใช้ยืนยันช่วงเวลาที่เข้าซ่อมได้",
    TicketStatus.WAITING_PARTS: "รออะไหล่จากผู้จำหน่าย ประมาณ 3-5 วันทำการ",
    TicketStatus.RESOLVED: "ซ่อมเสร็จและทดสอบการใช้งานร่วมกับผู้แจ้งแล้ว",
    TicketStatus.CLOSED: "ปิดงานหลังผู้แจ้งยืนยันว่าใช้งานได้ปกติ",
    TicketStatus.CANCELLED: "ยกเลิกงาน — ผู้แจ้งทดลองแก้เบื้องต้นแล้วใช้งานได้",
}

FIXES = [
    ("สาย HDMI ภายในหลวม", "เปลี่ยนสาย HDMI ชุดใหม่และรัดสายใหม่ทั้งชุด", ["สาย HDMI 2.0 ยาว 3 ม."]),
    ("เฟิร์มแวร์ค้างเวอร์ชันเก่า", "อัปเดตเฟิร์มแวร์เป็นเวอร์ชันล่าสุดและรีเซ็ตค่าเริ่มต้น", []),
    ("แบตเตอรี่เสื่อมสภาพ", "เปลี่ยนแบตเตอรี่ชุดใหม่และทดสอบโหลด 30 นาที", ["แบตเตอรี่ 12V 9Ah"]),
    ("ฝุ่นอุดตันชุดระบายความร้อน", "ถอดทำความสะอาดพัดลมและเปลี่ยนซิลิโคนระบายความร้อน", []),
    ("อุปกรณ์กระจายสัญญาณตั้งค่าช่องสัญญาณทับกัน", "ตั้งค่าช่องสัญญาณใหม่และจำกัดกำลังส่ง", []),
]

PM_PLANS = [
    ("ตรวจเช็กจอสัมผัสประจำภาคเรียน", DeviceType.INTERACTIVE_DISPLAY, 120, [
        "ทำความสะอาดหน้าจอและกรอบ IR",
        "ทดสอบความแม่นยำการสัมผัส 9 จุด",
        "ตรวจสายสัญญาณและสายไฟ",
        "ตรวจเวอร์ชันเฟิร์มแวร์",
    ]),
    ("บำรุงรักษาเครื่องคอมพิวเตอร์", DeviceType.COMPUTER_AIO, 90, [
        "ทำความสะอาดภายในเครื่องและพัดลม",
        "ตรวจพื้นที่ดิสก์คงเหลือ",
        "อัปเดตระบบปฏิบัติการและโปรแกรมป้องกันไวรัส",
        "ทดสอบเสียงและพอร์ต USB",
    ]),
    ("ตรวจอุปกรณ์เครือข่ายหลัก", DeviceType.ROUTER, 90, [
        "ตรวจอุณหภูมิและการระบายอากาศ",
        "ตรวจ log ขาดการเชื่อมต่อ",
        "สำรองไฟล์คอนฟิก",
        "ทดสอบความเร็วอินเทอร์เน็ต",
    ]),
    ("ตรวจจุดกระจายสัญญาณ Wi-Fi", DeviceType.ACCESS_POINT, 120, [
        "วัดความแรงสัญญาณกลางห้องเรียน",
        "ตรวจการยึดจุดติดตั้ง",
        "ตรวจช่องสัญญาณทับซ้อน",
    ]),
    ("ตรวจสภาพ UPS และแบตเตอรี่", DeviceType.UPS, 90, [
        "ทดสอบตัดไฟและจับเวลาสำรองไฟ",
        "ตรวจแรงดันแบตเตอรี่",
        "ทำความสะอาดขั้วต่อ",
    ]),
    ("บำรุงรักษาเครื่องพิมพ์", DeviceType.PRINTER, 180, [
        "ทำความสะอาดชุดดึงกระดาษ",
        "ตรวจระดับหมึกและหัวพิมพ์",
        "พิมพ์ทดสอบคุณภาพงานพิมพ์",
    ]),
]


# ---------------------------------------------------------------------------
# ตัวช่วย
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """ต้องให้ผลรูปแบบ ``salt$digest`` เหมือน app.main.hash_password เป๊ะ

    นำมาเขียนซ้ำเพื่อไม่ต้อง import app.main (ซึ่งจะลาก FastAPI/ตัวตั้งค่าทั้งชุดมาด้วย)
    """
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"{salt}${digest}"


_DB_ENUM_CACHE: dict[str, set[str]] = {}


def load_db_enum(db, type_name: str) -> set[str]:
    """label ที่ enum type นั้นรับได้จริงในฐานข้อมูล (cache ไว้ใช้ซ้ำ)

    คืน set ว่างเมื่อไม่พบ type (หรือ backend ไม่ใช่ PostgreSQL) → ผู้เรียกถือว่าผ่าน
    """
    if type_name not in _DB_ENUM_CACHE:
        try:
            rows = db.execute(
                text(
                    "SELECT e.enumlabel FROM pg_type t "
                    "JOIN pg_enum e ON e.enumtypid = t.oid "
                    "WHERE t.typname = :name"
                ),
                {"name": type_name},
            ).scalars().all()
        except Exception:
            rows = []
        _DB_ENUM_CACHE[type_name] = set(rows)
    return _DB_ENUM_CACHE[type_name]


def allowed(db, enum_obj, value: str) -> bool:
    """True เมื่อ value ใช้ได้ทั้งใน SAEnum ของโมเดล และใน enum จริงของฐานข้อมูล"""
    declared = getattr(enum_obj, "enums", None)
    if declared and value not in declared:
        return False
    labels = load_db_enum(db, getattr(enum_obj, "name", "") or "")
    if not labels:
        return True
    return value in labels


def resolve_role(db, role: str) -> str:
    """บทบาทที่ฐานข้อมูลรับได้จริง ตามลำดับความชอบใน ROLE_FALLBACK"""
    labels = load_db_enum(db, "user_role_enum")
    if not labels:
        return role
    for candidate in ROLE_FALLBACK.get(role, (role,)):
        if candidate in labels:
            return candidate
    # ไม่มีค่าใดตรงเลย → ใช้ค่าที่มีอยู่จริงค่าแรก เพื่อไม่ให้ seed ล้มทั้งชุด
    return sorted(labels)[0]


def jdump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def org_code_token(code: Optional[str], org_id: Optional[int]) -> str:
    """รหัสโรงเรียนแบบปลอดภัย (A–Z0–9 ยาวไม่เกิน 8) — ต้องให้ผลตรงกับ
    _org_code_token ใน backend/app/main.py ไม่อย่างนั้นเลข Ticket ที่ seed สร้าง
    จะอยู่คนละ prefix กับที่ API สร้างตอนใช้งานจริง แล้วลำดับจะเริ่มนับใหม่ซ้อนกัน
    """
    token = re.sub(r"[^A-Za-z0-9]", "", (code or "")).upper()[:8]
    if token:
        return token
    return f"ORG{org_id}" if org_id is not None else "SCH"


#: ต้องตรงกับ DEVICE_TYPE_CODES ใน backend/app/main.py — ไม่อย่างนั้นรหัสอุปกรณ์
#: ที่ seed สร้างจะอยู่คนละ prefix กับที่ API สร้าง แล้วลำดับจะเริ่มนับซ้อนกัน
DEVICE_TYPE_CODES = {
    "Interactive Display": "DISP",
    "Computer AIO": "COMP",
    "Computer Notebook": "COMP",
    "Computer Tablet": "COMP",
    "Computer Desktop": "COMP",
    "Router": "RTR",
    "Access Point": "AP",
    "Switch": "SW",
    "Speaker": "SPK",
    "Camera": "CAM",
    "Visualizer": "CAM",
    "Microphone": "MIC",
    "UPS": "UPS",
    "Printer": "PRN",
    "Projector": "PJT",
    "Software (Picaro)": "SW",
    "Software (Phonics Hero)": "SW",
    "Other": "DEV",
}


def device_type_code(device_type: Optional[str]) -> str:
    """รหัสย่อของประเภทอุปกรณ์ — mirror ของ _device_type_code ใน app/main.py"""
    return DEVICE_TYPE_CODES.get(device_type or "", "DEV")


def building_code_token(raw: Optional[str], floor: Optional[str]) -> str:
    """รหัสอาคารย่อสำหรับ device_id — mirror ของ _building_code ใน app/main.py

    'อาคาร 1' → 'B1', 'อาคาร B ชั้น 3' → 'BB', ไม่มีข้อมูล → 'B0'
    """
    if raw:
        s = re.sub(r"[^\u0E00-\u0E7Fa-zA-Z0-9]", "", str(raw)).strip()
        if not s:
            return "B0"
        num = re.search(r"[0-9]+", str(raw))
        if num:
            return f"B{num.group()[:2]}"
        if floor:
            fnum = re.search(r"[0-9]+", str(floor))
            if fnum:
                return f"B{fnum.group()[:2]}"
        latin = re.findall(r"[a-zA-Z]", str(raw))
        if latin:
            return "B" + "".join(latin[:2]).upper()
        return "B" + s[:2].upper()
    if floor:
        fnum = re.search(r"[0-9]+", str(floor))
        if fnum:
            return f"B{fnum.group()[:2]}"
    return "B0"


def device_id_prefix(org: Organization, room: Optional[Room], device_type: str) -> str:
    """prefix ของ device_id: <รหัสโรงเรียน>-<อาคาร>-<ห้อง>-<ประเภท>-

    รหัสอุปกรณ์จึงขึ้นต้นด้วยรหัสของโรงเรียนนั้นเสมอ — อุปกรณ์ตำแหน่งเดียวกัน
    ของสองโรงเรียนจะไม่ได้รหัสเดียวกัน (ตรงกับ generate_device_id ของ API)
    """
    building = building_code_token(room.building if room else None,
                                   room.floor if room else None) if room else "B0"
    room_code = (room.code or "R000") if room else "R000"
    return (
        f"{org_code_token(org.code, org.id)}-{building}-{room_code}-"
        f"{device_type_code(device_type)}-"
    )


#: ชุดอักขระของ ISO 7064 MOD 37,36 — ต้องตรงกับ _CHECK_ALPHABET ใน backend/app/main.py
CHECK_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: คำนำหน้าเลข Ticket — ต้องตรงกับ TICKET_NO_PREFIX ใน backend/app/main.py
TICKET_NO_PREFIX = "TK"


def mod37_36_check_char(payload: str) -> str:
    """ตัวตรวจสอบท้ายเลข Ticket (ISO 7064 MOD 37,36)

    ต้องให้ผลตรงกับ _mod37_36_check_char ใน backend/app/main.py ไม่อย่างนั้น
    เลขที่ seed สร้างจะถูก API มองว่า "กรอกผิด" แล้วเปิดดูไม่ได้เลย
    อักขระคั่น (. - _ /) ถูกข้ามในการคำนวณ
    """
    p = 36
    for ch in (payload or "").upper():
        value = CHECK_ALPHABET.find(ch)
        if value < 0:          # ตัวคั่น — ไม่นับเข้าสูตร
            continue
        p = ((p + value) % 36 or 36) * 2 % 37
    return CHECK_ALPHABET[(37 - p) % 36]


def ticket_no_of(school_token: str, year: int, seq: int, width: int = 4) -> str:
    """ประกอบเลข Ticket: TK.<รหัสโรงเรียน>.<ปี 2 หลัก>.<ลำดับ>-<ตัวตรวจสอบ>

    ต้องให้ผลตรงกับ ticket_no_of ใน backend/app/main.py
    """
    body = f"{TICKET_NO_PREFIX}.{school_token}.{year % 100:02d}.{seq:0{width}d}"
    return f"{body}-{mod37_36_check_char(body)}"


def next_ticket_seq(db, prefix: str) -> int:
    """ลำดับถัดไปของ ticket_id ตาม prefix ที่ส่งมา (อ่านค่าสูงสุดที่มีอยู่)

    prefix มาจาก f"TK.{รหัสโรงเรียน}.{ปี 2 หลัก}." จึงนับแยกกันในแต่ละโรงเรียน
    หางของเลขคือ <ลำดับ>-<ตัวตรวจสอบ> จึงตัดเอาเฉพาะส่วนหน้าขีดมาคิดลำดับ
    ใช้ MAX+1 ไม่ใช่ COUNT+1 เพื่อไม่ให้เลขซ้ำเมื่อมี Ticket กลางลำดับถูกลบ
    (prefix มีแต่ A-Z0-9 กับจุด ซึ่งไม่ใช่ wildcard ของ LIKE จึงใช้ like ได้ตรง ๆ)
    """
    rows = db.execute(
        select(RepairTicket.ticket_id).where(RepairTicket.ticket_id.like(f"{prefix}%"))
    ).scalars().all()
    top = 0
    for tid in rows:
        tail = tid[len(prefix):].split("-", 1)[0]
        if tail.isdigit():
            top = max(top, int(tail))
    return top + 1


def next_pm_seq(db, yyyymm: str) -> int:
    """ลำดับถัดไปของ task_no รูปแบบ PM-YYYYMM-NNNN"""
    prefix = f"PM-{yyyymm}-"
    rows = db.execute(
        select(PMTask.task_no).where(PMTask.task_no.like(f"{prefix}%"))
    ).scalars().all()
    top = 0
    for no in rows:
        tail = no[len(prefix):]
        if tail.isdigit():
            top = max(top, int(tail))
    return top + 1


def symptom_for(rnd: random.Random, device_type: str):
    options = SYMPTOMS.get(device_type)
    if not options:
        return GENERIC_SYMPTOM
    return rnd.choice(options)


def dec(value: float) -> Decimal:
    return Decimal(str(round(value, 6)))


# ---------------------------------------------------------------------------
# purge — ลบเฉพาะข้อมูล mockup ชุดนี้
# ---------------------------------------------------------------------------

def purge(db) -> None:
    codes = [s["code"] for s in SCHOOLS]
    orgs = db.execute(
        select(Organization).where(Organization.code.in_(codes))
    ).scalars().all()

    # audit_logs ไม่มี FK → ลบด้วยแท็กที่สคริปต์นี้ประทับไว้เท่านั้น
    logs = db.execute(
        select(AuditLog).where(AuditLog.user_agent == SEED_TAG)
    ).scalars().all()
    for row in logs:
        db.delete(row)

    plan_names = [p[0] for p in PM_PLANS]
    plans = db.execute(
        select(PMPlan).where(PMPlan.name.in_(plan_names))
    ).scalars().all()

    for org in orgs:
        # ห้อง/อุปกรณ์/ผู้ใช้ ลบตาม cascade ของ relationship
        # pm_tasks / device_health_flags ลบตาม ON DELETE CASCADE ระดับฐานข้อมูล
        db.delete(org)
    db.flush()

    for plan in plans:
        db.delete(plan)

    db.commit()
    print(f"🧹 ลบข้อมูล mockup แล้ว: องค์กร {len(orgs)} แห่ง, แผน PM {len(plans)} แผน, "
          f"audit log {len(logs)} แถว")


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------

def seed(password: str) -> None:
    init_db()
    rnd = random.Random(RND_SEED)
    now = datetime.now(timezone.utc)
    pwd_hash = hash_password(password)

    db = SessionLocal()
    counts = {
        "orgs": 0, "rooms": 0, "devices": 0, "users": 0,
        "tickets": 0, "updates": 0, "pm_plans": 0, "pm_tasks": 0, "flags": 0, "audit": 0,
    }

    try:
        # เลข Ticket แยกลำดับตามโรงเรียน (SC-<รหัสโรงเรียน>-YYYY-NNNN) ให้ตรงกับ
        # generate_ticket_id ใน backend/app/main.py — ลำดับตั้งต้นในลูปแต่ละโรงเรียน
        last_ticket_id = ""
        pm_month = now.strftime("%Y%m")
        pm_seq = next_pm_seq(db, pm_month)

        # ── แผน PM (ใช้ร่วมทุกโรงเรียน) ─────────────────────────────────
        plans_by_type: dict[str, PMPlan] = {}
        for name, dev_type, interval, checklist in PM_PLANS:
            plan = db.execute(
                select(PMPlan).where(PMPlan.name == name)
            ).scalar_one_or_none()
            if plan is None:
                plan = PMPlan(
                    name=name,
                    device_type=dev_type,
                    interval_days=interval,
                    checklist=jdump(checklist),
                    is_active=True,
                )
                db.add(plan)
                counts["pm_plans"] += 1
            plans_by_type[dev_type] = plan
        db.flush()

        for school_idx, school in enumerate(SCHOOLS, start=1):
            org = db.execute(
                select(Organization).where(Organization.code == school["code"])
            ).scalar_one_or_none()
            if org is None:
                org = Organization(
                    code=school["code"],
                    name=school["name"],
                    short_name=school["short_name"],
                    timezone="Asia/Bangkok",
                )
                db.add(org)
                db.flush()
                counts["orgs"] += 1
            else:
                print(f"↺ มี {school['code']} อยู่แล้ว — เติมเฉพาะข้อมูลที่ยังขาด")

            base_lat, base_lng = school["gps"]

            # ── ห้อง ────────────────────────────────────────────────────
            rooms: list[Room] = []
            for r_idx, (code, name, building, floor) in enumerate(school["rooms"]):
                room = db.execute(
                    select(Room).where(
                        Room.organization_id == org.id, Room.code == code
                    )
                ).scalar_one_or_none()
                if room is None:
                    room = Room(
                        organization_id=org.id,
                        code=code,
                        name=name,
                        building=building,
                        floor=floor,
                        gps_lat=dec(base_lat + r_idx * 0.00012),
                        gps_lng=dec(base_lng + r_idx * 0.00012),
                    )
                    db.add(room)
                    db.flush()
                    counts["rooms"] += 1
                rooms.append(room)

            # ── ผู้ใช้ทดสอบของโรงเรียน ──────────────────────────────────
            school_users = [
                (f"sch{school_idx:02d}.admin", f"ผู้ดูแล {school['short_name']}",
                 UserRole.ADMIN_SCHOOL),
                (f"sch{school_idx:02d}.it", f"ช่าง IT {school['short_name']}",
                 UserRole.IT_SUPPORT),
            ]
            created_users: list[User] = []
            for username, display, role in school_users:
                user = db.execute(
                    select(User).where(User.line_user_id == username)
                ).scalar_one_or_none()
                if user is None:
                    db_role = resolve_role(db, role)
                    if db_role != role:
                        print(f"⚠ {username}: ฐานข้อมูลไม่มีบทบาท '{role}' "
                              f"→ ใช้ '{db_role}' แทน")
                    user = User(
                        line_user_id=username,
                        line_display_name=display,
                        line_email=f"{username}@example.ac.th",
                        organization_id=org.id,
                        password_hash=pwd_hash,
                        role=db_role,
                        is_active=True,
                        last_login_at=now - timedelta(hours=rnd.randint(1, 72)),
                    )
                    db.add(user)
                    db.flush()
                    counts["users"] += 1
                created_users.append(user)
            it_user = created_users[-1]
            it_name = it_user.line_display_name or it_user.line_user_id

            # ── อุปกรณ์ตามโควตาของโรงเรียน (DEVICE_COUNTS) ────────────
            # รหัสอุปกรณ์ = <รหัสโรงเรียน>-<อาคาร>-<ห้อง>-<ประเภท>-<ลำดับ>
            devices: list[Device] = []
            # ลำดับต่อ prefix — นับในหน่วยความจำ (ไม่ใช่ MAX+1 จาก DB) เพื่อให้รัน
            # สคริปต์ซ้ำได้รหัสเดิม แล้วเช็ก "มีอยู่แล้ว → ข้าม" ยังทำงานถูก
            device_seq: dict[str, int] = {}
            device_quota = DEVICE_COUNTS[school_idx - 1]
            for d_idx in range(1, device_quota + 1):
                # โรงเรียนที่มีอุปกรณ์เกิน 20 ตัว จะวน DEVICE_BLUEPRINT ซ้ำเป็นชุดที่ 2
                # (device_id / serial ยังไม่ซ้ำ เพราะผูกกับ d_idx ที่เดินต่อเนื่อง)
                bp_idx = (d_idx - 1) % len(DEVICE_BLUEPRINT)
                bp_cycle = (d_idx - 1) // len(DEVICE_BLUEPRINT)
                dev_type, brand, model, room_index = DEVICE_BLUEPRINT[bp_idx]
                if bp_cycle:
                    model = f"{model} (ชุดที่ {bp_cycle + 1})"
                dev_room = rooms[room_index] if room_index < len(rooms) else None
                dev_prefix = device_id_prefix(org, dev_room, dev_type)
                device_seq[dev_prefix] = device_seq.get(dev_prefix, 0) + 1
                device_id = f"{dev_prefix}{device_seq[dev_prefix]:02d}"
                device = db.execute(
                    select(Device).where(Device.device_id == device_id)
                ).scalar_one_or_none()
                if device is not None:
                    devices.append(device)
                    continue

                purchased = now - timedelta(days=rnd.randint(200, 1800))
                # 2 ตัวต่อโรงเรียนตั้งใจให้ประกันหมดใน 30 วัน → PM Rule 2 มีข้อมูลจับ
                # ชุดประกันครอบคลุมทุกสถานะที่หน้า "ตรวจสอบประกัน" แสดงได้
                #   d_idx 5, 13 -> ใกล้หมดภายใน 30 วัน (PM Rule 2 ต้องจับได้ด้วย)
                #   d_idx 3     -> หมดประกันแล้ว
                #   d_idx 9     -> ไม่มีวันสิ้นสุดประกัน (ข้อมูลไม่ครบเหมือนของจริง)
                warranty: Optional[datetime]
                if d_idx in (5, 13):
                    warranty = now + timedelta(days=rnd.randint(5, 28))
                elif d_idx == 3:
                    warranty = now - timedelta(days=rnd.randint(40, 400))
                elif d_idx == 9:
                    warranty = None
                else:
                    warranty = purchased + timedelta(days=rnd.choice([1095, 1460, 1825]))

                status = DeviceStatus.ACTIVE
                if d_idx == device_quota and school_idx == 5:
                    status = DeviceStatus.INACTIVE

                device = Device(
                    device_id=device_id,
                    organization_id=org.id,
                    room_id=dev_room.id if dev_room else None,
                    device_type=dev_type,
                    brand=brand,
                    model=model,
                    serial_number=mock_serial(brand, purchased, school_idx, d_idx),
                    firmware_version=rnd.choice(["1.0.2", "2.4.1", "3.1.0", "5.6", "N/A"]),
                    status=status,
                    qr_token=secrets.token_hex(16),
                    purchase_date=purchased,
                    warranty_until=warranty,
                    notes=mock_device_notes(
                        brand=brand,
                        model=model,
                        dev_type=dev_type,
                        purchased=purchased,
                        warranty=warranty,
                        school_idx=school_idx,
                        d_idx=d_idx,
                        room=dev_room,
                    ),
                    created_at=purchased,
                )
                db.add(device)
                db.flush()
                counts["devices"] += 1
                devices.append(device)

            if not devices:
                continue

            # ── ใบแจ้งซ่อม 12 ใบ + ชุดซ่อมซ้ำ ───────────────────────────
            ticket_token = org_code_token(org.code, org.id)
            ticket_prefix = f"{TICKET_NO_PREFIX}.{ticket_token}.{now.year % 100:02d}."
            ticket_seq = next_ticket_seq(db, ticket_prefix)

            ticket_plan: list[tuple[Device, str, datetime]] = []
            for i, status in enumerate(TICKET_STATUS_MIX):
                device = devices[(i * 3 + school_idx) % len(devices)]
                created = now - timedelta(
                    days=rnd.randint(2, 120), hours=rnd.randint(0, 9), minutes=rnd.randint(0, 59)
                )
                ticket_plan.append((device, status, created))

            # โรงเรียน 1-2: ทำให้อุปกรณ์ตัวแรกมีงานซ่อมซ้ำ 3 ใบใน 90 วัน (Rule 1)
            repeated_device = devices[0] if school_idx <= 2 else None
            if repeated_device is not None:
                for k in range(3):
                    ticket_plan.append((
                        repeated_device,
                        TicketStatus.CLOSED,
                        now - timedelta(days=15 + k * 20, hours=rnd.randint(0, 8)),
                    ))

            for device, status, created in ticket_plan:
                if not allowed(db, ticket_status_enum, status):
                    continue
                title, description, symptom_code, ai_category, priority = symptom_for(
                    rnd, device.device_type
                )
                if not allowed(db, priority_enum, priority):
                    priority = Priority.NORMAL

                reporter = rnd.choice(REPORTERS)
                sla_hours = SLA_RESOLVE_HOURS.get(priority, 24)
                sla_due = created + timedelta(hours=sla_hours)

                ticket = RepairTicket(
                    ticket_id=ticket_no_of(ticket_token, now.year, ticket_seq),
                    organization_id=org.id,
                    device_id=device.device_id,
                    reporter_name=reporter[0],
                    reporter_email=reporter[1],
                    reporter_phone=reporter[2],
                    reporter_type="teacher",
                    title=title,
                    description=description,
                    priority=priority,
                    status=status,
                    channel=rnd.choice(["qr", "line", "web"]),
                    symptom_code=symptom_code,
                    ai_category=ai_category,
                    scan_gps_lat=dec(base_lat + rnd.uniform(-0.0004, 0.0004)),
                    scan_gps_lng=dec(base_lng + rnd.uniform(-0.0004, 0.0004)),
                    scan_timestamp=created,
                    sla_due_at=sla_due,
                    escalation_level=1 if priority == Priority.CRITICAL else 0,
                    created_at=created,
                )
                last_ticket_id = ticket.ticket_id
                ticket_seq += 1

                path = STATUS_PATH.get(status, [TicketStatus.NEW])
                if len(path) > 1:
                    ticket.assigned_to = it_name

                if status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
                    root_cause, solution, parts = rnd.choice(FIXES)
                    resolved = created + timedelta(
                        hours=max(1, int(sla_hours * rnd.uniform(0.4, 1.6)))
                    )
                    if resolved > now:
                        resolved = now - timedelta(hours=1)
                    ticket.root_cause = root_cause
                    ticket.solution = solution
                    ticket.parts_used = jdump(parts)
                    ticket.resolution_notes = "ทดสอบการใช้งานร่วมกับผู้แจ้งเรียบร้อย"
                    ticket.resolved_at = resolved
                    ticket.sla_met = resolved <= sla_due
                    if status == TicketStatus.CLOSED:
                        ticket.closed_at = resolved + timedelta(hours=rnd.randint(2, 36))
                        ticket.rating = rnd.randint(4, 5)
                        ticket.feedback = rnd.choice([
                            "เจ้าหน้าที่มาเร็ว แก้ไขเรียบร้อยดี",
                            "ใช้งานได้ปกติแล้ว ขอบคุณครับ",
                            "อธิบายวิธีป้องกันปัญหาซ้ำให้ด้วย ดีมาก",
                        ])
                elif status == TicketStatus.CANCELLED:
                    ticket.resolution_notes = "ผู้แจ้งแก้ไขเบื้องต้นได้เองแล้ว"

                db.add(ticket)
                db.flush()
                counts["tickets"] += 1

                # ประวัติเปลี่ยนสถานะ
                span_end = ticket.closed_at or ticket.resolved_at or min(
                    now, created + timedelta(hours=sla_hours)
                )
                total_steps = max(1, len(path) - 1)
                step = (span_end - created) / total_steps
                prev = None
                for s_idx, state in enumerate(path):
                    db.add(TicketUpdate(
                        ticket_id=ticket.id,
                        from_status=prev,
                        to_status=state,
                        note=STATUS_NOTE.get(state, ""),
                        author_name=reporter[0] if state == TicketStatus.NEW else it_name,
                        author_role="reporter" if state == TicketStatus.NEW else "it_support",
                        created_at=created + step * s_idx,
                    ))
                    counts["updates"] += 1
                    prev = state

            # ── งาน PM คละสถานะ ────────────────────────────────────────
            pm_targets = [d for d in devices if d.device_type in plans_by_type][:6]
            pm_statuses = ["pending", "pending", "overdue", "done", "done", "skipped"]
            for t_idx, device in enumerate(pm_targets):
                plan = plans_by_type[device.device_type]
                status = pm_statuses[t_idx % len(pm_statuses)]
                task_no = f"PM-{pm_month}-{pm_seq:04d}"
                pm_seq += 1

                if status == "overdue":
                    due = now - timedelta(days=rnd.randint(3, 25))
                elif status in ("done", "skipped"):
                    due = now - timedelta(days=rnd.randint(5, 40))
                else:
                    due = now + timedelta(days=rnd.randint(3, 45))

                task = PMTask(
                    task_no=task_no,
                    plan_id=plan.id,
                    device_id=device.device_id,
                    organization_id=org.id,
                    due_date=due,
                    status=status,
                )
                if status == "done":
                    checklist = json.loads(plan.checklist or "[]")
                    task.result = jdump([
                        {"item": item, "value": True, "note": ""} for item in checklist
                    ])
                    task.photos = jdump([])
                    task.done_by = it_name
                    task.done_at = due + timedelta(hours=rnd.randint(1, 30))
                    task.next_due = task.done_at + timedelta(days=plan.interval_days)
                elif status == "skipped":
                    task.skip_reason = "โรงเรียนปิดภาคเรียน เข้าพื้นที่ไม่ได้ในรอบนี้"
                    task.done_by = it_name
                    task.done_at = due + timedelta(days=1)

                db.add(task)
                counts["pm_tasks"] += 1

            # ── device_health_flags ตัวอย่างครบทั้ง 3 กฎ ─────────────────
            flag_specs = []
            if repeated_device is not None:
                flag_specs.append((
                    repeated_device, "REPEATED_FAILURE", "critical",
                    f"อุปกรณ์ {repeated_device.device_id} มีงานซ่อม 3 ครั้งใน 90 วัน",
                    {"ticket_count": 3, "window_days": 90}, "open",
                ))
            warranty_device = devices[4] if len(devices) > 4 else devices[0]
            flag_specs.append((
                warranty_device, "WARRANTY_EXPIRING", "warning",
                f"ประกันของ {warranty_device.device_id} จะหมดภายใน 30 วัน",
                {
                    "warranty_until": warranty_device.warranty_until.isoformat()
                    if warranty_device.warranty_until else None
                },
                "open",
            ))
            if len(devices) > 9:
                old_device = devices[9]
                flag_specs.append((
                    old_device, "REPLACEMENT_CANDIDATE", "info",
                    f"อุปกรณ์ {old_device.device_id} อายุการใช้งานเกินเกณฑ์ ควรพิจารณาเปลี่ยนเครื่อง",
                    {"age_days": (now - (old_device.purchase_date or old_device.created_at)).days},
                    "acknowledged",
                ))

            for device, rule_code, severity, message, detail, flag_status in flag_specs:
                exists = db.execute(
                    select(DeviceHealthFlag).where(
                        DeviceHealthFlag.device_id == device.device_id,
                        DeviceHealthFlag.rule_code == rule_code,
                        DeviceHealthFlag.status == flag_status,
                    )
                ).scalar_one_or_none()
                if exists is not None:
                    continue
                db.add(DeviceHealthFlag(
                    device_id=device.device_id,
                    organization_id=org.id,
                    rule_code=rule_code,
                    severity=severity,
                    message=message,
                    detail=detail,
                    status=flag_status,
                    acknowledged_by=it_name if flag_status != "open" else None,
                    created_at=now - timedelta(days=rnd.randint(1, 20)),
                ))
                counts["flags"] += 1

            # ── audit_logs ตัวอย่าง (ติดแท็กไว้ให้ purge ได้) ────────────
            audit_rows = [
                ("login", "user", str(it_user.id), None,
                 {"username": it_user.line_user_id, "result": "success"}),
                ("device_create", "device", devices[0].device_id, None,
                 {"device_id": devices[0].device_id, "device_type": devices[0].device_type}),
                # fallback ใช้ ticket_no_of ตัวเดียวกับของจริง ไม่ประกอบเลขรูปแบบเก่าเอง
                ("ticket_status_change", "ticket",
                 last_ticket_id or ticket_no_of(ticket_token, now.year, 1),
                 {"status": "in_progress"}, {"status": "resolved"}),
                ("pm_task_submit", "pm_task", f"PM-{pm_month}-{max(1, pm_seq - 1):04d}", None,
                 {"status": "done", "device_id": pm_targets[0].device_id if pm_targets else None}),
            ]
            for action, entity_type, entity_id, old_value, new_value in audit_rows:
                db.add(AuditLog(
                    user_id=it_user.id,
                    user_name=it_name,
                    user_role=it_user.role,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    old_value=jdump(old_value) if old_value is not None else None,
                    new_value=jdump(new_value) if new_value is not None else None,
                    ip_address="203.0.113.%d" % rnd.randint(2, 250),
                    user_agent=SEED_TAG,
                    created_at=now - timedelta(days=rnd.randint(0, 30), hours=rnd.randint(0, 23)),
                ))
                counts["audit"] += 1

            db.flush()

        db.commit()

        print("\n✅ สร้างข้อมูล mockup เรียบร้อย")
        print(f"   องค์กรใหม่        : {counts['orgs']}")
        print(f"   ห้องใหม่          : {counts['rooms']}")
        print(f"   อุปกรณ์ใหม่       : {counts['devices']}")
        print(f"   ผู้ใช้ทดสอบใหม่    : {counts['users']}")
        print(f"   ใบแจ้งซ่อมใหม่     : {counts['tickets']} (ประวัติสถานะ {counts['updates']} แถว)")
        print(f"   แผน PM ใหม่       : {counts['pm_plans']} / งาน PM {counts['pm_tasks']}")
        print(f"   health flags      : {counts['flags']}")
        print(f"   audit logs        : {counts['audit']}")
        print(f"\n   บัญชีทดสอบ: sch01.admin … sch05.admin / sch01.it … sch05.it")
        print("   รหัสผ่าน  : ใช้ค่าที่กำหนดตอนรัน (ไม่แสดงใน log)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="สร้างข้อมูล mockup 5 โรงเรียน / 100 อุปกรณ์ สำหรับเดโมและทดสอบ"
    )
    parser.add_argument(
        "--password", default=os.environ.get("MOCK_PASSWORD"),
        help="รหัสผ่านบัญชีทดสอบ local (หรือกำหนด MOCK_PASSWORD)",
    )
    parser.add_argument(
        "--purge", action="store_true",
        help="ลบข้อมูล mockup ชุดนี้ (องค์กร SCH-M01..M05, แผน PM, audit ที่ติดแท็ก) ก่อนสร้างใหม่",
    )
    parser.add_argument(
        "--purge-only", action="store_true",
        help="ลบข้อมูล mockup แล้วจบ ไม่สร้างใหม่",
    )
    args = parser.parse_args()

    require_local_demo_database()

    if not args.password or len(args.password) < 12:
        parser.error("ต้องกำหนดรหัสผ่านบัญชีทดสอบอย่างน้อย 12 ตัวอักษร")

    if args.purge or args.purge_only:
        init_db()
        db = SessionLocal()
        try:
            purge(db)
        finally:
            db.close()
        if args.purge_only:
            return

    seed(args.password)


if __name__ == "__main__":
    main()
