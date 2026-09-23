#!/usr/bin/env python3
"""seed_db.py — ใส่ข้อมูลอุปกรณ์ตัวอย่าง (องค์กร/ห้อง/อุปกรณ์) ลง PostgreSQL
ใช้: python scripts/seed_db.py
ปลายทางคือ DATABASE_URL ของ app.models (ค่าเริ่มต้น: postgres@localhost:5432/smart_classroom)

รหัสอุปกรณ์ไม่ฮาร์ดโค้ดแล้ว — ขอจาก generate_device_id ของ API ตัวเดียวกัน จึงได้
รูปแบบ <รหัสโรงเรียน>-<อาคาร>-<ห้อง>-<ประเภท>-<ลำดับ> เหมือนอุปกรณ์ที่สร้างผ่านหน้าเว็บ
(เดิม seed ใส่ DEV-2024-00xxx ซึ่งไม่ผูกกับโรงเรียน/ห้อง และต้องตามแก้ด้วย
scripts/migrate_device_ids.py ทีหลัง)
"""

import os
import sys
from datetime import datetime, timezone

# สคริปต์อยู่ที่ backend/scripts/ → path ที่ต้องเพิ่มคือ backend/ (พาเรนต์) ไม่ใช่ backend/backend
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

from app.models import (
    Device,
    DeviceType,
    DeviceStatus,
    Organization,
    Room,
    init_db,
    SessionLocal,
)
from demo_safety import require_local_demo_database

