# backend/scripts — สคริปต์ดูแลระบบ

สคริปต์ทุกตัวในโฟลเดอร์นี้ **ไม่ใช่ส่วนของเว็บ** (เว็บคือ `backend/app/`) และ **pytest ไม่เก็บไปรัน**
(`backend/pytest.ini` ตั้ง `norecursedirs = scripts`) ชุดเทสต์อัตโนมัติอยู่ที่ `backend/test_*.py` และ `backend/tests/`

สคริปต์ส่วนใหญ่ต่อฐานข้อมูลตาม env `DATABASE_URL` (ไม่ตั้ง = Postgres ในเครื่อง `localhost:5432`)
**ก่อนรันกับ production (Supabase) ให้สำรองก่อนเสมอ**: `bash backend/scripts/migrate_to_supabase.sh dump`

วิธีรันทั่วไป (จากโฟลเดอร์ `backend/`):
```bash
DATABASE_URL='<url>' JWT_SECRET=x PYTHONPATH=. python scripts/<ชื่อสคริปต์>.py
```
หรือใน Docker: `docker compose exec backend python scripts/<ชื่อสคริปต์>.py`

ช่อง "เขียนข้อมูล": ✏️ = แก้/เพิ่มข้อมูล, 🗑️ = ลบข้อมูล, 👁️ = อ่านอย่างเดียว

## 1. รันอัตโนมัติตอน Render start (อยู่ใน `render.yaml` → `startCommand`)
ห้ามลบหรือเปลี่ยนชื่อ ถ้าแก้ต้องแก้ `render.yaml` ด้วย ทุกตัวรันซ้ำได้ (idempotent)

| สคริปต์ | ทำอะไร | เขียนข้อมูล |
|---|---|---|
| `migrate_membership.py` | สร้างตารางคำขอสมัครสมาชิก + คอลัมน์วันที่จัดซื้อ | ✏️ |
| `migrate_role_enum.py --apply` | เติมค่าที่ขาดใน enum `user_role_enum` | ✏️ |
| `migrate_chatbot_studio.py` | เพิ่มคอลัมน์ของหน้า "จัดการ AI / LINE OA" | ✏️ |
| `import_demo_pack.py --apply` | นำเข้าโรงเรียนเดโมครั้งเดียว (ใช้ `demo_schools.json` + `demo_safety.py`) | ✏️ |
| `import_sales_demo.py --apply` | นำเข้าข้อมูลลูกค้า/ยอดขายตัวอย่างครั้งเดียว (ใช้ `app/demo_sales.py`) | ✏️ |

ไฟล์ประกอบ: `demo_schools.json` (ข้อมูลเดโม), `demo_safety.py` (กันสคริปต์ seed ไปเขียน production)

## 2. Migration ที่รันมือครั้งเดียว (รันซ้ำได้ ไม่เสียหาย)
| สคริปต์ | ทำอะไร | เขียนข้อมูล |
|---|---|---|
| `migrate_ticket_indexes.py` | เพิ่ม index ให้รายการใบงานแบบแบ่งหน้า | ✏️ |
| `migrate_audit.py` | ตาราง Audit Log + KB แยกโรงเรียน | ✏️ |
| `migrate_pm.py` | ตาราง/คอลัมน์ของระบบบำรุงรักษา (PM) | ✏️ |
| `migrate_device_ids.py` | แปลงรหัสอุปกรณ์รูปแบบเก่าเป็นรูปแบบใหม่ | ✏️ |
| `migrate_ticket_numbers.py` | แปลงเลข Ticket รูปแบบเก่าเป็นแบบแยกโรงเรียน | ✏️ |
| `retire_legacy_roles.py` | ปิดบัญชีบทบาทเก่า teacher/student | ✏️ |
| `backfill_warranty_mockup.py` | เติมข้อมูลประกันแบบ mockup ให้อุปกรณ์ที่ว่าง | ✏️ |

