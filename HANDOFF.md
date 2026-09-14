# HANDOFF — ระบบ Smart Classroom Support (สถานะ 14 ก.ย. 2026)

เอกสารนี้สำหรับผู้ที่จะรับช่วงดูแลระบบต่อ อ่านจบแล้วแก้ต่อได้เลย

---

## 1. สถาปัตยกรรมที่ใช้จริง

| ส่วน | ที่อยู่ | หมายเหตุ |
|---|---|---|
| Frontend | Vercel — `https://iwasmart-service.vercel.app` | React + Vite (static) |
| Backend | Render — `https://smart-classroom-backend-3tv7.onrender.com` | FastAPI, free tier **หลับหลังไม่มีคนใช้ ~15 นาที** |
| Database | Neon — `neondb` (ผู้ให้บริการ Postgres) | ต่อผ่าน `DATABASE_URL` ใน Render env |
| n8n | Railway — `https://n8n-production-3bcb9.up.railway.app` | มี volume `n8n-volume` แล้ว (ข้อมูลไม่หายเมื่อ redeploy) |
| ไฟล์อัปโหลด | Cloudflare R2 (`STORAGE_BACKEND=cloud`) | Render free ไม่มี disk ถาวร |
| ไลน์ | LINE OA → **n8n** → backend | backend เป็นเจ้าของบทสนทนา, n8n ทำหน้าที่ส่งต่อ + cron + แจ้งเตือน |

**ห้ามตัด n8n ออกจากเส้นทาง LINE** (เป็นข้อกำหนดของระบบ) — LINE Console ชี้ไปที่
`https://n8n-production-3bcb9.up.railway.app/webhook/line-webhook`

---

## 2. ⚠️ งานค้างที่ต้องทำก่อนบอทตอบผู้ใช้ได้จริง

**LINE Channel Access Token หมดอายุ** (ทดสอบแล้วได้ `401 Authentication failed`)

ตอนนี้ระบบทำงานครบทุกส่วน **ยกเว้นการตอบกลับเข้า LINE จริง** เพราะ token ใช้ไม่ได้

วิธีแก้:
1. เข้า LINE Developers Console → Messaging API channel → **Channel access token (long-lived)** → Issue
2. นำ token ใหม่ไปตั้ง **2 ที่** (ต้องตรงกันทั้งคู่):
   - Render → service `smart-classroom-backend` → Environment → `LINE_CHANNEL_TOKEN`
   - Railway → service `n8n` → Variables → `LINE_CHANNEL_TOKEN`
3. ทดสอบ: ส่งข้อความหา OA แล้วดูว่า backend มี log (ตาราง `chatbot_logs`) และมีข้อความตอบกลับใน LINE

---

## 3. n8n — workflow ที่ติดตั้งอยู่ (4 ตัว, active ทั้งหมด)

| ชื่อ | ทำงานอะไร |
|---|---|
| `LINE → Backend (Smart Classroom)` | รับ LINE webhook → ส่งต่อ backend `/api/line/webhook` (แนบ secret) |
| `Notification Dispatcher (จาก backend)` | รับ event จาก backend (`/webhook/notify`) → push ข้อความเข้ากลุ่ม LINE เจ้าหน้าที่ |
| `SLA Check (ทุก 15 นาที)` | เรียก `/api/internal/sla/check` เพื่อยกระดับงานเกินกำหนด |
| `Keep-alive backend (ทุก 10 นาที)` | ยิง `/health` กัน Render หลับ (ไม่งั้น LINE ตอบช้า/error) |
| `Smart Classroom - All-in-One (WF1-WF5)` | webhook เสริม: `qr-scan`, `web-report`, `ticket-status`, `ticket-update` (สาขา LINE ตัดออกแล้ว) |

**การแก้ workflow** (n8n 2.38):
```bash
railway ssh --service n8n -- "n8n import:workflow --input=/tmp/ชื่อไฟล์.json"
railway ssh --service n8n -- "n8n publish:workflow --id=<workflow-uuid>"
railway restart --service n8n --yes     # ต้อง restart ไม่งั้น webhook ยัง 404
```
- ไฟล์ JSON ต้นทางอยู่ในโฟลเดอร์ `_n8n_restore/` ของโปรเจกต์
- ดูรายการ: `railway ssh --service n8n -- "n8n list:workflow"`
- `n8n update:workflow --all --active=true` **ใช้ไม่ได้แล้ว** ในเวอร์ชันนี้

---

## 4. กับดักที่ต้องรู้ (เจอจริงมาแล้ว)

1. **Render `PUT /v1/services/{id}/env-vars` = ลบตัวแปรอื่นทั้งหมด** — ให้ใช้
   `PUT /v1/services/{id}/env-vars/{KEY}` ทีละตัว แล้ว `GET` ตรวจว่ายังครบ
