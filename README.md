# Smart Classroom Support System

ระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนการบำรุงรักษาอุปกรณ์ Smart Classroom
(Online Repair Request and Smart Classroom Maintenance Support System)

โปรเจกต์ฝึกงานต้นแบบ (Prototype) — ข้อกำหนดและการออกแบบดูที่
`System_Blueprint_Smart_Classroom_IT_Support_v1_0.md` และ `วิเคราะห์และออกแบบระบบ.md`

> README นี้อธิบาย **การรันบนเครื่องด้วย Docker Compose**
> ระบบที่ deploy จริง (Vercel / Render / Neon / Railway), ค่าลับ, และงานค้างล่าสุด อยู่ใน [HANDOFF.md](HANDOFF.md)

## ภาพรวมฟีเจอร์

- **QR Code** — อุปกรณ์แต่ละเครื่องมี QR (URL + token) สแกนแล้วเปิดหน้าแจ้งซ่อมพร้อมข้อมูลอุปกรณ์/ห้องอัตโนมัติ ไม่ต้อง login
- **แจ้งซ่อมออนไลน์** — ฟอร์มแจ้งซ่อมไม่ต้องมีบัญชี (สแกน QR ได้เลย), กันแจ้งซ้ำอัตโนมัติ, AI แนะนำวิธีแก้เบื้องต้น
- **Ticket Management** — สถานะครบ (new → assigned → in_progress → resolved → closed/cancelled), มอบหมาย/รับงาน/ปิดงาน+ให้คะแนน, ติดตามสถานะด้วยเลข Ticket แบบสาธารณะ
- **Dashboard** — ภาพรวม + สถิติ แยกตามบทบาท (admin/teacher/student)
- **ฐานความรู้ (KB)** — บทความวิธีแก้ไข 30+ หัวข้อ + AI Troubleshooting (Gemini, ตอบจาก KB เท่านั้น)
- **Preventive Maintenance (PM)** — แผน/งานบำรุงรักษาเชิงป้องกัน + สร้างงานอัตโนมัติ
- **Multi-school** — แยกข้อมูลรายโรงเรียน (super_admin เห็นทุกโรงเรียน)
- **รายงาน** — สรุปสถานะ, ปัญหาที่พบบ่อย, อุปกรณ์ที่เสียบ่อย

## Tech Stack

| ชั้น | เทคโนโลยี |
|---|---|
| Frontend | React + TypeScript + Vite (port 5173) |
| Backend | FastAPI + SQLAlchemy (port 8000) |
| Database | PostgreSQL 16 (port 5432) · pgAdmin (5050) |
| Cache/Object | Redis (6379) · MinIO (9000/9001) |
| Automation | n8n (5678) |
| AI | Google Gemini API |
| Deploy | Docker Compose |

## โครงสร้างโปรเจกต์

```
smart-classroom-support/
├── docker-compose.yml      # ทั้งระบบ (postgres, backend, frontend, n8n, redis, minio, pgadmin)
├── .env                    # secrets (GEMINI_API_KEY, LINE...) — อย่า commit
├── backend/
│   ├── Dockerfile
│   └── app/
│       ├── main.py             # FastAPI — 70+ endpoints
│       ├── models.py           # SQLAlchemy models (17 ตาราง)
│       └── gemini_service.py   # เรียก Gemini API (REST)
├── frontend/
│   ├── Dockerfile
│   └── src/
│       ├── App.tsx             # routing + Dashboard + หน้า login/scan
│       ├── api/client.ts       # API client
│       └── components/         # หน้าแยก (Devices, Users, KB, PM, Scan...)
└── data/                    # (volume) ข้อมูล
```

## วิธีเริ่มระบบ

```bash
# 1. สร้าง .env จาก template (ใส่ GEMINI_API_KEY)
cp .env.example .env   # หรือสร้างเองตามด้านล่าง

# 2. Build + เริ่มทุก service
docker compose up -d --build

# 3. เข้าถึง
#    Frontend: http://localhost:5173
#    Backend API docs (Swagger): http://localhost:8000/docs
#    pgAdmin: http://localhost:5050
#    n8n: http://localhost:5678
#    MinIO console: http://localhost:9001
```