## 3. ฐานข้อมูล production (Supabase)
| สคริปต์ | ทำอะไร | เขียนข้อมูล |
|---|---|---|
| `migrate_to_supabase.sh check\|dump\|restore\|verify\|lock` | ย้าย/สำรอง/ตรวจฐานข้อมูล อ่าน URL จาก `.env.migrate` (ไม่ขึ้น git) ต้องมี Docker (ใช้ image `postgres:18`) | dump 👁️ / restore ✏️ / lock ✏️ |
| `backup_db.py` | สำรองข้อมูลทุกตารางเป็น `backups/db_<วันเวลา>.sql/.json/.txt` (ข้อมูลอย่างเดียว ไม่มีสคีมา) | 👁️ |
| `promote_local_mockup.py` | คัดลอกโรงเรียนเดโม 5 แห่งจากเครื่องไป production (ถาม URL แบบซ่อน) | ✏️ |
| `export_demo_pack.py` | ส่งออกโรงเรียนเดโมในเครื่องเป็น `demo_schools.json` | 👁️ |

## 4. ข้อมูลตัวอย่างในเครื่อง (ห้ามรันกับ production — `demo_safety.py` กันไว้บางตัว)
| สคริปต์ | ทำอะไร | เขียนข้อมูล |
|---|---|---|
| `seed_mockup_5_schools.py` | 5 โรงเรียน 100 อุปกรณ์ (ลบด้วย `--purge-only`) | ✏️🗑️ |
| `seed_more_schools.py` | เพิ่มโรงเรียน/อุปกรณ์/ticket สำหรับทดสอบหลายโรงเรียน | ✏️ |
| `seed_sales_mockup.py` | ตัวอย่างข้อมูลขาย (เฉพาะในเครื่อง) | ✏️ |
| `seed_db.py` | องค์กร/ห้อง/อุปกรณ์ตัวอย่างชุดเล็ก | ✏️ |
| `seed_admin.py` | ⚠️ **ลบข้อมูลทั้งหมด** แล้วสร้าง super_admin เริ่มต้น | 🗑️✏️ |
| `generate_qr.py` | สร้างไฟล์ QR ของอุปกรณ์จากฐานข้อมูล | 👁️ |

## 5. Smoke test (ยิงระบบจริงด้วยมือ — ไม่ใช่ pytest)
ไฟล์ขึ้นต้น `smoke_` เพื่อไม่ให้ pytest หยิบไปรัน หลายตัวสร้าง/แก้ข้อมูลจริงแล้วเก็บกวาดเอง
| สคริปต์ | ทดสอบอะไร | เขียนข้อมูล |
|---|---|---|
| `smoke_chatbot.py` | บอท LINE 9 สถานการณ์ (เรียก `handle_message` ตรง) | ✏️ |
| `smoke_line_real.py` | เคสจริงจาก log LINE ที่เคยพัง | ✏️ |
| `smoke_api.py` | API หลักผ่าน TestClient (เดิม `backend/run_tests.py`) | ✏️ |
| `smoke_full.py` | flow แจ้งซ่อมผ่านบอท + LINE webhook + RBAC | ✏️ |
| `smoke_kb_perms.py` | สิทธิ์ KB ของ admin_school / admin (ลบข้อมูลที่สร้างเองตอนจบ) | ✏️🗑️ |
| `smoke_notify_endpoints.py` | ทุก endpoint ที่ส่งแจ้งเตือนไป n8n (กันบั๊ก NameError) | ✏️ |
| `verify_secure_line.py` | ตรวจว่าเส้นทาง n8n ยังใช้ได้และคำขอปลอมถูกปฏิเสธ (ทิ้ง log ผู้ใช้ `Uhack*` ไว้ ลบด้วย `cleanup_test_data.py`) | ✏️ log |
| `rbac_probe.py` | ล็อกอินหลายบทบาทแล้วยิง GET API บน Render จริง | 👁️ |

## 6. เก็บกวาดข้อมูลทดสอบ
| สคริปต์ | ทำอะไร | เขียนข้อมูล |
|---|---|---|
| `cleanup_test_data.py` | ลบ log/session/profile ที่เกิดจากการทดสอบ (ไม่แตะ ticket จริง) | 🗑️ |
| `cleanup_tickets.py` | ลบ ticket ทดสอบ + คืนสถานะใบที่ระบุ | 🗑️✏️ |
