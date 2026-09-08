# -*- coding: utf-8 -*-
"""Append PM + SLA check + QR endpoints to main.py and hook seed into lifespan"""
import io

p = r'C:\Users\nonam\smart-classroom-support\backend\app\main.py'
with io.open(p, 'r', encoding='utf-8') as f:
    s = f.read()

# hook seed_kb_articles into lifespan
old_lifespan = '''@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield'''

new_lifespan = '''@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Seed KB 30 หัวข้อ (ถ้าตารางว่าง) + สร้าง PM plans ตั้งต้น
    db = get_db().__next__()
    try:
        from app.models import KBArticle, PMPlan
        seeded = seed_kb_articles(db)
        pm_count = db.execute(select(func.count()).select_from(PMPlan)).scalar_one()
        if pm_count == 0:
            import json as _json
            db.add_all([
                PMPlan(name="บำรุงรักษาจอ Interactive รายไตรมาส", device_type="Interactive Display", interval_days=90,
                       checklist=_json.dumps([
                           {"order": 1, "item": "ทำความสะอาดหน้าจอและกรอบ", "type": "boolean"},
                           {"order": 2, "item": "ทดสอบระบบสัมผัสทุกมุมจอ", "type": "boolean"},
                           {"order": 3, "item": "ตรวจสอบสายสัญญาณและสายไฟ", "type": "boolean"},
                           {"order": 4, "item": "ทดสอบเสียงลำโพง", "type": "boolean"},
                           {"order": 5, "item": "อุณหภูมิเครื่อง (°C)", "type": "number"},
                       ], ensure_ascii=False), is_active=True),
                PMPlan(name="บำรุงรักษาคอมพิวเตอร์ราย 6 เดือน", device_type="Computer Desktop", interval_days=180,
                       checklist=_json.dumps([
                           {"order": 1, "item": "ทำความสะอาดพัดลมและช่องระบายอากาศ", "type": "boolean"},
                           {"order": 2, "item": "อัปเดตระบบปฏิบัติการ", "type": "boolean"},
                           {"order": 3, "item": "ตรวจสอบพื้นที่ว่างดิสก์", "type": "boolean"},
                           {"order": 4, "item": "ตรวจสอบแบตเตอรี่ CMOS", "type": "boolean"},
                       ], ensure_ascii=False), is_active=True),
                PMPlan(name="บำรุงรักษา Router/AP ราย 6 เดือน", device_type="Router", interval_days=180,
                       checklist=_json.dumps([
                           {"order": 1, "item": "ตรวจสัญญาณ Wi-Fi แต่ละจุด", "type": "boolean"},
                           {"order": 2, "item": "อัปเดต Firmware", "type": "boolean"},
                           {"order": 3, "item": "ทำความสะอาดฝุ่น", "type": "boolean"},
                           {"order": 4, "item": "ตรวจสอบสาย LAN และ PoE", "type": "boolean"},
                       ], ensure_ascii=False), is_active=True),
                PMPlan(name="บำรุงรักษาระบบเสียงรายไตรมาส", device_type="Speaker", interval_days=90,
                       checklist=_json.dumps([
                           {"order": 1, "item": "ทดสอบเสียงลำโพงทุกตัว", "type": "boolean"},
                           {"order": 2, "item": "ตรวจสายและขั้วต่อ", "type": "boolean"},
                           {"order": 3, "item": "ตรวจไมโครโฟนไร้สาย", "type": "boolean"},
                       ], ensure_ascii=False), is_active=True),
            ])
            db.commit()
    finally:
        db.close()
    yield'''

assert old_lifespan in s, "lifespan pattern not found"
s = s.replace(old_lifespan, new_lifespan)