`.env` ตัวอย่าง:

```bash
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-flash-latest
LINE_CHANNEL_SECRET=
LINE_CHANNEL_TOKEN=
```

> หมายเหตุ: backend อ่าน env จาก `.env` (ผ่าน `env_file` ใน compose) — ถ้าแก้โค้ดต้อง `docker compose build` ใหม่ (ภาพไม่ mount source) + `up -d --force-recreate`

## บัญชีเริ่มต้น

สร้างด้วย `backend/scripts/seed_admin.py` (สคริปต์นี้ **ล้างข้อมูลทั้งฐาน** — สำรองก่อน)

| บทบาท | username | password |
|---|---|---|
| `super_admin` | `iwasuperadmin` | ตั้งผ่าน env `SEED_ADMIN_PASSWORD` ตอนรันสคริปต์ (ค่าเริ่มต้น `IwaScr2026!admin`) |

bash
cd backend
DATABASE_URL='<connection string>' JWT_SECRET=x PYTHONPATH=. \
 SEED_ADMIN_PASSWORD='<รหัสที่ต้องการ>' python scripts/seed_admin.py --yes


> เปลี่ยนรหัสผ่านได้หลัง login ที่หน้า "โปรไฟล์"

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

## รูปแบบ ID

- **Ticket:** `SC-YYYY-NNNNNN` เช่น `SC-2026-000001` (ของเดิม `TK-YYYYMM-XXXX` ยังค้นหาได้)
- **Device:** `{SCHOOL}-B{อาคาร}-{ห้อง}-{TYPE}-{ลำดับ}` เช่น `SCHE2E-B1-201-DISP-01`
- **PM task:** `PM-YYYYMM-XXXX`

## QR Code

- QR ฝัง URL + token เท่านั้น (`/scan?t={token}`) ไม่ฝังข้อมูลอุปกรณ์ → ย้ายอุปกรณ์ได้ไม่ต้องพิมพ์ใหม่
- ข้อมูลอุปกรณ์/ห้องอ่านจาก DB ตอน resolve token (ผ่าน `GET /api/qr/resolve/{token}`)
- สร้าง QR ได้ที่หน้า "อุปกรณ์" (ปุ่ม QR ต่อเครื่อง) + "พิมพ์ QR" (batch)

## ดูรายละเอียด API

- รันระบบแล้วเปิด `http://localhost:8000/docs` (Swagger UI อัตโนมัติ)
- เอกสารออกแบบ: `System_Blueprint_Smart_Classroom_IT_Support_v1_0.md`

## งานที่ยังค้าง / หมายเหตุ

สถานะจริงของระบบที่ deploy แล้วอยู่ใน [HANDOFF.md](HANDOFF.md) — ที่นี่สรุปเฉพาะที่ยังค้าง

- **ทดสอบ LINE จริงจากมือถือ** — ต้องมีคนส่งข้อความหา OA เองแล้วยืนยันว่ามีข้อความตอบกลับ (HANDOFF ข้อ 9 หัวข้อ 9)
- **ยืนยันข้อความแจ้งเตือนเข้ากลุ่ม LINE เจ้าหน้าที่** — ยังไม่ได้ตรวจด้วยข้อความจริง (HANDOFF ข้อ 9 หัวข้อ 10)
- **Gemini** — ต่อแล้ว แต่ key free tier quota จำกัด (เจอ 503 บ่อย) → มี fallback เป็น keyword match อัตโนมัติ ใช้ paid key เพื่อความเสถียร
- **n8n (บนเครื่อง)** — ถ้ารันด้วย docker compose ต้อง setup owner ผ่าน UI (`localhost:5678`) ก่อน แล้ว import ไฟล์ใน `n8n_workflows/` (รัน `python n8n_workflows/prepare_import.py` แทนค่าลับก่อน import)
- **ไฟล์ `vite.config.ts` ที่ราก repo** — เป็นของเก่าที่ไม่ถูกใช้ (ตัวจริงคือ `frontend/vite.config.ts`) ลบทิ้งได้