2. **Railway redeploy = ข้อมูล service หาย ถ้าไม่มี volume** (n8n เคยหายมาแล้วครั้งหนึ่ง)
3. **Render free หลับ** → request แรกอาจช้า 30-60 วิ หรือได้หน้า "Application loading"
   (มี workflow keep-alive แก้ไว้แล้ว)
4. **n8n re-serialize body ของ LINE** → `X-Line-Signature` ของ LINE ใช้ไม่ได้
   จึงใช้ shared secret ระหว่าง n8n กับ backend (header `X-N8N-Secret` หรือ query `?k=`)
   ค่าอยู่ใน `_n8n_secret.txt` (gitignore) และใน env ของ Render (`N8N_SHARED_SECRET`) + workflow JSON
5. **`create_all()` ไม่ ALTER ตารางเดิม** — เพิ่มคอลัมน์ต้อง `ALTER TABLE` เอง
6. **sequence ของ Postgres** หลัง migrate ข้อมูลต้อง `setval` ไม่งั้น INSERT ตอบ 500

---

## 5. สิทธิ์การเข้าถึง (RBAC) ที่ใช้อยู่

| บทบาท | เห็นข้อมูล |
|---|---|
| `owner` | ทุกโรงเรียน (สูงสุด, role อื่นแก้ไม่ได้) |
| `super_admin`, `admin` | ทุกโรงเรียน |
| `admin_school` | เฉพาะโรงเรียนตัวเอง (จัดการอุปกรณ์/user/KB เฉพาะของตัวเอง) |
| `it_support` (ไม่มีสังกัด) | ทุกโรงเรียน |
| `it_support` (มีสังกัด) | เฉพาะโรงเรียนตัวเอง + ไม่มีปุ่มแก้ไข KB |
| `teacher`, `student` | เฉพาะโรงเรียนตัวเอง |

---

## 6. สคริปต์ทดสอบที่มีให้ (ใน `backend/scripts/`)

```bash
cd backend
DATABASE_URL='<neon>' JWT_SECRET=x PYTHONPATH=. .venv/Scripts/python.exe scripts/smoke_chatbot.py    # ทดสอบบอท 9 สถานการณ์
DATABASE_URL='<neon>' JWT_SECRET=x PYTHONPATH=. .venv/Scripts/python.exe scripts/smoke_line_real.py   # เคสจริงจาก log LINE
DATABASE_URL='<neon>' JWT_SECRET=x PYTHONPATH=. .venv/Scripts/python.exe scripts/verify_secure_line.py # ตรวจว่า endpoint ล็อกถูก
DATABASE_URL='<neon>' JWT_SECRET=x PYTHONPATH=. .venv/Scripts/python.exe scripts/cleanup_test_data.py  # ล้างข้อมูลทดสอบ
```

---

## 7. ลำดับการ deploy

- **Backend (Render)**: push ขึ้น `main` แล้ว Render deploy อัตโนมัติ หรือสั่งผ่าน API
- **Frontend (Vercel)**: `cd frontend && npm run build && vercel --prod`
- **n8n**: import + publish + restart (ดูข้อ 3)

---

## 8. การสำรองข้อมูล (สำคัญ — ทำก่อนแก้อะไรใหญ่ๆ)

| ต้องสำรอง | ที่เก็บ | วิธี |
|---|---|---|
| ฐานข้อมูล (Neon) | `backups/neondb_<วันเวลา>.sql` / `.json` | `cd backend` แล้ว `DATABASE_URL='<neon>' PYTHONPATH=. .venv/Scripts/python.exe scripts/backup_db.py` |
| n8n workflows | `n8n_workflows/` (ใน git) | ดึงจาก n8n แล้วบันทึกทับ (ดู README ในโฟลเดอร์) |
| โค้ด | GitHub | `git push` |
| ค่าตั้งค่า/ความลับ | `.env` ในเครื่อง + env ของ Render/Railway | ไม่ขึ้น git — เก็บสำเนาไว้ในที่ปลอดภัย |

**กู้คืนฐานข้อมูล**: ให้ backend รันหนึ่งครั้งเพื่อสร้างสคีมา แล้ว `psql < backups/neondb_xxx.sql`
(ไฟล์สำรองเป็นข้อมูลอย่างเดียว ไม่รวมสคีมา — สคีมาสร้างจาก models.py)

**บทเรียน**: ก่อน redeploy service ที่ไม่มี volume (เช่น n8n) ต้องสำรองก่อนทุกครั้ง — เคยทำข้อมูล n8n หายมาแล้วครั้งหนึ่ง
