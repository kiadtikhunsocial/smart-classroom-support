# Smart Classroom Support System

ระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนการบำรุงรักษาอุปกรณ์ Smart Classroom
(Online Repair Request and Smart Classroom Maintenance Support System)

ข้อกำหนดและการออกแบบ: `System_Blueprint_Smart_Classroom_IT_Support_v1_0.md` และ `วิเคราะห์และออกแบบระบบ.md`

## 📚 เอกสารสำหรับคนที่จะทำต่อ (อ่านตามลำดับ)

| เอกสาร | อ่านเมื่อ |
|---|---|
| [HANDOFF.md](HANDOFF.md) | ระบบที่ deploy จริง, ฐานข้อมูล Supabase, กับดัก, งานค้าง |
| [docs/SYSTEM_MAP.md](docs/SYSTEM_MAP.md) | ส่วนไหนเชื่อมกับอะไร ข้อมูลไหลทางไหน ตัวแปร env ทั้งหมด |
| [frontend/README.md](frontend/README.md) | URL → หน้า → API ของหน้าเว็บ |
| [backend/chatbot_prompts/README.md](backend/chatbot_prompts/README.md) | prompt AI ทุกตัวอยู่ที่ไหน และแก้ยังไง (บนเว็บ / ไฟล์ / โค้ด) |
| [backend/scripts/README.md](backend/scripts/README.md) | สคริปต์ดูแลระบบ ตัวไหนเขียนข้อมูลจริง |
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | คู่มือผู้ใช้ |

ทุกไฟล์ใน `backend/app/` มีหัว "แผนที่ไฟล์" บอกหน้าที่ / ใครเรียก / เชื่อมไปไหน / env ที่อ่าน
`backend/app/main.py` มีสารบัญ endpoint อยู่ด้านบนไฟล์

## ภาพรวมฟีเจอร์

- **QR Code** — อุปกรณ์แต่ละเครื่องมี QR (URL + token) สแกนแล้วเปิดฟอร์มแจ้งซ่อมพร้อมข้อมูลอุปกรณ์/ห้อง ไม่ต้อง login
- **แจ้งซ่อมออนไลน์** — ไม่ต้องมีบัญชี, กันแจ้งซ้ำอัตโนมัติ, AI แนะนำวิธีแก้เบื้องต้น
- **Ticket Management** — new → assigned → in_progress → resolved → closed/cancelled, ติดตามสถานะด้วยเลข Ticket แบบสาธารณะ
- **ส่งงานให้ช่างอัตโนมัติ** — ช่างที่ว่างได้งานทันที, ทุกคนยุ่ง = รอคิว
- **LINE OA + แชต AI** — แชตบอต LINE และแชต AI บนหน้าเว็บ 5 ภาษา (Gemini, ตอบจากฐานความรู้เท่านั้น)
- **ฐานความรู้ (KB)**, **บำรุงรักษาเชิงป้องกัน (PM)**, **หลายโรงเรียน**, **รายงาน**, **ยอดขาย/lead**

## Tech Stack

| ชั้น | เทคโนโลยี | production |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite | Vercel |
| Backend | FastAPI + SQLAlchemy (Python 3.11) | Render |
| Database | PostgreSQL | Supabase |
| Automation | n8n | Railway |
| AI | Google Gemini API | – |
| ไฟล์แนบ | S3-compatible | Cloudflare R2 |

## รันบนเครื่อง (Docker Desktop)

```bash
cp .env.example .env                                   # ใส่ค่าที่ต้องใช้ (GEMINI_API_KEY ฯลฯ)
docker compose up -d postgres redis backend frontend   # ห้ามใช้ `up` เฉย ๆ: image minio/minio หายจาก Docker Hub
```
- เว็บ: http://127.0.0.1:5173   ·   API docs (Swagger): http://127.0.0.1:8000/docs
- แก้โค้ด backend แล้วต้อง `docker compose up -d --build backend` (frontend mount โค้ดอยู่แล้ว แก้แล้วเห็นทันที)
- ข้อมูลตัวอย่าง: `docker compose exec backend python scripts/seed_mockup_5_schools.py` (ลบด้วย `--purge-only`)
- เทสต์: ดู HANDOFF.md ข้อ 6

## บัญชีสำหรับ local development

Docker Compose สร้างบัญชี local ให้ครั้งแรกโดยอัตโนมัติ (ไม่ลบ/ไม่ทับข้อมูล):

| บทบาท | username | password |
|---|---|---|
| `super_admin` | `admin` | `local-admin-change-me` |

เปลี่ยนได้ด้วย `LOCAL_ADMIN_USERNAME` / `LOCAL_ADMIN_PASSWORD` ใน `.env` ทำงานเฉพาะ `ENVIRONMENT=development`
(production จะไม่ยอม start ถ้าเปิด `BOOTSTRAP_LOCAL_ADMIN`)

## สถานะ Ticket

| สถานะ | ความหมาย |
|---|---|
| `new` | รอรับเรื่อง |
| `assigned` | มอบหมายช่างแล้ว |
| `in_progress` | กำลังซ่อม |
| `pending` | รออะไหล่/รอภายนอก |
| `resolved` | ซ่อมเสร็จ รอผู้แจ้งยืนยัน |
| `closed` | ปิดงาน |
| `cancelled` | ยกเลิก |

กฎการเปลี่ยนสถานะ: `backend/app/ticket_state.py`

## รูปแบบ ID

- **Ticket:** `TK.<รหัสโรงเรียน>.<ปี 2 หลัก>.<ลำดับ>-<ตัวตรวจสอบ>` เช่น `TK.SCHM01.26.0016-F` (สร้างที่ `generate_ticket_id()` ใน `main.py`)
- **Device:** `{SCHOOL}-B{อาคาร}-{ห้อง}-{TYPE}-{ลำดับ}` เช่น `SCHE2E-B1-201-DISP-01`
- **PM task:** `PM-YYYYMM-XXXX`

## QR Code

- QR ฝัง URL + token เท่านั้น (`/scan?t={token}`; Vercel ส่งทุก path ไปที่ `index.html` แล้ว `App.tsx` อ่าน `?t=`) ไม่ฝังข้อมูลอุปกรณ์ → ย้ายอุปกรณ์ได้ไม่ต้องพิมพ์ใหม่
- ข้อมูลอุปกรณ์/ห้องอ่านจากฐานข้อมูลตอน resolve token (`GET /api/qr/resolve/{token}`)
- สร้าง QR ได้ที่หน้า "อุปกรณ์" (ต่อเครื่อง) และ "พิมพ์ QR" (ทีละหลายเครื่อง)
- `backend/scripts/generate_qr.py` สร้าง QR ออฟไลน์จากฐานข้อมูลที่ต่ออยู่ (ผลลัพธ์ `qr_codes/` ไม่ขึ้น git)
