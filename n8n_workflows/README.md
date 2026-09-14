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

> หมายเหตุ: workflow ชุดนี้ตั้งใจให้ **backend เป็นเจ้าของบทสนทนา LINE** (n8n ทำหน้าที่ส่งต่อ + cron + แจ้งเตือน)
> ไม่ใช่ All-in-One 72 โหนดเดิม — ดู HANDOFF.md หัวข้อ 3
