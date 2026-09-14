# n8n workflows (สำเนาสำหรับกู้คืน)

ไฟล์ในโฟลเดอร์นี้คือ workflow ที่ใช้งานจริงบน Railway (service `n8n`)
เก็บไว้เพื่อ **กู้คืนได้เสมอ** — n8n บน Railway เก็บข้อมูลใน volume ถ้า volume หาย งานหายทั้งหมด

## วิธีนำกลับเข้า n8n
```bash
# 1) แทนที่ <N8N_SHARED_SECRET> ด้วยค่าจริง (ดูใน Render env: N8N_SHARED_SECRET)
# 2) ส่งไฟล์เข้า container แล้ว import
railway ssh --service n8n -- "n8n import:workflow --input=/tmp/<ไฟล์>.json"
railway ssh --service n8n -- "n8n publish:workflow --id=<workflow-uuid>"   # ต้อง publish รายตัว
railway restart --service n8n --yes                                        # ต้อง restart ไม่งั้น webhook 404
```

## รายการ workflow
| ไฟล์ | ชื่อใน n8n | หน้าที่ |
|---|---|---|
| wf_line_forward.json | LINE → Backend (Smart Classroom) | รับ LINE webhook → ส่งต่อ backend |
| wf_notify.json | Notification Dispatcher (จาก backend) | รับ event จาก backend → push กลุ่ม LINE |
| wf_sla_check.json | SLA Check (ทุก 15 นาที) | เรียก /api/internal/sla/check |
| wf_keepalive.json | Keep-alive backend (ทุก 10 นาที) | ยิง /health กัน Render หลับ |
| wf_allinone.json | Smart Classroom - All-in-One (WF1-WF5) | webhook เสริม: qr-scan / web-report / ticket-status / ticket-update |

> หมายเหตุ: workflow ชุดนี้ตั้งใจให้ **backend เป็นเจ้าของบทสนทนา LINE** (n8n ทำหน้าที่ส่งต่อ + cron + แจ้งเตือน)
> ไม่ใช่ All-in-One 72 โหนดเดิม — ดู HANDOFF.md หัวข้อ 3

## All-in-One (wf_allinone.json)
- **สาขา LINE ถูกตัดออกแล้ว** (`Webhook - LINE OA` ถูกลบ) — บทสนทนา LINE เป็นของ backend ผ่าน workflow `LINE → Backend`
- webhook ที่ใช้ได้: 
  - `GET  /webhook/qr-scan?deviceId=xxx` → คืนข้อมูลอุปกรณ์ที่ต้องเติมในฟอร์ม
  - `GET  /webhook/ticket-status?ticketNo=TK-YYYYMM-XXXX` → สถานะงาน
  - `POST /webhook/web-report` → สร้าง ticket จากฟอร์มเว็บ (เรียก backend)
  - `POST /webhook/ticket-update` → เจ้าหน้าที่อัปเดตสถานะ (เรียก backend ด้วย X-N8N-Secret)
- **หมายเหตุ n8n 2.38**: webhook path ที่มี `:param` **ไม่ถูกลงทะเบียน** จึงเปลี่ยนมาใช้ query string แทน
- โหนดที่เหลือของสาขา LINE (Postgres/Gemini เดิม) เป็นโหนดที่ไม่มีทางถูกเรียก — เก็บไว้เป็นข้อมูลอ้างอิง
