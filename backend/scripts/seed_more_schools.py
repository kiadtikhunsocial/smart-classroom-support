#!/usr/bin/env python3
"""seed_more_schools.py — เพิ่มโรงเรียนเพิ่มเติม + อุปกรณ์ + tickets สำหรับทดสอบ multi-school admin
ใช้: python seed_more_schools.py
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app.models import (
    Base,
    Device,
    DeviceType,
    DeviceStatus,
    Organization,
    RepairTicket,
    Room,
    TicketStatus,
    Priority,
    engine,
    SessionLocal,
)


def seed() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        existing = db.query(Organization).all()
        print(f"มีองค์กรอยู่แล้ว: {[o.code for o in existing]}")

        new_orgs = [
            {
                "code": "SCH-02",
                "name": "โรงเรียนอนุบาลร่มเกล้า",
                "short_name": "ร่มเกล้า",
                "rooms": [
                    ("101", "ห้องเรียน ป.1/1", "อาคาร 1", "1"),
                    ("102", "ห้องเรียน ป.1/2", "อาคาร 1", "1"),
                    ("201", "ห้องคอมพิวเตอร์", "อาคาร 2", "2"),
                ],
                "devices": [
                    dict(device_id="DEV-2025-00101", room_code="101", device_type=DeviceType.INTERACTIVE_DISPLAY, brand="Samsung", model="WM75B", serial_number="SAM-WM75-00101"),
                    dict(device_id="DEV-2025-00102", room_code="101", device_type=DeviceType.COMPUTER_AIO, brand="HP", model="ProOne 440", serial_number="HP-440-00102"),
                    dict(device_id="DEV-2025-00201", room_code="201", device_type=DeviceType.COMPUTER_NOTEBOOK, brand="Lenovo", model="ThinkPad E14", serial_number="LNV-E14-00201"),
                    dict(device_id="DEV-2025-00202", room_code="201", device_type=DeviceType.ROUTER, brand="MikroTik", model="hAP ax3", serial_number="MTK-AX3-00202"),
                    dict(device_id="DEV-2025-00301", room_code="102", device_type=DeviceType.SPEAKER, brand="JBL", model="Control 25", serial_number="JBL-C25-00301"),
                ],
                "tickets": [
                    dict(title="จอภาพไม่ติด", description="เปิดจอแล้วไม่มีภาพ", priority=Priority.HIGH, status=TicketStatus.IN_PROGRESS, reporter_name="ครูอารยา", device_id="DEV-2025-00101"),
                    dict(title="Wi-Fi ในห้องคอมไม่เข้า", description="นักเรียนเชื่อมต่อไม่ได้", priority=Priority.MEDIUM, status=TicketStatus.OPEN, reporter_name="ครูสมชาย", device_id="DEV-2025-00202"),
                ],
            },
            {
                "code": "SCH-03",
                "name": "โรงเรียนวัดศรีสุวรรณ",
                "short_name": "วัดศรีฯ",
                "rooms": [
                    ("A101", "ห้องเรียน ม.1/1", "อาคาร A", "1"),
                ],
                "devices": [
                    dict(device_id="DEV-2025-01001", room_code="A101", device_type=DeviceType.INTERACTIVE_DISPLAY, brand="ViewSonic", model="IFP7550", serial_number="VS-IFP75-01001"),
                    dict(device_id="DEV-2025-01002", room_code="A101", device_type=DeviceType.UPS, brand="Vertiv", model="GXT3 1kVA", serial_number="VTX-1K-01002"),
                ],
                "tickets": [
                    dict(title="เครื่องเสียงไม่ดัง", description="ลำโพงไม่มีเสียงออก", priority=Priority.CRITICAL, status=TicketStatus.OPEN, reporter_name="ครูมาลี", device_id="DEV-2025-01001"),
                ],
            },
        ]

        created = 0
        for org_data in new_orgs:
            # ข้ามถ้าซ้ำ
            if db.query(Organization).filter(Organization.code == org_data["code"]).first():
                print(f"⏭ {org_data['code']} มีอยู่แล้ว — ข้าม")
                continue

            org = Organization(
                code=org_data["code"],
                name=org_data["name"],
                short_name=org_data["short_name"],
            )
            db.add(org)
            db.flush()

            room_map = {}
            for code, name, building, floor in org_data["rooms"]:
                room = Room(code=code, name=name, building=building, floor=floor, organization_id=org.id)
                db.add(room)
                db.flush()
                room_map[code] = room

            for d in org_data["devices"]:
                room = room_map.get(d["room_code"])
                device = Device(
                    device_id=d["device_id"],
                    organization_id=org.id,
                    room_id=room.id if room else None,
                    device_type=d["device_type"],
                    brand=d.get("brand"),
                    model=d.get("model"),
                    serial_number=d.get("serial_number"),
                    status=DeviceStatus.ACTIVE,
                )
                db.add(device)
                db.flush()

            ticket_counter = 1
            for t in org_data["tickets"]:
                dev = db.query(Device).filter(Device.device_id == t["device_id"]).first()
                if not dev:
                    continue
                ticket = RepairTicket(
                    ticket_id=f"TK-2026-{org.id:03d}-{str(ticket_counter).zfill(2)}",
                    organization_id=org.id,
                    device_id=dev.device_id,
                    title=t["title"],
                    description=t.get("description"),
                    priority=t["priority"],
                    status=t["status"],
                    reporter_name=t["reporter_name"],
                    created_at=datetime.now(timezone.utc),
                )
                db.add(ticket)
                ticket_counter += 1

            created += 1
            print(f"✅ {org_data['code']} {org_data['name']} — {len(org_data['devices'])} อุปกรณ์, {len(org_data['tickets'])} tickets")

        db.commit()
        print(f"\nเสร็จ: เพิ่ม {created} องค์กรใหม่")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
