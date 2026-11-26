# แผนที่ระบบ Smart Classroom Support (อัปเดต 26 พ.ย. 2026)

อ่านไฟล์นี้ก่อนแก้อะไรก็ตาม: บอกว่าแต่ละส่วนอยู่ที่ไหน เชื่อมกับอะไร และข้อมูลไหลไปทางไหน
รายละเอียดการดูแลระบบ/งานค้างอยู่ใน [`HANDOFF.md`](../HANDOFF.md)

## 1. ภาพรวม

```
 ลูกค้า/ครู (เบราว์เซอร์, สแกน QR)          เจ้าหน้าที่/ช่าง (เบราว์เซอร์)
              │                                       │
              ▼                                       ▼
   ┌──────────────────────── Frontend (Vercel) ────────────────────────┐
   │ React + Vite   iwasmart-service.vercel.app   โค้ด: frontend/        │
   └──────────────────────────────┬─────────────────────────────────────┘
                                  │ HTTPS /api/*  (frontend/src/api/client.ts)
                                  ▼
   ┌──────────────────────── Backend (Render) ─────────────────────────┐
   │ FastAPI  smart-classroom-backend-3tv7.onrender.com  โค้ด: backend/app/ │
   └──┬──────────┬──────────────┬──────────────┬──────────────┬─────────┘
      │          │              │              │              │
      ▼          ▼              ▼              ▼              ▼
  Supabase    Gemini AI     LINE API       Cloudflare R2   Google Sheets
  (Postgres)  (Google)      (ส่งข้อความ)    (ไฟล์แนบ/รูป)    (สมาชิก/lead)
      ▲                         ▲
      │                         │ push แจ้งเตือนกลุ่ม
      │            ┌────────────┴───────── n8n (Railway) ──────────────┐
      │            │ รับ LINE webhook → ส่งต่อ backend, cron SLA,       │
      └── SLA cron ┤ keep-alive, แจ้งเตือนกลุ่ม LINE  โค้ด: n8n_workflows/ │
                   └────────────▲───────────────────────────────────────┘
                                │ webhook
                        LINE OA (ลูกค้าคุยในแอป LINE)
```

## 2. ส่วนประกอบ: อยู่ที่ไหน → เชื่อมกับอะไร

| ส่วน | ให้บริการโดย | โค้ด/ตั้งค่า | เชื่อมไปที่ | ตั้งค่าอยู่ที่ |
|---|---|---|---|---|
| หน้าเว็บ | Vercel | `frontend/` (แผนที่หน้า: `frontend/README.md`) | backend `/api/*` (Vercel ส่งต่อ `/api/*` และ `/uploads/*` ไป Render ตาม `frontend/vercel.json`) | `frontend/vercel.json`, env `VITE_API_URL` (ไม่บังคับ) |
| API | Render (free, หลับถ้าไม่มีคนใช้ ~15 นาที) | `backend/app/main.py` (+ โมดูลใน `backend/app/`) | Supabase, Gemini, LINE, R2, Sheets, n8n | Render → Environment (`render.yaml` บอกรายชื่อ) |
| ฐานข้อมูล | **Supabase** โปรเจกต์ `smart-classroom-support` (Singapore, ฟรี) | ตาราง: `backend/app/models.py` | – | `DATABASE_URL` บน Render |
| ฐานข้อมูลเก่า (สำรอง) | Neon | – | ไม่มีใครต่อแล้ว (ใช้กลับได้ถ้ามีปัญหา) | – |
| LINE + งานตั้งเวลา | n8n บน Railway | `n8n_workflows/*.json` | LINE API, backend | Railway → service `n8n` |
| AI | Google Gemini | `backend/app/ai_client.py` | – | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| ไฟล์แนบ | Cloudflare R2 | `backend/app/storage.py` | – | `STORAGE_BACKEND=cloud`, `S3_*` |
| สมาชิก/ยอดขาย | Google Sheets | `backend/app/google_sheets.py` | – | `GOOGLE_*` |

## 3. เส้นทางข้อมูลหลัก (ทีละขั้น)

**ก. ลูกค้าสแกน QR แจ้งซ่อม**
1. สแกนสติกเกอร์ → `/?t=<token>` หรือ `/?device=<รหัส>` → `PublicNoLoginReportView.tsx`
2. ฟอร์มเรียก `GET /api/qr/resolve/{token}` (หาอุปกรณ์) แล้ว `POST /api/public/report`
3. backend บันทึก Ticket ลง Supabase (`repair_tickets`) → `dispatch.py` ส่งงานให้ช่างที่ว่าง
4. `_notify_n8n()` ส่ง event ไป n8n `/webhook/notify` → n8n push ข้อความเข้ากลุ่ม LINE เจ้าหน้าที่
5. ลูกค้าได้เลข Ticket ติดตามที่ `/?ticket=<เลข>` → `GET /api/tickets/track/{no}`

**ข. ลูกค้าคุยกับ LINE OA**
1. LINE → n8n workflow "LINE → Backend" (`/webhook/line-webhook`)
2. n8n → `POST /api/line/webhook?k=<N8N_SHARED_SECRET>` บน backend
3. `chatbot_core.handle_message()` ตัดสินใจ: ตอบจาก KB / ถามข้อมูล / สร้าง Ticket / ตรวจประกัน (ใช้ Gemini ผ่าน `gemini_service.py`)
4. ตอบกลับ: `line_bot.py` ส่งตรงไป LINE API (`api.line.me`) ด้วย `LINE_CHANNEL_TOKEN`

