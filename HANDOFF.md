# HANDOFF — ระบบ Smart Classroom Support (สถานะ 26 พ.ย. 2026)

เอกสารนี้สำหรับผู้ที่จะรับช่วงดูแลระบบต่อ อ่านจบแล้วแก้ต่อได้เลย

**เริ่มที่นี่:**
1. [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md) — ส่วนไหนอยู่ที่ไหน เชื่อมกับอะไร ข้อมูลไหลทางไหน ตัวแปร env ทั้งหมด
2. [`frontend/README.md`](frontend/README.md) — URL → หน้า → API
3. [`backend/chatbot_prompts/README.md`](backend/chatbot_prompts/README.md) — prompt AI ทั้งหมด และวิธีแก้
4. [`backend/scripts/README.md`](backend/scripts/README.md) — สคริปต์ดูแลระบบ ตัวไหนเขียนข้อมูลจริง
5. ทุกไฟล์ใน `backend/app/` มีหัว "แผนที่ไฟล์" บอกหน้าที่ / ใครเรียก / เชื่อมไปไหน / env ที่อ่าน

---

## 1. สถาปัตยกรรมที่ใช้จริง

| ส่วน | ที่อยู่ | หมายเหตุ |
|---|---|---|
| Frontend | Vercel — `https://iwasmart-service.vercel.app` | React + Vite (static) |
| Backend | Render — `https://smart-classroom-backend-3tv7.onrender.com` | FastAPI, free tier **หลับหลังไม่มีคนใช้ ~15 นาที** |
| Database | **Supabase** — โปรเจกต์ `smart-classroom-support` (Singapore, ฟรี) | ย้ายจาก Neon เมื่อ 26 พ.ย. 2026 — ต่อผ่าน `DATABASE_URL` ใน Render env |
| n8n | Railway — `https://n8n-production-3bcb9.up.railway.app` | มี volume `n8n-volume` (ข้อมูลไม่หายเมื่อ redeploy) |
| ไฟล์อัปโหลด | Cloudflare R2 (`STORAGE_BACKEND=cloud`) | Render free ไม่มี disk ถาวร |
| ไลน์ | LINE OA → **n8n** → backend | backend เป็นเจ้าของบทสนทนา, n8n ทำหน้าที่ส่งต่อ + cron + แจ้งเตือน |

**ห้ามตัด n8n ออกจากเส้นทาง LINE** (เป็นข้อกำหนดของระบบ) — LINE Console ชี้ไปที่
`https://n8n-production-3bcb9.up.railway.app/webhook/line-webhook`

---

## 2. ฐานข้อมูล Supabase

- **ต้องใช้ “Session pooler”** (Supabase → Connect → Direct → Session pooler, port 5432, ผู้ใช้ `postgres.<project-ref>`)
  ห้ามใช้ Direct connection (`db.<ref>.supabase.co`) เพราะเป็น IPv6 อย่างเดียว Render และ Docker ต่อไม่ได้
  ต่อท้าย URL ด้วย `?sslmode=require`
- **Data API ปิดอยู่** และ **เปิด RLS ทุกตาราง** — backend ต่อเป็น `postgres` จึงไม่ติด RLS แต่คนนอกอ่านตารางผ่าน API ของ Supabase ไม่ได้
  ถ้าเพิ่มตารางใหม่ Supabase เปิด RLS ให้อัตโนมัติ (ตั้งไว้ตอนสร้างโปรเจกต์) รัน `migrate_to_supabase.sh lock` ซ้ำได้ถ้าไม่แน่ใจ
- **โปรเจกต์ฟรีถูกหยุดถ้าไม่มีการใช้งาน 7 วัน** — n8n เรียก SLA check ทุก 15 นาทีซึ่งแตะฐานข้อมูลอยู่แล้ว
  ถ้าโดนหยุด: เข้า Supabase dashboard → กด Restore (ควรเช็คก่อนวันนำเสนองาน)
- เครื่องมือ: `bash backend/scripts/migrate_to_supabase.sh check|dump|restore|verify|lock|backup`
  อ่าน URL จาก `.env.migrate` (ไม่ขึ้น git) ต้องมี Docker (ใช้ image `postgres:18` เพราะ Neon เดิมเป็น PG18, Supabase เป็น PG17)