def seed() -> None:
    require_local_demo_database()
    # import ในฟังก์ชัน: app.main ดึง FastAPI app ทั้งก้อนมาด้วย ไม่ควรโหลดตอน import สคริปต์
    from app.main import generate_device_id

    init_db()

    db = SessionLocal()
    try:
        if db.query(Device).first():
            print("⚠ มีข้อมูลอยู่แล้ว — ข้ามการ seed")
            return

        org = Organization(
            code="SCH-DEMO",
            name="โรงเรียนสาธิตแห่งหนึ่ง",
            short_name="สาธิต",
        )
        db.add(org)
        db.flush()

        rooms = [
            Room(code="301", name="ห้องเรียนปฐมวัย 301", building="อาคาร A", floor="3", organization_id=org.id),
            Room(code="302", name="ห้องเรียนปฐมวัย 302", building="อาคาร A", floor="3", organization_id=org.id),
            Room(code="201", name="ห้องคอมพิวเตอร์ 201", building="อาคาร B", floor="2", organization_id=org.id),
        ]
        for r in rooms:
            db.add(r)
        db.flush()

        # ไม่มีคีย์ device_id — ลำดับมาจาก generate_device_id ตอนสร้างทีละตัว
        devices_data = [
            dict(
                room_code="301",
                device_type=DeviceType.INTERACTIVE_DISPLAY,
                brand="TIPS",
                model='iClassBoard 75" 4K',
                serial_number="ICB-75-2024-00123",
                firmware_version="2.4.1",
                notes="จอภาพระบบสัมผัส 75 นิ้ว 4K IR Touch 40 จุด, Android 13 + Windows OPS",
            ),
            dict(
                room_code="301",
                device_type=DeviceType.COMPUTER_AIO,
                brand="TIPS",
                model="OPS Mini PC i7-13650HX",
                serial_number="OPS-2024-00124",
                firmware_version="N/A",
                notes="Intel Core i7-13650HX, RAM 8GB, 256GB SSD (OPS slot)",
            ),
            dict(
                room_code="302",
                device_type=DeviceType.INTERACTIVE_DISPLAY,
                brand="TIPS",
                model='iClassBoard 75" 4K',
                serial_number="ICB-75-2024-00201",
                firmware_version="2.4.1",
            ),
            dict(
                room_code="201",
                device_type=DeviceType.ROUTER,
                brand="TP-Link",
                model="Archer AX55",
                serial_number="Archer-AX55-00301",
                firmware_version="1.2.3",
                notes="WiFi 6 + AP",
            ),
            dict(
                room_code="201",
                device_type=DeviceType.ACCESS_POINT,
                brand="TP-Link",
                model="EAP610",
                serial_number="EAP610-00302",
                firmware_version="3.0.0",
            ),
            dict(
                room_code="301",
                device_type=DeviceType.SPEAKER,
                brand="TIPS",
                model="ชุดลำโพงซาวด์บาร์ + Subwoofer",
                serial_number="SPK-SB-00401",
            ),
            dict(
                room_code="301",
                device_type=DeviceType.CAMERA,
                brand="TIPS",
                model="AI Camera (built-in)",
                serial_number="AICAM-00402",
                firmware_version="1.0.0",
                notes="กล้อง AI ในตัวจอ, 4800M, 120° FOV, Auto-framing",
            ),
            dict(
                room_code="301",
                device_type=DeviceType.UPS,
                brand="APC",
                model="Back-UPS 650VA",
                serial_number="APC-650-00501",
            ),
            dict(
                room_code="301",
                device_type=DeviceType.PRINTER,
                brand="Epson",
                model="L3250 Ink Tank",
                serial_number="EPSON-L3250-00601",
                notes="Printer/Copier/Scanner, WiFi",
            ),
            dict(
                room_code="201",
                device_type=DeviceType.COMPUTER_NOTEBOOK,
                brand="Acer",
                model="Aspire 3",
                serial_number="ACER-A3-00701",
                notes="Notebook 5 เครื่อง, ใช้ในห้องคอมฯ",
            ),
            dict(
                room_code="301",
                device_type=DeviceType.SOFTWARE_PICARO,
                brand="Cambridge English",
                model="Picaro - The Online English Adventure",
                serial_number="PICARO-SCHOOL-00801",
                firmware_version="4.x",
                notes="CEFR Pre-A1-A2, 4 Level, LMS, 80 บทเรียน",
                warranty_until=datetime(2027, 8, 3, tzinfo=timezone.utc),
            ),
            dict(
                room_code="301",
                device_type=DeviceType.SOFTWARE_PHONICS_HERO,
                brand="Phonics Hero",
                model="Phonics Hero",
                serial_number="PH-HERO-00901",
                firmware_version="3.x",
                notes="Synthetic Phonics, 44 เสียง, 800+ เกม, 3 Part 26 Level",
                warranty_until=datetime(2027, 8, 3, tzinfo=timezone.utc),
            ),
        ]

        created_ids = []
        for d in devices_data:
            # กรองด้วย organization_id ด้วย ไม่ใช่รหัสห้องอย่างเดียว — รหัสห้องซ้ำกันได้
            # ระหว่างโรงเรียน ถ้า seed นี้ถูกรันตอนมีโรงเรียนอื่นอยู่แล้ว
            room = (
                db.query(Room)
                .filter(Room.organization_id == org.id, Room.code == d["room_code"])
                .first()
            )
            device = Device(
                device_id=generate_device_id(db, org, room, d["device_type"]),
                organization_id=org.id,
                room_id=room.id if room else None,
                device_type=d["device_type"],
                brand=d.get("brand"),
                model=d.get("model"),
                serial_number=d.get("serial_number"),
                firmware_version=d.get("firmware_version"),
                status=DeviceStatus.ACTIVE,
                notes=d.get("notes"),
                warranty_until=d.get("warranty_until"),
            )
            db.add(device)
            # flush ทุกตัว: generate_device_id หาเลขจาก MAX ในตาราง devices ถ้าไม่ flush
            # อุปกรณ์ประเภทเดียวกันในห้องเดียวกันจะได้ลำดับ 01 ซ้ำกันทั้งกลุ่ม
            db.flush()
            created_ids.append(device.device_id)
        db.commit()

        print(f"✅ ใส่ข้อมูลครบ: 1 องค์กร, {len(rooms)} ห้อง, {len(devices_data)} อุปกรณ์")
        for did in created_ids:
            print(f"   {did}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
