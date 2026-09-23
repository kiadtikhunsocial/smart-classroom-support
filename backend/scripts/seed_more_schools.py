#!/usr/bin/env python3
"""seed_more_schools.py — เพิ่มโรงเรียนเพิ่มเติม + อุปกรณ์ + tickets สำหรับทดสอบ multi-school admin
ใช้: python scripts/seed_more_schools.py

รหัสอุปกรณ์และเลข Ticket ไม่ฮาร์ดโค้ด — ขอจากตัวสร้างของ API (generate_device_id /
generate_ticket_id) จึงได้รูปแบบเดียวกับข้อมูลจริง อุปกรณ์กับ ticket ในสคริปต์นี้
อ้างถึงกันด้วยคีย์ภายใน "ref" แล้วแมปเป็นรหัสที่สร้างได้จริงตอนรัน
"""

import os
import sys
from datetime import datetime, timezone

# สคริปต์อยู่ที่ backend/scripts/ → path ที่ต้องเพิ่มคือ backend/ (พาเรนต์)
# ไม่ใช่โฟลเดอร์ของสคริปต์เอง ไม่อย่างนั้น import app.models ไม่เจอ
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

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
from demo_safety import require_local_demo_database


def seed() -> None:
    require_local_demo_database()
    # import ในฟังก์ชัน: app.main ดึง FastAPI app ทั้งก้อนมาด้วย ไม่ควรโหลดตอน import สคริปต์
    # ใช้ตัวสร้างกลางเพื่อให้ข้อมูลทดสอบได้เลขรูปแบบเดียวกับของจริง
    # (TK.<รหัสโรงเรียน>.<ปี 2 หลัก>.<ลำดับ>-<ตัวตรวจสอบ> และ
    #  <รหัสโรงเรียน>-<อาคาร>-<ห้อง>-<ประเภท>-<ลำดับ>)
    from app.main import generate_device_id, generate_ticket_id
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
                    dict(ref="disp-101", room_code="101", device_type=DeviceType.INTERACTIVE_DISPLAY, brand="Samsung", model="WM75B", serial_number="SAM-WM75-00101"),
                    dict(ref="aio-101", room_code="101", device_type=DeviceType.COMPUTER_AIO, brand="HP", model="ProOne 440", serial_number="HP-440-00102"),
                    dict(ref="nb-201", room_code="201", device_type=DeviceType.COMPUTER_NOTEBOOK, brand="Lenovo", model="ThinkPad E14", serial_number="LNV-E14-00201"),
                    dict(ref="rtr-201", room_code="201", device_type=DeviceType.ROUTER, brand="MikroTik", model="hAP ax3", serial_number="MTK-AX3-00202"),
                    dict(ref="spk-102", room_code="102", device_type=DeviceType.SPEAKER, brand="JBL", model="Control 25", serial_number="JBL-C25-00301"),
                ],
                "tickets": [
                    dict(title="จอภาพไม่ติด", description="เปิดจอแล้วไม่มีภาพ", priority=Priority.HIGH, status=TicketStatus.IN_PROGRESS, reporter_name="ครูอารยา", device_ref="disp-101"),
                    dict(title="Wi-Fi ในห้องคอมไม่เข้า", description="นักเรียนเชื่อมต่อไม่ได้", priority=Priority.NORMAL, status=TicketStatus.NEW, reporter_name="ครูสมชาย", device_ref="rtr-201"),
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
                    dict(ref="disp-a101", room_code="A101", device_type=DeviceType.INTERACTIVE_DISPLAY, brand="ViewSonic", model="IFP7550", serial_number="VS-IFP75-01001"),
                    dict(ref="ups-a101", room_code="A101", device_type=DeviceType.UPS, brand="Vertiv", model="GXT3 1kVA", serial_number="VTX-1K-01002"),
                ],
                "tickets": [
                    dict(title="เครื่องเสียงไม่ดัง", description="ลำโพงไม่มีเสียงออก", priority=Priority.CRITICAL, status=TicketStatus.NEW, reporter_name="ครูมาลี", device_ref="disp-a101"),
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

            # ref → รหัสอุปกรณ์จริงที่สร้างได้ ใช้ผูก ticket ทีหลัง
            device_ids: dict[str, str] = {}
            for d in org_data["devices"]:
                room = room_map.get(d["room_code"])
                device = Device(
                    device_id=generate_device_id(db, org, room, d["device_type"]),
                    organization_id=org.id,
                    room_id=room.id if room else None,
                    device_type=d["device_type"],
                    brand=d.get("brand"),
                    model=d.get("model"),
                    serial_number=d.get("serial_number"),
                    status=DeviceStatus.ACTIVE,
                )
                db.add(device)
                # flush ทุกตัว: generate_device_id นับลำดับจาก MAX ในตาราง devices
                # ถ้าไม่ flush อุปกรณ์ประเภทเดียวกันในห้องเดียวกันจะได้ลำดับซ้ำ
                db.flush()
                device_ids[d["ref"]] = device.device_id

            # ลำดับมาจาก generate_ticket_id (นับแยกตามโรงเรียน/ปี) จึงไม่นับเองในสคริปต์
            for t in org_data["tickets"]:
                device_id = device_ids.get(t["device_ref"])
                if not device_id:
                    print(f"   ⚠ ข้าม ticket '{t['title']}': ไม่พบอุปกรณ์ ref={t['device_ref']}")
                    continue
                ticket = RepairTicket(
                    ticket_id=generate_ticket_id(db, org.id),
                    organization_id=org.id,
                    device_id=device_id,
                    title=t["title"],
                    description=t.get("description"),
                    priority=t["priority"],
                    status=t["status"],
                    reporter_name=t["reporter_name"],
                    created_at=datetime.now(timezone.utc),
                )
                db.add(ticket)
                db.flush()  # ให้ใบถัดไปเห็นลำดับนี้ใน repair_tickets ไม่งั้นได้เลขซ้ำทั้งก้อน

            created += 1
            print(f"✅ {org_data['code']} {org_data['name']} — {len(org_data['devices'])} อุปกรณ์, {len(org_data['tickets'])} tickets")
            for ref, did in device_ids.items():
                print(f"   {ref:<10} → {did}")

        db.commit()
        print(f"\nเสร็จ: เพิ่ม {created} องค์กรใหม่")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
