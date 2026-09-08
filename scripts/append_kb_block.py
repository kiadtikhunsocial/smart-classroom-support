# -*- coding: utf-8 -*-
"""Append new endpoint blocks (KB/upload/diagnose/self-service) to main.py"""
import io

p = r'C:\Users\nonam\smart-classroom-support\backend\app\main.py'
with io.open(p, 'r', encoding='utf-8') as f:
    s = f.read()

block = '''

# ─── Uploads (รูปภาพแนบ — TOR 1.5.2) ─────────────────────────────────
from fastapi import File, UploadFile
from fastapi.staticfiles import StaticFiles

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.post("/api/uploads", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """อัปโหลดรูปภาพ (สูงสุด 10MB) — ใช้กับฟอร์มแจ้งซ่อม + PM"""
    import uuid as _uuid
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ไฟล์เกิน 10 MB")
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"):
        raise HTTPException(status_code=415, detail="ชนิดไฟล์ไม่รองรับ (ใช้ jpg/png/webp)")
    fname = f"{_uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, fname)
    with open(path, "wb") as f:
        f.write(content)
    return {"url": f"/uploads/{fname}", "filename": file.filename, "size": len(content)}


# ─── Knowledge Base (KB — TOR 1.5.5 / 5.6) ────────────────────────────

class KBArticleCreate(BaseModel):
    device_type: Optional[str] = None
    title: str = Field(..., min_length=3, max_length=255)
    symptom_tags: Optional[list[str]] = None
    steps: Optional[list] = None
    is_published: bool = True

class KBArticleUpdate(BaseModel):
    device_type: Optional[str] = None
    title: Optional[str] = None
    symptom_tags: Optional[list[str]] = None
    steps: Optional[list] = None
    is_published: Optional[bool] = None

class KBArticleOut(BaseModel):
    id: int
    kb_id: str
    device_type: Optional[str] = None
    title: str
    symptom_tags: Optional[list] = None
    steps: Optional[list] = None
    is_published: bool
    view_count: int = 0
    success_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


def _kb_to_out(a: KBArticle) -> KBArticleOut:
    return KBArticleOut(
        id=a.id, kb_id=a.kb_id, device_type=a.device_type, title=a.title,
        symptom_tags=json.loads(a.symptom_tags) if a.symptom_tags else [],
        steps=json.loads(a.steps) if a.steps else [],
        is_published=a.is_published, view_count=a.view_count, success_count=a.success_count,
        created_at=a.created_at, updated_at=a.updated_at,
    )


@app.get("/api/kb/articles", response_model=list[KBArticleOut])
def list_kb_articles(
    q: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    is_published: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(KBArticle).order_by(KBArticle.title)
    if device_type:
        stmt = stmt.where(KBArticle.device_type == device_type)
    if is_published is not None:
        stmt = stmt.where(KBArticle.is_published == is_published)
    if q:
        stmt = stmt.where(KBArticle.title.ilike(f"%{q}%"))
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [_kb_to_out(a) for a in rows]


@app.get("/api/kb/articles/{kb_id}", response_model=KBArticleOut)
def get_kb_article(kb_id: str, db: Session = Depends(get_db)):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="KB article not found")
    return _kb_to_out(a)


@app.post("/api/kb/articles", response_model=KBArticleOut, status_code=201)
def create_kb_article(payload: KBArticleCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin"))):
    count = db.execute(select(func.count()).select_from(KBArticle)).scalar_one() + 1
    a = KBArticle(
        kb_id=f"kb-{count:04d}",
        device_type=payload.device_type,
        title=payload.title,
        symptom_tags=json.dumps(payload.symptom_tags or [], ensure_ascii=False),
        steps=json.dumps(payload.steps or [], ensure_ascii=False),
        is_published=payload.is_published,
    )
    db.add(a); db.commit(); db.refresh(a)
    return _kb_to_out(a)


@app.patch("/api/kb/articles/{kb_id}", response_model=KBArticleOut)
def update_kb_article(kb_id: str, payload: KBArticleUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin"))):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="KB article not found")
    data = payload.model_dump(exclude_unset=True)
    if "symptom_tags" in data and data["symptom_tags"] is not None:
        data["symptom_tags"] = json.dumps(data["symptom_tags"], ensure_ascii=False)
    if "steps" in data and data["steps"] is not None:
        data["steps"] = json.dumps(data["steps"], ensure_ascii=False)
    for k, v in data.items():
        setattr(a, k, v)
    db.commit(); db.refresh(a)
    return _kb_to_out(a)


@app.delete("/api/kb/articles/{kb_id}")
def delete_kb_article(kb_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("super_admin", "admin"))):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="KB article not found")
    db.delete(a); db.commit()
    return {"message": "KB article deleted", "kb_id": kb_id}


# ─── Seed KB 30 หัวข้อ (TOR ภาคผนวก ง) ────────────────────────────────

def seed_kb_articles(db: Session):
    """ใส่บทความ KB ตั้งต้น 30 หัวข้อ — รันเมื่อตารางว่าง"""
    count = db.execute(select(func.count()).select_from(KBArticle)).scalar_one()
    if count > 0:
        return 0
    articles = [
        ("Interactive Display", "จอ Interactive ไม่มีภาพ (ไฟเปิดติด)", ["จอไม่ติด", "ไม่มีภาพ", "no signal", "จอดำ", "ไฟติด"], [
            "ตรวจสอบสาย HDMI ให้เสียบแน่นทั้งสองด้าน",
            "กดปุ่ม Source/Input ที่รีโมท เลือกช่องสัญญาณให้ตรงกับพอร์ต",
            "ปิดจอค้างไว้ 10 วินาที แล้วเปิดใหม่",
            "ตรวจสอบว่าคอมพิวเตอร์เปิดอยู่และไม่ได้อยู่ในโหมด Sleep",
            "หากมีสาย HDMI สำรอง ให้ลองสลับสาย",
        ]),
        ("Interactive Display", "จอ Interactive ระบบสัมผัสไม่ทำงาน", ["สัมผัส", "touch", "touchscreen", "กดไม่ได้", "เขียนไม่ได้"], [
            "เช็ดหน้าจอให้สะอาดด้วยผ้าแห้ง (ไม่ใช้แอลกอฮอล์)",
            "ตรวจสอบว่าโหมดสัมผัสเปิดอยู่ (Settings → Touch)",
            "ถอดปลั๊กจอ 30 วินาที แล้วเสียบกลับ",
            "ลองแตะที่มุมจอทั้ง 4 ด้านเพื่อ calibrate",
            "ถ้ายังไม่หาย ต้องส่งช่างตรวจแผงสัมผัส",
        ]),
        ("Interactive Display", "จอ Interactive ไม่มีเสียง", ["ไม่มีเสียง", "no sound", "เงียบ", "ลำโพงไม่ดัง"], [
            "กดปุ่มเพิ่มเสียงที่รีโมท/ตัวเครื่อง",
            "ตรวจสอบว่าไม่ได้ Mute (ปุ่มรูปกากบาทเสียง)",
            "ตรวจสอบการตั้งค่าเสียงในระบบปฏิบัติการ",
            "ลองเสียบหูฟังเพื่อตรวจว่าลำโพงในตัวเสียหรือไม่",
            "ถ้าหูฟังดังแต่ลำโพงไม่ดัง ให้แจ้งช่างเปลี่ยนลำโพง",
        ]),
        ("Computer Desktop", "คอมพิวเตอร์เปิดไม่ติด", ["เปิดไม่ติด", "boot ไม่ขึ้น", "ไฟไม่เข้า", "จอดำ", "คอมไม่ทำงาน"], [
            "ตรวจสอบปลั๊กไฟและสายไฟให้เสียบแน่น",
            "กดปุ่ม Power ค้าง 10 วินาที แล้วกดใหม่",
            "ตรวจสอบว่าเต้ารับมีไฟ (ลองเสียบอุปกรณ์อื่น)",
            "ฟังเสียงพัดลม — ถ้าเงียบสนิทอาจ PSU เสีย",
            "ถ้ายังไม่ติด ให้แจ้งช่าง (ห้ามแกะเครื่องเอง)",
        ]),
        ("Computer Desktop", "คอมพิวเตอร์ช้า ค้างบ่อย", ["ช้า", "ค้าง", "แฮงก์", "หน่วง", "ช้าลง"], [
            "รีสตาร์ทเครื่องก่อน (Restart ไม่ใช่ Shutdown)",
            "ปิดโปรแกรมที่ไม่ใช้ (Ctrl+Shift+Esc → Task Manager)",
            "ตรวจสอบพื้นที่ว่างดิสก์ (ต้องเหลืออย่างน้อย 10%)",
            "ตรวจสอบอุณหภูมิ CPU — ถ้าร้อนจัดพัดลมอาจตัน",
            "ถ้ายังช้า ให้แจ้งช่างตรวจพัดลม/เปลี่ยน SSD",
        ]),
        ("Computer Desktop", "คอมพิวเตอร์ต่ออินเทอร์เน็ตไม่ได้", ["เน็ตไม่เข้า", "อินเทอร์เน็ต", "wifi ไม่", "lan ไม่", "ออฟไลน์"], [
            "ตรวจสอบว่าสาย LAN เสียบแน่น หรือ Wi-Fi เปิดอยู่",
            "ลองคลิกไอคอนเน็ต → แก้ไขปัญหา (Troubleshoot)",
            "ตรวจสอบว่าเครื่องอื่นในห้องใช้เน็ตได้หรือไม่",
            "ลอง restart เราเตอร์/AP ในห้อง",
            "ถ้าเครื่องอื่นก็ใช้ไม่ได้ ให้แจ้งช่างตรวจเครือข่าย",
        ]),
        ("Computer Notebook", "โน้ตบุ๊กชาร์จไม่เข้า", ["ชาร์จไม่เข้า", "แบตไม่ชาร์จ", "adapter", "สายชาร์จ"], [
            "ตรวจสอบปลั๊กและหัวชาร์จให้เสียบแน่น",
            "ลองเปลี่ยนเต้ารับอื่น",
            "ตรวจสอบไฟที่ adapter (ถ้าไม่มีไฟ แสดงว่า adapter เสีย)",
            "ถอดแบต (ถ้าถอดได้) แล้วใส่ใหม่",
            "ถ้ายังไม่ชาร์จ ให้แจ้งช่างเปลี่ยน adapter/หัวชาร์จ",
        ]),
        ("Projector", "โปรเจกเตอร์ไม่ขึ้นภาพ", ["โปรเจกเตอร์", "projector", "ไม่ขึ้นภาพ", "จอไม่แสดง"], [
            "ตรวจสอบไฟที่ตัวเครื่อง — ถ้าติดแต่ไม่มีภาพ อาจโคมไฟ (lamp) เสื่อม",
            "ตรวจสอบสาย VGA/HDMI ให้เสียบแน่นทั้งสองด้าน",
            "กดปุ่ม Source เลือกช่องสัญญาณที่ถูกต้อง",
            "รอเครื่องอุ่นเครื่อง 2-3 นาที (โคมไฟต้องอุ่นก่อน)",
            "ถ้าไฟกระพริบสีแดง ให้แจ้งช่างเปลี่ยนโคมไฟ",
        ]),
        ("Router", "Wi-Fi ช้า หลุดบ่อย", ["wifi ช้า", "เน็ตช้า", "หลุด", "สัญญาณอ่อน", "wi-fi"], [
            "รีสตาร์ทเราเตอร์ (ถอดปลั๊ก 30 วินาที แล้วเสียบใหม่)",
            "ตรวจสอบตำแหน่งเราเตอร์ — ควรอยู่สูงและกลางห้อง",
            "จำกัดจำนวนเครื่องที่เชื่อมต่อพร้อมกัน",
            "ตรวจสอบว่าสายจาก ONT/โมเด็มเสียบแน่น",
            "ถ้ายังช้า ให้แจ้งช่างตรวจสัญญาณ/อัปเดต firmware",
        ]),
        ("Access Point", "Access Point ไม่มีสัญญาณ", ["ap ไม่", "access point", "สัญญาณหาย", "wifi หาย"], [
            "ตรวจสอบไฟที่ AP — ถ้าดับแสดงว่าไฟไม่เข้า",
            "รีสตาร์ท AP โดยถอดปลั๊ก 30 วินาที",
            "ตรวจสอบสาย LAN ที่ต่อเข้ากับ AP",
            "ตรวจสอบว่า PoE Switch ที่จ่ายไฟทำงานอยู่",
            "ถ้ายังไม่มีสัญญาณ ให้แจ้งช่างตรวจ AP/Switch",
        ]),
        ("Speaker", "ลำโพงห้องเรียนไม่มีเสียง", ["ลำโพง", "ไม่มีเสียง", "เครื่องเสียง", "ไมค์ไม่ดัง"], [
            "ตรวจสอบปุ่ม Volume ที่เครื่องขยายเสียง (Amplifier)",
            "ตรวจสอบสายสัญญาณ (RCA/XLR) ให้เสียบแน่น",
            "ตรวจสอบว่าไม่ได้กด Mute",
            "ลองเปิดเพลงจากโทรศัพท์ผ่านสาย AUX เพื่อทดสอบลำโพง",
            "ถ้าลำโพงหลักไม่ดัง ให้แจ้งช่างตรวจแอมป์",
        ]),
        ("Microphone", "ไมโครโฟนไม่ดัง", ["ไมค์", "microphone", "ไมโครโฟน", "พูดไม่ได้ยิน"], [
            "ตรวจสอบสวิตช์เปิด/ปิดไมค์",
            "ตรวจสอบแบตเตอรี่ (ถ้าเป็นไร้สาย)",
            "ตรวจสอบความถี่ช่องสัญญาณให้ตรงกับเครื่องรับ",
            "ลองเสียบไมค์สายเข้ากับแอมป์โดยตรง",
            "ถ้ายังไม่ดัง ให้แจ้งช่างตรวจเครื่องรับสัญญาณ",
        ]),
        ("Camera", "กล้องวงจรปิดไม่มีภาพ", ["กล้อง", "cctv", "วงจรปิด", "ไม่มีภาพ", "มืด"], [
            "ตรวจสอบไฟที่กล้อง (IR LED ควรติดตอนกลางคืน)",
            "ตรวจสอบสาย LAN/สายไฟให้เสียบแน่น",
            "รีสตาร์ทเครื่องบันทึก (DVR/NVR)",
            "ตรวจสอบว่าจอ monitor เปิดอยู่และเลือกช่องถูกต้อง",
            "ถ้ายังไม่มีภาพ ให้แจ้งช่างตรวจกล้อง/เครื่องบันทึก",
        ]),
        ("Visualizer", "Visualizer ไม่แสดงภาพ", ["visualizer", "เครื่องฉายภาพ", "doc cam", "ไม่แสดงภาพ"], [
            "ตรวจสอบว่าเปิดไฟที่ตัวเครื่อง",
            "ตรวจสอบสาย VGA/HDMI ให้เสียบแน่น",
            "กดปุ่ม Source ที่จอ/โปรเจกเตอร์ เลือกช่องที่ถูกต้อง",
            "ลองกดปุ่ม Freeze/Standby ที่รีโมท",
            "ถ้ายังไม่แสดง ให้แจ้งช่างตรวจเซนเซอร์กล้อง",
        ]),
        ("UPS", "UPS เสียงเตือนดัง", ["ups", "สำรองไฟ", "เสียงเตือน", "beep"], [
            "เสียงเตือนต่อเนื่อง = ไฟบ้านดับ กำลังใช้แบตสำรอง — ประหยัดการใช้ไฟ",
            "เสียงเตือนสั้น ๆ เป็นระยะ = แบตเสื่อมหรือโหลดเกิน",
            "ตรวจสอบไฟที่ผนังว่ามีจริงหรือไม่",
            "กดปุ่ม Test เพื่อตรวจสภาพแบตเตอรี่",
            "ถ้าแบตเสื่อม (เตือนถี่ขึ้น) ให้แจ้งช่างเปลี่ยนแบต",
        ]),
        ("Printer", "ปริ้นเตอร์ไม่ทำงาน", ["ปริ้น", "printer", "พิมพ์ไม่ได้", "กระดาษติด"], [
            "ตรวจสอบกระดาษในถาดและแกะกระดาษติด (ถ้ามี)",
            "ตรวจสอบหมึก/โทนเนอร์ — ถ้าเหลือน้อยจะปริ้นไม่ออก",
            "ตรวจสอบว่าเครื่องปริ้นเปิดอยู่และเชื่อมต่อ (USB/Wi-Fi)",
            "ลองยกเลิกงานค้างในคิวพิมพ์ (Printer queue)",
            "ถ้ายังไม่ทำงาน ให้แจ้งช่างตรวจหัวพิมพ์/เซนเซอร์",
        ]),
        ("Software (Picaro)", "โปรแกรม Picaro เปิดไม่ได้", ["picaro", "เปิดไม่ได้", "crash", "error"], [
            "ปิดโปรแกรมทั้งหมดแล้วเปิดใหม่",
            "รีสตาร์ทคอมพิวเตอร์ก่อนลองอีกครั้ง",
            "ตรวจสอบว่าโปรแกรมติดตั้งเวอร์ชันล่าสุด",
            "บันทึกข้อความ error แล้วส่งให้ช่างตรวจ",
            "ถ้ายังเปิดไม่ได้ ให้แจ้งช่างติดตั้งใหม่",
        ]),
        ("Software (Phonics Hero)", "โปรแกรม Phonics Hero เข้าไม่ได้", ["phonics", "login ไม่ได้", "เข้าไม่ได้", "password"], [
            "ตรวจสอบอินเทอร์เน็ตก่อน (โปรแกรมต้องออนไลน์)",
            "ลองรีเซ็ตรหัสผ่าน (ลืมรหัสผ่าน)",
            "ตรวจสอบว่าบัญชีนักเรียน/ครูยัง active",
            "ลองใช้เบราว์เซอร์อื่น/เคลียร์แคช",
            "ถ้ายังเข้าไม่ได้ ให้แจ้งผู้ดูแลบัญชี",
        ]),
        ("Other", "อุปกรณ์มีกลิ่นไหม้ / ควัน", ["กลิ่นไหม้", "ควัน", "ไฟช็อต", "อันตราย"], [
            "ปิดเครื่องทันทีและถอดปลั๊ก (สำคัญที่สุด)",
            "อย่าเปิดเครื่องอีกจนกว่าช่างจะตรวจ",
            "ตักเตือนนักเรียนไม่ให้เข้าใกล้",
            "แจ้งช่างทันที — ห้ามซ่อมเอง",
            "บันทึกตำแหน่งอุปกรณ์เพื่อให้ช่างหาเจอ",
        ]),
        ("Other", "ปลั๊ก/เต้ารับร้อนผิดปกติ", ["ปลั๊กร้อน", "เต้ารับ", "ช็อต", "ไฟดูด"], [
            "หยุดใช้อุปกรณ์ที่เสียบอยู่นั้นทันที",
            "ถอดปลั๊ก (ใช้ผ้าหนา/ถุงมือกันไฟ)",
            "ตรวจสอบว่ามีอุปกรณ์เกินกำลังหรือไม่",
            "แจ้งช่างตรวจสายไฟ/เบรกเกอร์",
            "ห้ามเสียบอุปกรณ์อื่นแทนจนกว่าจะตรวจเสร็จ",
        ]),
        ("Computer AIO", "จอ AIO ฟ้า (Blue Screen)", ["blue screen", "จอฟ้า", "bsod", "error จอ"], [
            "จดรหัส error ที่ขึ้นบนจอ",
            "รีสตาร์ทเครื่อง (กดปุ่มค้าง 10 วินาที)",
            "ถ้าเกิดซ้ำ ให้ลอง Safe Mode (กด F8/F4 ตอนบูต)",
            "ตรวจสอบพื้นที่ว่างดิสก์และอัปเดต Windows",
            "ถ้าเกิดบ่อย ให้แจ้งช่างตรวจ RAM/ฮาร์ดดิสก์",
        ]),
        ("Computer AIO", "คอมพิวเตอร์บูตช้า", ["บูตช้า", "startup ช้า", "windows ช้า"], [
            "ปิดโปรแกรม auto-start ที่ไม่จำเป็น (Task Manager → Startup)",
            "ตรวจสอบพื้นที่ว่างดิสก์",
            "ถอดอุปกรณ์ USB ที่ไม่จำเป็นออก",
            "สแกนไวรัส/โปรแกรมไม่พึงประสงค์",
            "ถ้ายังช้า ให้แจ้งช่างตรวจ/เปลี่ยน SSD",
        ]),
        ("Computer Tablet", "แท็บเล็ตค้าง/รีสตาร์ทเอง", ["แท็บเล็ต", "tablet", "ค้าง", "รีสตาร์ทเอง", "ปิดเอง"], [
            "กดปุ่ม Power ค้าง 10 วินาที เพื่อบังคับรีสตาร์ท",
            "ตรวจสอบแบตเตอรี่ (ชาร์จให้เกิน 30%)",
            "อัปเดตระบบปฏิบัติการให้เป็นเวอร์ชันล่าสุด",
            "ล้างแคชแอปที่ใช้งานบ่อย",
            "ถ้ายังรีสตาร์ทเอง ให้แจ้งช่างตรวจแบต/เมนบอร์ด",
        ]),
        ("Computer Tablet", "แท็บเล็ตชาร์จไม่เข้า", ["แท็บเล็ตชาร์จ", "ชาร์จไม่เข้า", "หัวชาร์จ"], [
            "ตรวจสอบสายและหัวชาร์จให้เสียบแน่น",
            "ลองเปลี่ยนสาย/หัวชาร์จตัวอื่น",
            "ตรวจสอบพอร์ตชาร์จว่ามีฝุ่นหรือไม่ (เป่าลมเบา ๆ)",
            "ลองชาร์จข้ามคืน (แบตอาจหมดสนิท)",
            "ถ้ายังไม่ชาร์จ ให้แจ้งช่างเปลี่ยนพอร์ต/แบต",
        ]),
        ("Interactive Display", "จอ Interactive ภาพเพี้ยน/มีเส้น", ["ภาพเพี้ยน", "เส้น", "จอแตก", "จุดด่าง"], [
            "ถ่ายรูปอาการเพื่อส่งช่าง (สำคัญ)",
            "ลองเปลี่ยนสาย HDMI",
            "ตรวจสอบว่าจอมีรอยแตก/รอยกระแทกหรือไม่",
            "รีสตาร์ทจอและแหล่งสัญญาณ",
            "ถ้าเป็นรอยแตกที่แผง ต้องแจ้งช่างเปลี่ยนจอ",
        ]),
        ("Interactive Display", "จอ Interactive ร้อนจัด/พัดลมดัง", ["ร้อน", "พัดลมดัง", "เสียงดัง", "จอร้อน"], [
            "ตรวจสอบช่องระบายอากาศว่ามีฝุ่นอุดตันหรือไม่",
            "ตรวจสอบตำแหน่งติดตั้ง — ควรมีที่ว่างรอบเครื่อง",
            "ปิดจอพัก 10 นาที ให้เย็นลง",
            "ถ้าพัดลมดังผิดปกติต่อเนื่อง ให้แจ้งช่าง",
            "ห้ามฉีดน้ำหรือของเหลวใส่เครื่อง",
        ]),
        ("Router", "Router ไฟกระพริบไม่หยุด", ["router ไฟ", "ไฟกระพริบ", "internet ไฟแดง"], [
            "ไฟ Power กระพริบ = ตัวเครื่องมีปัญหา → รีสตาร์ท",
            "ไฟ Internet/WAN สีแดง = สัญญาณจากโมเด็มขาด",
            "รีสตาร์ททั้งโมเด็มและเราเตอร์",
            "ตรวจสอบสายจากโมเด็มเข้า WAN ให้เสียบแน่น",
            "ถ้ายังแดง ให้แจ้งช่างตรวจกับผู้ให้บริการเน็ต",
        ]),
        ("Camera", "กล้องภาพเบลอ/ไม่ชัด", ["กล้องเบลอ", "ภาพไม่ชัด", "โฟกัส"], [
            "เช็ดเลนส์กล้องด้วยผ้าแห้งนุ่ม",
            "ตรวจสอบฟิล์มกันรอยที่เลนส์ (ถ้ามี) ลอกออก",
            "ปรับโฟกัสด้วยมือ (ถ้าเป็นกล้องปรับได้)",
            "ตรวจสอบความละเอียดการบันทึก (Resolution)",
            "ถ้ายังเบลอ ให้แจ้งช่างตรวจเลนส์/เซนเซอร์",
        ]),
        ("Speaker", "เครื่องขยายเสียงฮัม/มีเสียงรบกวน", ["เสียงฮัม", "hum", "เสียงรบกวน", "แอมป์"], [
            "ลดเกน (Gain) ของไมค์ลง",
            "ตรวจสอบสายสัญญาณว่าขาด/ชำรุดหรือไม่",
            "ย้ายสายสัญญาณให้ห่างจากสายไฟ",
            "ตรวจสอบการต่อ Ground (สายดิน)",
            "ถ้ายังฮัม ให้แจ้งช่างตรวจแอมป์",
        ]),
        ("UPS", "อุปกรณ์ต่อ UPS ดับทั้งที่ไฟเข้า", ["ups ดับ", "ไฟดับ", "เครื่องดับ"], [
            "ตรวจสอบว่า UPS เปิดสวิตช์อยู่",
            "ตรวจสอบว่าโหลดไม่เกินกำลัง (อย่าเสียบหลายเครื่อง)",
            "กดปุ่ม Test — ถ้าแบตหมดจะเตือน",
            "ตรวจสอบว่าปลั๊กผนังมีไฟจริง",
            "ถ้า UPS เก่าเกิน 3 ปี ให้แจ้งช่างเปลี่ยนแบต",
        ]),
        ("Other", "สอบถามเรื่องการใช้อุปกรณ์", ["วิธีใช้", "ใช้งานยังไง", "สอบถาม", "how to"], [
            "ระบุอุปกรณ์และรหัสห้องให้ชัดเจน",
            "แจ้งอาการ/สิ่งที่ต้องการทำ",
            "ช่างจะแนะนำหรือนัดสาธิตการใช้งาน",
            "ถ้าเป็นซอฟต์แวร์ ให้ระบุเวอร์ชัน",
            "กรณีเร่งด่วนระหว่างสอน ให้โทรหา IT โดยตรง",
        ]),
    ]
    for i, (dtype, title, tags, steps) in enumerate(articles, start=1):
        db.add(KBArticle(
            kb_id=f"kb-{i:04d}",
            device_type=dtype,
            title=title,
            symptom_tags=json.dumps(tags, ensure_ascii=False),
            steps=json.dumps([{"order": j + 1, "text": t} for j, t in enumerate(steps)], ensure_ascii=False),
            is_published=True,
        ))
    db.commit()
    return len(articles)


# ─── AI Diagnose (TOR 5.5) — ค้น KB ด้วยคำสำคัญ, score < 0.3 → ส่งต่อช่าง ──

class DiagnoseRequest(BaseModel):
    device_id: Optional[str] = None
    device_type: Optional[str] = None
    symptom_text: str = Field(..., min_length=2, max_length=500)

class DiagnoseResult(BaseModel):
    session_id: str
    found: bool
    confidence: Optional[float] = None
    category: Optional[str] = None
    kb_article_id: Optional[str] = None
    title: Optional[str] = None
    steps: list = []
    message: str = ""
    next_actions: list = []
    fallback_mode: bool = False


@app.post("/api/ai/diagnose", response_model=DiagnoseResult)
def ai_diagnose(payload: DiagnoseRequest, db: Session = Depends(get_db)):
    """วิเคราะห์อาการ → ค้น KB (ไม่ใช้ LLM ให้ AI เดา — ตอบจาก KB เท่านั้นตาม TOR)"""
    import uuid as _uuid
    import re
    session_id = f"ai-{_uuid.uuid4().hex[:12]}"
    articles = db.execute(
        select(KBArticle).where(KBArticle.is_published == True)
    ).scalars().all()

    tokens = [t.lower() for t in re.split(r"[\\s,，。.!?/\\\\/]+", payload.symptom_text) if len(t.strip()) >= 2]
    if not tokens:
        tokens = [payload.symptom_text.lower()]

    best = None
    best_score = 0.0
    for a in articles:
        tags = json.loads(a.symptom_tags) if a.symptom_tags else []
        corpus = " ".join(t.lower() for t in tags) + " " + a.title.lower()
        score = sum(1 for t in tokens if t in corpus) / max(len(tokens), 1)
        if payload.device_type and a.device_type == payload.device_type:
            score += 0.15
        if score > best_score:
            best_score = score
            best = a

    if best and best_score >= 0.3:
        best.view_count = (best.view_count or 0) + 1
        db.commit()
        steps = [s["text"] for s in (json.loads(best.steps) if best.steps else [])]
        return DiagnoseResult(
            session_id=session_id,
            found=True,
            confidence=round(best_score, 2),
            category=best.device_type,
            kb_article_id=best.kb_id,
            title=best.title,
            steps=steps,
            message="พบวิธีแก้ไขเบื้องต้นจากฐานความรู้ ลองทำตามขั้นตอนด้านล่างก่อนนะคะ",
            next_actions=[
                {"type": "resolved", "label": "แก้ไขได้แล้ว ✅"},
                {"type": "create_ticket", "label": "ยังไม่หาย → แจ้งเจ้าหน้าที่"},
            ],
        )

    return DiagnoseResult(
        session_id=session_id,
        found=False,
        confidence=round(best_score, 2),
        category=None,
        message="ระบบไม่พบวิธีแก้ไขเบื้องต้นสำหรับอาการนี้ ขออนุญาตส่งต่อให้เจ้าหน้าที่ดำเนินการครับ",
        next_actions=[{"type": "create_ticket", "label": "แจ้งเจ้าหน้าที่"}],
    )


# ─── Self-Service Case (TOR 5.8) ──────────────────────────────────────

class SelfServiceCreate(BaseModel):
    device_id: Optional[str] = None
    symptom: Optional[str] = None
    kb_article_id: Optional[int] = None
    ai_session_id: Optional[str] = None
    helpful_step: Optional[int] = None
    time_saved_minutes: Optional[int] = None


@app.post("/api/self-service", status_code=201)
def create_self_service(payload: SelfServiceCreate, db: Session = Depends(get_db)):
    """บันทึกกรณีผู้ใช้แก้ไขได้เองจากคำแนะนำ Chatbot/KB"""
    if payload.kb_article_id:
        kb = db.get(KBArticle, payload.kb_article_id)
        if kb:
            kb.success_count = (kb.success_count or 0) + 1
    case = SelfServiceCase(
        device_id=payload.device_id,
        symptom=payload.symptom,
        kb_article_id=payload.kb_article_id,
        ai_session_id=payload.ai_session_id,
        helpful_step=payload.helpful_step,
        time_saved_minutes=payload.time_saved_minutes,
        resolved=True,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return {"id": case.id, "message": "บันทึกเรียบร้อย ขอบคุณครับ"}


@app.get("/api/self-service")
def list_self_service(
    device_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("super_admin", "admin")),
):
    stmt = select(SelfServiceCase).order_by(SelfServiceCase.created_at.desc())
    if device_id:
        stmt = stmt.where(SelfServiceCase.device_id == device_id)
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [
        {
            "id": c.id,
            "device_id": c.device_id,
            "symptom": c.symptom,
            "kb_article_id": c.kb_article_id,
            "ai_session_id": c.ai_session_id,
            "helpful_step": c.helpful_step,
            "time_saved_minutes": c.time_saved_minutes,
            "created_at": c.created_at,
        }
        for c in rows
    ]
'''

with io.open(p, 'a', encoding='utf-8') as f:
    f.write(block)
print("APPENDED OK,", len(block), "chars")