**ค. แชต AI บนหน้าเว็บ**
`AIChatWidget.tsx` → `POST /api/chatbot/web` → `web_agent.reply()` → Gemini (ใช้ KB + แค็ตตาล็อก + สถานะ Ticket จริง)
ถ้า Gemini ใช้ไม่ได้ → `chatbot_core` แบบกฎ + แปลภาษาด้วย `chatbot_i18n.py`

**ง. ส่งงานให้ช่าง (dispatch)**
Ticket ใหม่ → `dispatch.py` เลือกช่างที่ว่าง (on-duty, ติดต่อได้) → แจ้งทาง LINE (`line_bot.py`) + ป๊อปอัปในแอปเจ้าหน้าที่ (`/api/dispatch/me`)
ทุกคนยุ่ง → งานรอคิว คนที่ว่างก่อนได้งานเก่าสุด ตัวกวาดงานทำงานในตัว backend (ปิดได้ด้วย `DISPATCH_SWEEP_DISABLED=1`)

**จ. งานตั้งเวลาใน n8n**
| workflow (`n8n_workflows/`) | เรียก | ทุก |
|---|---|---|
| `wf_sla_check.json` | `GET /api/internal/sla/check` (อ่าน/เขียน Supabase) | 15 นาที |
| `wf_keepalive.json` | `GET /health` (กัน Render หลับ ไม่แตะฐานข้อมูล) | 10 นาที |

> Supabase ฟรีจะ **หยุดโปรเจกต์ถ้าไม่มีการใช้งาน 7 วัน** (ตามเอกสาร Supabase) การเรียก SLA check ทุก 15 นาทีนับเป็นการใช้งาน
> ถ้า n8n ล่ม ให้เช็ค Supabase dashboard ถ้าถูกหยุด กด Restore ได้

## 4. ตัวแปร env ของ backend (ตั้งใน Render → Environment)

| ตัวแปร | ใช้กับ | อ่านในไฟล์ |
|---|---|---|
| `DATABASE_URL` | Supabase (Session pooler, `sslmode=require`) | `models.py` |
| `JWT_SECRET` | ลงชื่อ token ล็อกอิน + ลิงก์ไฟล์ | `main.py`, `storage.py` |
| `CORS_ORIGINS` | โดเมน frontend ที่อนุญาต | `main.py` |
| `N8N_SHARED_SECRET` | รหัสลับระหว่าง n8n ↔ backend | `main.py` |
| `N8N_WEBHOOK_URL` | ที่อยู่ n8n สำหรับส่งแจ้งเตือน (`.../webhook/`) | `main.py` |
| `LINE_CHANNEL_TOKEN`, `LINE_CHANNEL_SECRET`, `LINE_GROUP_ID` | LINE Messaging API | `line_bot.py`, `main.py` |
| `LINE_WORKERS` | จำนวน thread ประมวลผลข้อความ LINE | `main.py` |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TUNED_ENDPOINT` | Google Gemini | `ai_client.py`, `gemini_service.py` |
| `ENABLE_GEMINI_CLASSIFIER`, `ENABLE_GEMINI_ORCHESTRATION`, `ENABLE_GEMINI_NATURAL_REPLIES` | เปิด/ปิดขั้น AI ของแชตบอต LINE | `chatbot_core.py`, `gemini_service.py` |
| `STORAGE_BACKEND`, `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `UPLOAD_URL_SECRET`, `MAX_UPLOAD_MB` | Cloudflare R2 / ไฟล์แนบ | `storage.py` |
| `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_*_RANGE` | Google Sheets | `google_sheets.py` |
| `REPORT_FORM_URL`, `CUSTOMER_SIGNUP_URL`, `STAFF_APP_URL` | ลิงก์ที่บอทส่งให้ผู้ใช้ | `chatbot_core.py`, `line_report_link.py`, `chatbot_helpers.py`, `dispatch.py` |
| `AUTO_ASSIGN_ENABLED`, `DISPATCH_*` | ระบบส่งงานให้ช่าง | `dispatch.py` |
| `RATINGS_VIEWER_USERNAME` | บัญชีที่ดูผลประเมินได้ | `main.py` |
| `ENVIRONMENT`, `LOG_LEVEL`, `CACHE_*`, `FAQ_CACHE_TTL_SECONDS` | ทั่วไป | หลายไฟล์ |
| `BOOTSTRAP_LOCAL_ADMIN`, `LOCAL_ADMIN_*` | สร้างแอดมินในเครื่องเท่านั้น | `main.py` |

`SMTP_*` ใน `.env.example` ยังไม่มีโค้ดใช้ (อีเมลแจ้งเตือนยังไม่ได้ทำ)

## 5. โครงโฟลเดอร์

| โฟลเดอร์ | คืออะไร |
|---|---|
| `backend/app/` | โค้ด API (ทุกไฟล์มีหัว "แผนที่ไฟล์" บอกหน้าที่ / ใครเรียก / เชื่อมไปไหน) |
| `backend/chatbot_prompts/` | คำแนะนำ AI ค่าเริ่มต้น + **README แผนที่ prompt ทั้งหมด** |
| `backend/tests/` | ชุดเทสต์อัตโนมัติ (pytest) |
| `backend/scripts/` | สคริปต์ดูแลระบบ: migration, สำรอง, seed, smoke (ดู README ในโฟลเดอร์) |
| `frontend/` | หน้าเว็บ (ดู `frontend/README.md`) |
| `n8n_workflows/` | สำเนา workflow n8n สำหรับกู้คืน |
| `scripts/` | เครื่องมือ fine-tune AI + ทดสอบบอท (CI) |
| `docs/` | คู่มือผู้ใช้, คู่มือแชตบอต, แผนที่ระบบนี้ |
| `backups/` | ไฟล์สำรองฐานข้อมูล (ไม่ขึ้น git) |
