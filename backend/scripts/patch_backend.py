"""
patch_backend.py — Patch backend/main.py:
เพิ่ม /api/devices, /api/stats/devices, แก้ get_ticket, และเพิ่ม import selectinload
"""
import os

MAIN_PY = "C:/Users/nonam/smart-classroom-support/backend/app/main.py"

with open(MAIN_PY, "r", encoding="utf-8") as f:
    content = f.read()

changes = []

# 1. เพิ่ม selectinload ใน import
old_import = "from sqlalchemy.orm import Session"
new_import = "from sqlalchemy.orm import Session, selectinload"
if old_import in content and new_import not in content:
    content = content.replace(old_import, new_import)
    changes.append("เพิ่ม selectinload import")

# 2. เพิ่ม /api/devices endpoint ก่อนบรรทัด @app.get("/api/tickets"
marker = '@app.get("/api/tickets", response_model=list[TicketOut])'
if marker in content and '@app.get("/api/devices"' not in content:
    insert_pos = content.find(marker)
    new_endpoint = '''
@app.get("/api/devices", response_model=list[DeviceInfo])
def list_devices(
    status: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    organization_code: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Device, Room, Organization)
        .outerjoin(Room, Room.id == Device.room_id)
        .join(Organization, Organization.id == Device.organization_id)
        .order_by(Device.device_id)
    )
    if status:
        stmt = stmt.where(Device.status == status)
    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
    if organization_code:
        stmt = stmt.where(Organization.code == organization_code)
    stmt = stmt.offset(offset).limit(limit)

    rows = db.execute(stmt).all()
    result: list[DeviceInfo] = []
    for device, room, org in rows:
        result.append(DeviceInfo(
            device_id=device.device_id,
            device_type=device.device_type,
            brand=device.brand,
            model=device.model,
            serial_number=device.serial_number,
            firmware_version=device.firmware_version,
            status=device.status,
            room_code=room.code if room else None,
            room_name=room.name if room else None,
            building=room.building if room else None,
            floor=room.floor if room else None,
            organization_code=org.code,
            organization_name=org.name,
            warranty_until=device.warranty_until,
            notes=device.notes,
        ))
    return result

'''
    content = content[:insert_pos] + new_endpoint + content[insert_pos:]
    changes.append("เพิ่ม /api/devices endpoint")

# 3. เพิ่ม /api/stats/devices endpoint ก่อนบรรทัด @app.get("/api/tickets"
if '/api/stats/devices' not in content and marker in content:
    insert_pos = content.find(marker)
    new_stats = '''

@app.get("/api/stats/devices")
def get_device_stats(db: Session = Depends(get_db)):
    """Dashboard stats: นับ ticket ตามประเภทอุปกรณ์, สถานะ, ความเร่งด่วน"""
    by_type = db.execute(text("""
        SELECT d.device_type, COUNT(rt.id) as count
        FROM repair_tickets rt
        JOIN devices d ON rt.device_id = d.device_id
        GROUP BY d.device_type
        ORDER BY count DESC
    """)).fetchall()

    by_status = db.execute(text("""
        SELECT status, COUNT(*) as count
        FROM repair_tickets
        GROUP BY status
        ORDER BY count DESC
    """)).fetchall()

    by_priority = db.execute(text("""
        SELECT priority, COUNT(*) as count
        FROM repair_tickets
        GROUP BY priority
        ORDER BY count DESC
    """)).fetchall()

    devices_by_status = db.execute(text("""
        SELECT status, COUNT(*) as count
        FROM devices
        GROUP BY status
    """)).fetchall()

    return {
        "by_type": [{"device_type": r.device_type, "count": r.count} for r in by_type],
        "by_status": [{"status": r.status, "count": r.count} for r in by_status],
        "by_priority": [{"priority": r.priority, "count": r.count} for r in by_priority],
        "devices_by_status": [{"status": r.status, "count": r.count} for r in devices_by_status],
    }

'''
    content = content[:insert_pos] + new_stats + content[insert_pos:]
    changes.append("เพิ่ม /api/stats/devices endpoint")

# 4. แก้ get_ticket เพิ่ม device_info + history
old_get_ticket = '@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)\ndef get_ticket(ticket_id: str, db: Session = Depends(get_db)):\n    ticket = db.execute(\n        select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)\n    ).scalar_one_or_none()\n    if not ticket:\n        raise HTTPException(status_code=404, detail="Ticket not found")\n\n    return TicketOut('
if old_get_ticket in content:
    # หาตำแหน่งปิดท้าย function ด้วย "def list_tickets" หรือ "@app.patch"
    function_start = content.find(old_get_ticket)
    # หาจุดสิ้นสุดของ function (บรรทัดว่างๆ ก่อน function ถัดไป)
    rest = content[function_start:]
    # หาบรรทัด "def list_tickets" หรือ "@app.patch"
    end_marker = rest.find("\n\n@app.patch")
    if end_marker == -1:
        end_marker = rest.find("\n\ndef list_tickets")
    if end_marker == -1:
        end_marker = rest.find("\n@app.patch")
    
    if end_marker != -1:
        # แทนที่เฉพาะส่วนที่เป็น return + ปิดท้าย
        new_get_ticket = '''@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.execute(
        select(RepairTicket)
        .options(selectinload(RepairTicket.device), selectinload(RepairTicket.updates))
        .where(RepairTicket.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    out = TicketOut(
        id=ticket.id,
        ticket_id=ticket.ticket_id,
        device_id=ticket.device_id,
        title=ticket.title,
        description=ticket.description,
        reporter_name=ticket.reporter_name,
        reporter_email=ticket.reporter_email,
        reporter_phone=ticket.reporter_phone,
        reporter_type=ticket.reporter_type,
        priority=ticket.priority,
        status=ticket.status,
        assigned_to=ticket.assigned_to,
        scan_gps_lat=(float(ticket.scan_gps_lat) if ticket.scan_gps_lat else None),
        scan_gps_lng=(float(ticket.scan_gps_lng) if ticket.scan_gps_lng else None),
        scan_timestamp=ticket.scan_timestamp,
        resolution_notes=ticket.resolution_notes,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )
    out_dict = out.model_dump()
    out_dict["device_info"] = {
        "device_id": ticket.device.device_id if ticket.device else None,
        "device_type": ticket.device.device_type if ticket.device else None,
        "brand": ticket.device.brand if ticket.device else None,
        "model": ticket.device.model if ticket.device else None,
        "room_name": ticket.device.room.name if ticket.device and ticket.device.room else None,
        "organization_name": ticket.device.organization.name if ticket.device and ticket.device.organization else None,
    } if ticket.device else None
    out_dict["history"] = [
        {
            "id": u.id,
            "from_status": u.from_status,
            "to_status": u.to_status,
            "note": u.note,
            "author_name": u.author_name,
            "author_role": u.author_role,
            "created_at": u.created_at,
        }
        for u in ticket.updates
    ]
    return out_dict'''
        content = content[:function_start] + new_get_ticket + rest[end_marker:]
        changes.append("แก้ get_ticket เพิ่ม device_info + history")

print("เปลี่ยนแปลงที่ทำ:", changes)

with open(MAIN_PY, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\nOK: เขียนไฟล์ {MAIN_PY}")
print(f"เปลี่ยนแปลง: {len(changes)} รายการ")
for c in changes:
    print(f"  - {c}")