- **ถอยกลับ Neon**: เปลี่ยน `DATABASE_URL` ใน Render กลับเป็นของ Neon (ฐานข้อมูล Neon ยังอยู่ ไม่ได้ลบ แต่ข้อมูลหยุดที่ 26 พ.ย. 2026)

---

## 3. n8n — workflow ที่ติดตั้งอยู่ (active ทั้งหมด)

| ชื่อ | ทำงานอะไร |
|---|---|
| `LINE → Backend (Smart Classroom)` | รับ LINE webhook → ส่งต่อ backend `/api/line/webhook` (แนบ secret) |
| `Notification Dispatcher (จาก backend)` | รับ event จาก backend (`/webhook/notify`) → push ข้อความเข้ากลุ่ม LINE เจ้าหน้าที่ |
| `SLA Check (ทุก 15 นาที)` | เรียก `/api/internal/sla/check` เพื่อยกระดับงานเกินกำหนด |
| `Keep-alive backend (ทุก 10 นาที)` | ยิง `/health` กัน Render หลับ (ไม่งั้น LINE ตอบช้า/error) |
| `Smart Classroom - All-in-One (WF1-WF5)` | webhook เสริม: `qr-scan`, `web-report`, `ticket-status`, `ticket-update` (สาขา LINE ตัดออกแล้ว) |

ไฟล์ต้นฉบับอยู่ใน `n8n_workflows/` (ค่าลับแทนด้วย `<N8N_SHARED_SECRET>`) วิธี import ดู `n8n_workflows/README.md`:
```bash
railway ssh --service n8n -- "n8n import:workflow --input=/tmp/ชื่อไฟล์.json"
railway ssh --service n8n -- "n8n publish:workflow --id=<workflow-uuid>"
railway restart --service n8n --yes     # ต้อง restart ไม่งั้น webhook ยัง 404
```

---

## 4. กับดักที่ต้องรู้ (เจอจริงมาแล้ว)

1. **Render `PUT /v1/services/{id}/env-vars` = ลบตัวแปรอื่นทั้งหมด** — ใช้ `PUT /v1/services/{id}/env-vars/{KEY}` ทีละตัว
2. **Railway redeploy = ข้อมูล service หาย ถ้าไม่มี volume** (n8n เคยหายมาแล้วครั้งหนึ่ง)
3. **Render free หลับ** → request แรกอาจช้า 30-60 วิ (มี workflow keep-alive แก้ไว้แล้ว)
4. **n8n re-serialize body ของ LINE** → `X-Line-Signature` ใช้ไม่ได้ จึงใช้ shared secret ระหว่าง n8n กับ backend
   (header `X-N8N-Secret` หรือ query `?k=`) ค่าอยู่ใน env ของ Render (`N8N_SHARED_SECRET`) + workflow ใน n8n
5. **`create_all()` ไม่ ALTER ตารางเดิม** — เพิ่มคอลัมน์ต้องเขียน migration (ดู `backend/scripts/migrate_*.py`)
6. **ย้ายฐานข้อมูลด้วยการ INSERT เอง ต้อง `setval` sequence** — ใช้ `migrate_to_supabase.sh` (pg_dump) จะถูกต้องเอง
7. **prompt AI ที่บันทึกบนเว็บชนะไฟล์** — แก้ไฟล์ `chatbot_prompts/*.txt` แล้วไม่เห็นผล ให้กด “กลับไปใช้ค่าจากไฟล์” บนเว็บ
8. **repo เป็น PUBLIC** — ห้าม commit ค่าลับเด็ดขาด (`.env`, `.env.migrate`, token, API key)

---

## 5. สิทธิ์การเข้าถึง (RBAC) ที่ใช้อยู่

| บทบาท | เห็นข้อมูล |
|---|---|
| `owner` | ทุกโรงเรียน (สูงสุด, role อื่นแก้ไม่ได้) |
| `super_admin`, `admin` | ทุกโรงเรียน |
| `admin_school` | เฉพาะโรงเรียนตัวเอง (จัดการอุปกรณ์/user/KB เฉพาะของตัวเอง) |
| `it_support` (ไม่มีสังกัด) | ทุกโรงเรียน |
| `it_support` (มีสังกัด) | เฉพาะโรงเรียนตัวเอง + ไม่มีปุ่มแก้ไข KB |