block = '''

# ─── SLA Check + Escalation (TOR 4.5) — เรียกโดย n8n Cron ─────────────

@app.get("/api/internal/sla/check")
def sla_check(db: Session = Depends(get_db)):
    """ตรวจงานเกินกำหนด SLA → ยกระดับ L1/L2/L3 (เรียกทุก 15 นาทีโดย n8n)"""
    now = datetime.now(timezone.utc)
    overdue = db.execute(
        select(RepairTicket).where(
            RepairTicket.status.in_(["new", "assigned", "in_progress"]),
            RepairTicket.sla_due_at.is_not(None),
            RepairTicket.sla_due_at < now,
        )
    ).scalars().all()

    escalated = []
    for t in overdue:
        old_level = t.escalation_level
        if t.escalation_level == 0:
            t.escalation_level = 1
            note = "งานเกินกำหนด SLA — ระดับ 1 (เตือนช่างผู้รับผิดชอบ)"
        elif t.escalation_level == 1:
            t.escalation_level = 2
            note = "งานเกินกำหนด SLA เกิน 30 นาที — ระดับ 2 (แจ้งหัวหน้าฝ่าย IT)"
        else:
            note = "งานเกินกำหนด SLA นาน — ระดับ 3 (แจ้งผู้บริหาร)"
        if t.escalation_level != old_level:
            db.add(TicketUpdate(
                ticket=t,
                from_status=t.status,
                to_status=t.status,
                note=note,
                author_name="SLA System",
                author_role="system",
            ))
            escalated.append({
                "ticket_id": t.ticket_id,
                "priority": t.priority,
                "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
                "escalation_level": t.escalation_level,
                "note": note,
            })
    db.commit()
    return {"checked_at": now.isoformat(), "overdue_count": len(overdue), "escalated": escalated}


# ─── Preventive Maintenance (TOR 1.5.10 / 5.9) ───────────────────────

class PMPlanCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    device_type: Optional[str] = None
    interval_days: int = Field(90, ge=1, le=3650)
    checklist: Optional[list] = None
    is_active: bool = True


@app.get("/api/pm/plans")
def list_pm_plans(db: Session = Depends(get_db)):
    rows = db.execute(select(PMPlan).order_by(PMPlan.name)).scalars().all()
    return [
        {
            "id": p.id, "name": p.name, "device_type": p.device_type,
            "interval_days": p.interval_days,
            "checklist": json.loads(p.checklist) if p.checklist else [],
            "is_active": p.is_active,
        }
        for p in rows
    ]


@app.post("/api/pm/plans", status_code=201)
def create_pm_plan(payload: PMPlanCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin"))):
    plan = PMPlan(
        name=payload.name,
        device_type=payload.device_type,
        interval_days=payload.interval_days,
        checklist=json.dumps(payload.checklist or [], ensure_ascii=False),
        is_active=payload.is_active,
    )
    db.add(plan); db.commit(); db.refresh(plan)
    return {"id": plan.id, "name": plan.name, "device_type": plan.device_type,
            "interval_days": plan.interval_days,
            "checklist": json.loads(plan.checklist) if plan.checklist else [],
            "is_active": plan.is_active}


def _gen_pm_task_no(db: Session) -> str:
    now = datetime.now(timezone.utc)
    prefix = f"PM-{now.year}{now.month:02d}-"
    row = db.execute(
        text("SELECT COUNT(*) + 1 FROM pm_tasks WHERE task_no LIKE :p"),
        {"p": f"{prefix}%"},
    ).scalar_one()
    return f"{prefix}{row:04d}"


@app.post("/api/pm/generate")
def pm_generate(db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin", "it_support"))):
    """สร้างงาน PM ล่วงหน้า — อุปกรณ์ที่ถึงรอบ due (เรียกเองหรือ n8n Cron)"""
    now = datetime.now(timezone.utc)
    plans = db.execute(select(PMPlan).where(PMPlan.is_active == True)).scalars().all()
    generated = 0
    skipped = 0
    tasks = []
    for plan in plans:
        devices = db.execute(
            select(Device).where(
                (Device.device_type == plan.device_type) if plan.device_type else (Device.device_type.is_not(None))
            )
        ).scalars().all()
        for d in devices:
            # ข้ามถ้ามีงาน pending/overdue ค้างอยู่แล้ว
            existing = db.execute(
                select(PMTask).where(
                    PMTask.plan_id == plan.id,
                    PMTask.device_id == d.device_id,
                    PMTask.status.in_(["pending", "overdue"]),
                )
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            task = PMTask(
                task_no=_gen_pm_task_no(db),
                plan_id=plan.id,
                device_id=d.device_id,
                organization_id=d.organization_id,
                due_date=now + timedelta(days=7),
                status="pending",
            )
            db.add(task)
            tasks.append({"task_no": task.task_no, "device_id": d.device_id,
                          "due_date": task.due_date.isoformat()})
            generated += 1
    db.commit()
    return {"generated": generated, "skipped_duplicate": skipped, "tasks": tasks}


@app.get("/api/pm/tasks")
def list_pm_tasks(
    status: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(PMTask).order_by(PMTask.due_date)
    if status:
        stmt = stmt.where(PMTask.status == status)
    if device_id:
        stmt = stmt.where(PMTask.device_id == device_id)
    if organization_id:
        stmt = stmt.where(PMTask.organization_id == organization_id)
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    result = []
    for t in rows:
        plan = db.get(PMPlan, t.plan_id) if t.plan_id else None
        dev = db.execute(select(Device).where(Device.device_id == t.device_id)).scalar_one_or_none() if t.device_id else None
        result.append({
            "id": t.id, "task_no": t.task_no, "plan_id": t.plan_id,
            "plan_name": plan.name if plan else None,
            "device_id": t.device_id,
            "device_type": dev.device_type if dev else None,
            "organization_id": t.organization_id,
            "due_date": t.due_date,
            "status": t.status,
            "result": json.loads(t.result) if t.result else [],
            "photos": json.loads(t.photos) if t.photos else [],
            "done_at": t.done_at,
            "next_due": t.next_due,
            "ticket_id": t.ticket_id,
            "skip_reason": t.skip_reason,
            "checklist": json.loads(plan.checklist) if plan and plan.checklist else [],
        })
    return result


class PMSubmitRequest(BaseModel):
    result: Optional[list] = None
    photos: Optional[list[str]] = None


@app.post("/api/pm/tasks/{task_id}/submit")
def pm_submit(task_id: int, payload: PMSubmitRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin", "it_support"))):
    task = db.get(PMTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="PM task not found")
    now = datetime.now(timezone.utc)
    task.status = "done"
    task.result = json.dumps(payload.result or [], ensure_ascii=False)
    task.photos = json.dumps(payload.photos or [], ensure_ascii=False)
    task.done_at = now
    plan = db.get(PMPlan, task.plan_id) if task.plan_id else None
    task.next_due = now + timedelta(days=(plan.interval_days if plan else 90))

    # รายการ "ไม่ผ่าน" → สร้าง Ticket อัตโนมัติ (TOR 5.9)
    failed = [r for r in (payload.result or []) if r.get("value") is False or r.get("value") == "false"]
    auto_ticket = None
    if failed and task.device_id:
        dev = db.execute(select(Device).where(Device.device_id == task.device_id)).scalar_one_or_none()
        if dev:
            notes = " | ".join(str(r.get("note", "")) for r in failed if r.get("note"))
            ticket = RepairTicket(
                ticket_id=generate_ticket_id(db, dev.organization_id),
                organization_id=dev.organization_id,
                device_id=dev.device_id,
                title=f"PM พบปัญหา: {notes or task.task_no}",
                description=f"งาน PM {task.task_no} ตรวจพบรายการไม่ผ่าน: {notes}",
                priority="normal",
                status=TicketStatus.NEW,
                channel="pm",
                attachments=None,
            )
            db.add(ticket)
            db.flush()
            db.add(TicketUpdate(
                ticket=ticket,
                from_status=None,
                to_status=TicketStatus.NEW,
                note=f"สร้างอัตโนมัติจาก PM {task.task_no} — รายการไม่ผ่าน",
                author_name="PM System",
                author_role="system",
            ))
            task.ticket_id = ticket.ticket_id
            auto_ticket = {"ticket_no": ticket.ticket_id,
                           "symptom_text": ticket.title,
                           "priority": "normal"}
    db.commit()
    return {"status": task.status, "done_at": task.done_at, "next_due": task.next_due,
            "failed_items": len(failed), "auto_ticket": auto_ticket}


class PMSkipRequest(BaseModel):
    reason: str = Field(..., min_length=3)


@app.post("/api/pm/tasks/{task_id}/skip")
def pm_skip(task_id: int, payload: PMSkipRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin", "it_support"))):
    task = db.get(PMTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="PM task not found")
    task.status = "skipped"
    task.skip_reason = payload.reason
    db.commit()
    return {"message": "PM task skipped", "task_no": task.task_no, "reason": payload.reason}


# ─── QR Service (TOR 1.5.4 / 5.3) ─────────────────────────────────────

@app.get("/api/qr/resolve/{token}")
def qr_resolve(token: str, db: Session = Depends(get_db)):
    """แปลง QR token → ข้อมูลอุปกรณ์ (ไม่ต้อง login, มี rate limit ตาม spec)"""
    device = db.execute(select(Device).where(Device.qr_token == token)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="ไม่พบอุปกรณ์ที่ตรงกับ QR Code นี้")
    room = db.get(Room, device.room_id) if device.room_id else None
    org = db.get(Organization, device.organization_id)
    return {
        "type": "device",
        "device": {
            "device_id": device.device_id,
            "device_type": device.device_type,
            "brand": device.brand,
            "model": device.model,
            "serial_number": device.serial_number,
            "status": device.status,
            "warranty_until": device.warranty_until,
        },
        "room": {"name": room.name if room else None, "code": room.code if room else None,
                 "building": room.building if room else None},
        "organization": {"code": org.code if org else None, "name": org.name if org else None},
        "qr_url": f"/scan?t={token}",
    }


@app.post("/api/qr/rotate/{device_id}")
def qr_rotate(device_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin", "it_support"))):
    """ออก QR token ใหม่ (สติกเกอร์หาย/ถูกนำไปใช้ผิด) — device_id เดิม ไม่ต้องพิมพ์ใหม่ทั้งเครื่อง"""
    import secrets
    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.qr_token = secrets.token_urlsafe(24)
    db.commit()
    return {"device_id": device.device_id, "qr_token": device.qr_token,
            "qr_url": f"/scan?t={device.qr_token}"}


@app.get("/api/qr/lookup")
def qr_lookup(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """ช่องทางสำรอง QR ชำรุด — ค้นหาด้วยรหัสอุปกรณ์ (รองรับบางส่วน)"""
    rows = db.execute(
        select(Device)
        .where(Device.device_id.ilike(f"%{q}%"))
        .order_by(Device.device_id)
        .limit(limit)
    ).scalars().all()
    return [
        {
            "device_id": d.device_id,
            "device_type": d.device_type,
            "brand": d.brand,
            "model": d.model,
            "organization_id": d.organization_id,
            "qr_url": f"/scan?t={d.qr_token}" if d.qr_token else f"/scan?device={d.device_id}",
        }
        for d in rows
    ]


@app.get("/api/rooms/{room_id}/devices")
def room_devices(room_id: int, db: Session = Depends(get_db)):
    """รายการอุปกรณ์ในห้อง (Room QR — TOR 1.5.4)"""
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    devices = db.execute(
        select(Device).where(Device.room_id == room_id).order_by(Device.device_id)
    ).scalars().all()
    return {
        "room": {"id": room.id, "code": room.code, "name": room.name,
                 "building": room.building, "floor": room.floor},
        "devices": [
            {
                "device_id": d.device_id,
                "device_type": d.device_type,
                "brand": d.brand,
                "model": d.model,
                "status": d.status,
                "qr_url": f"/scan?t={d.qr_token}" if d.qr_token else f"/scan?device={d.device_id}",
            }
            for d in devices
        ],
    }


@app.get("/api/qr/batch")
def qr_batch(organization_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """รายการ QR ทั้งหมด (สำหรับหน้าพิมพ์ batch — TOR 1.5.4)"""
    stmt = select(Device).order_by(Device.device_id)
    if organization_id:
        stmt = stmt.where(Device.organization_id == organization_id)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "device_id": d.device_id,
            "device_type": d.device_type,
            "brand": d.brand,
            "model": d.model,
            "qr_url": f"/scan?t={d.qr_token}" if d.qr_token else f"/scan?device={d.device_id}",
        }
        for d in rows
    ]
'''

with io.open(p, 'a', encoding='utf-8') as f:
    f.write(block)
print("APPENDED PM/SLA/QR OK,", len(block), "chars")