ผู้แจ้งซ่อม (ครู/นักเรียน) ไม่มีบัญชี — แจ้งผ่านฟอร์ม QR สาธารณะ (บทบาท teacher/student ยกเลิกแล้ว)

---

## 6. รันในเครื่อง และทดสอบ

```bash
docker compose up -d postgres redis backend frontend   # ห้าม `up` เฉย ๆ (image minio หายจาก Docker Hub)
# เว็บ http://127.0.0.1:5173   API http://127.0.0.1:8000/docs
```

**เทสต์อัตโนมัติ** (ทุกไฟล์อยู่ใน `backend/tests/`; ชี้ฐานข้อมูลในเครื่องเท่านั้น):
```bash
docker run --rm --network smart-classroom-support_default -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL=postgresql+psycopg2://postgres:postgres@postgres:5432/smart_classroom \
  -e JWT_SECRET=test -e DISPATCH_SWEEP_DISABLED=1 smart-classroom-support-backend \
  sh -c "pip install -q pytest==8.3.4 && python -m pytest -q"
docker exec smart_classroom_frontend npx tsc --noEmit
docker exec smart_classroom_frontend npx vitest run
```
ผลล่าสุด (26 พ.ย. 2026): backend 198 passed / 15 skipped, vitest 27 passed, tsc ผ่าน

**Smoke test กับระบบจริง** (เขียนข้อมูลจริง อ่าน `backend/scripts/README.md` ก่อน):
```bash
cd backend
DATABASE_URL='<production-url>' JWT_SECRET=x PYTHONPATH=. python scripts/smoke_chatbot.py
DATABASE_URL='<production-url>' JWT_SECRET=x PYTHONPATH=. python scripts/cleanup_test_data.py
```

---

## 7. ลำดับการ deploy

- **Backend (Render)**: push ขึ้น `main` แล้ว Render deploy อัตโนมัติ (startCommand รัน migration ที่จำเป็นให้ก่อน)
- **Frontend (Vercel)**: deploy จาก GitHub หรือ `cd frontend && npm run build && vercel --prod`
- **n8n**: import + publish + restart (ดูข้อ 3)

---

## 8. การสำรองข้อมูล (สำคัญ — ทำก่อนแก้อะไรใหญ่ ๆ)

| ต้องสำรอง | ที่เก็บ | วิธี |
|---|---|---|
| ฐานข้อมูล (แนะนำ) | `backups/supabase_<วันเวลา>.dump` + `.counts.txt` | `bash backend/scripts/migrate_to_supabase.sh backup` (ใช้ `SUPABASE_URL` ใน `.env.migrate`) |
| ฐานข้อมูล (แบบ SQL อ่านง่าย) | `backups/db_<วันเวลา>.sql/.json` | `cd backend && DATABASE_URL='<url>' PYTHONPATH=. python scripts/backup_db.py` |
| n8n workflows | `n8n_workflows/` (ใน git) | ดึงจาก n8n แล้วบันทึกทับ (ดู README ในโฟลเดอร์) |
| โค้ด | GitHub | `git push` |
| ค่าตั้งค่า/ความลับ | `.env`, `.env.migrate` ในเครื่อง + env ของ Render/Railway | ไม่ขึ้น git — เก็บสำเนาไว้ในที่ปลอดภัย |

**บทเรียน**: ก่อน redeploy service ที่ไม่มี volume (เช่น n8n) ต้องสำรองก่อนทุกครั้ง

---

## 9. งานค้าง / สิ่งที่ต้องทำต่อ

| # | รายการ |
|---|---|
| 1 | **หมุน (เปลี่ยน) n8n API key** — สคริปต์เก่าที่ลบไปแล้วเคยมี API key ฝังอยู่ และยังอยู่ในประวัติ git ของ repo สาธารณะ: n8n → Settings → API → ลบ key เก่า สร้างใหม่ |
| 2 | ทดสอบด้วย LINE จริงจากมือถือ และข้อความแจ้งเตือนเข้ากลุ่ม LINE เจ้าหน้าที่ |
| 3 | Render ต้องตั้ง `GEMINI_API_KEY` / `GEMINI_MODEL` / `ENABLE_GEMINI_*` ให้แชต AI หน้าเว็บตอบแบบสนทนาได้ |
